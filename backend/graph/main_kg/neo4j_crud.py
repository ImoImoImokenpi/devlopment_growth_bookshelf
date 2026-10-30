# neo4j_crud.py
"""被験者ごとに分離されたナレッジグラフの読み書き。

グラフの分け方（詳細は neo4j_migrate.py の冒頭を参照）:
  - 客観データ  Book / Author / Publisher / NDC       → 全被験者で共有
  - 所有関係    (:Participant)-[:OWNS]->(:Book)       → 誰の蔵書か
  - 主観データ  Concept / Impression / ShelfPosition /
                SHELF_NEXT / PlacementEvent          → participantId で分離

読み出しは必ず OWNS か participantId を通すこと。ここを1箇所でも通し忘れると
他の被験者の本や意味づけが混ざり、研究データとして使えなくなる。
そのため participant_id は既定値を持たせず、呼び出し側に必ず渡させる。
"""
from graph.main_kg.neo4j_driver import get_session
from collections import defaultdict
from datetime import datetime
import uuid


class BookshelfNeo4j:

    PX_SCALE = 1.2
    ADJACENCY_GAP_PX = 1

    # ============================================================
    # 内部ユーティリティ
    # ============================================================

    @staticmethod
    def _calc_memory_weight(row_index: int, is_edge: bool, is_isolated: bool) -> float:
        """
        bs:memoryWeight の算出式（TTL定義と完全対応）
        memoryWeight = min(1.0, w_row × w_col × w_iso)

        w_row: rowIndex=0(最上段)=1.0 / 1=0.8 / 2以下=0.6
        w_col: isEdge=True → 1.0 / else → 0.7
        w_iso: isIsolated=True → 1.2 / else → 1.0
        """
        w_row = {0: 1.0, 1: 0.8}.get(row_index, 0.6)
        w_col = 1.0 if is_edge else 0.7
        w_iso = 1.2 if is_isolated else 1.0
        return round(min(1.0, w_row * w_col * w_iso), 4)

    @staticmethod
    def _spine_width_px(pages: int, height_mm: int | None = None) -> float:
        # 文庫(高さ160mm以下)は背幅を細めにする
        factor = 0.75 if height_mm and height_mm <= 160 else 1.0
        return min(100.0, max(1.0, pages * 0.08 * factor))

    @staticmethod
    def _pos_id(participant_id: str, shelf_index: int, column_index: int) -> str:
        """棚の位置IDは被験者ごとに空間を分ける。
        以前は 'pos_r0_c0' という全被験者共通の形だったため、
        20人分を1つのグラフに入れると別人の棚と衝突していた。"""
        return f"{participant_id}:r{shelf_index}c{column_index}"

    @staticmethod
    def _create_event(session, label: str, participant_id: str, by_rel: str, extra_props: dict | None = None) -> str:
        """操作ログイベントノードを1つ作り、Participantへ by_rel でつなぐ。
        PlacementEvent（棚レイアウト更新チェーン内で個別実装）と同じ形
        （eventId/participantId/timestamp/createdAt）に揃えるための共通ヘルパー。
        対象（本・グループ等）への関係は呼び出し側が個別に張る。
        label/by_rel は呼び出し側が固定文字列でしか渡さない前提（f-stringで埋め込むが、
        ユーザー入力が混ざることはない）。"""
        event_id = f"evt_{label.lower()}_{participant_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        session.run(
            f"""
            CREATE (e:{label} {{
                eventId: $event_id, participantId: $pid,
                timestamp: datetime(), createdAt: datetime()
            }})
            SET e += $extra
            WITH e
            MATCH (p:Participant {{participantId: $pid}})
            MERGE (e)-[:{by_rel}]->(p)
            """,
            event_id=event_id, pid=participant_id, extra=extra_props or {},
        )
        return event_id

    # ============================================================
    # 書籍登録
    # ============================================================

    def add_book_with_meaning(self, book_obj, participant_id: str):
        """
        SQLAlchemyのオブジェクト(MyHand/MyBookshelf) または dict を受け取り、
        Neo4jのナレッジグラフを更新・作成する。
        書誌情報は共有ノードとして MERGE し、その本を participant の蔵書として登録する。
        """
        def get_val(key, default=None):
            if isinstance(book_obj, dict):
                return book_obj.get(key, default)
            return getattr(book_obj, key, default)

        ndc_full = get_val("ndc") or ""
        ndc_l1 = ndc_full[0] if len(ndc_full) >= 1 and ndc_full[0].isdigit() else None
        ndc_l2 = ndc_full[:2] if len(ndc_full) >= 2 and ndc_full[:2].isdigit() else None
        ndc_l3 = ndc_full[:3] if len(ndc_full) >= 3 and ndc_full[:3].isdigit() else None

        authors = get_val("authors")
        if isinstance(authors, list):
            author_list = [a.strip() for a in authors if a.strip()]
            authors_str = ", ".join(author_list)
        else:
            authors_str = str(authors) if authors else "不明"
            author_list = [a.strip() for a in authors_str.split(",") if a.strip() and a.strip() != "不明"]

        publisher = get_val("publisher") or ""

        with get_session() as session:
            session.run(
                """
                MERGE (b:Book {isbn: $isbn})
                SET
                    b.title = $title,
                    b.authors = $authors,
                    b.publisher = $publisher,
                    b.published_year = $published_year,
                    b.cover = $cover,
                    b.spine_image = $spine_image,
                    b.height_mm = $height_mm,
                    b.pages = $pages,
                    b.size_label = $size_label,
                    b.description = $description,
                    b.spine_color = $spine_color,
                    b.updatedAt = datetime()

                // 蔵書の所有者を登録する（これが被験者ごとのグラフの入口になる）
                WITH b
                MERGE (p:Participant {participantId: $pid})
                    ON CREATE SET p.createdAt = datetime()
                MERGE (p)-[own:OWNS]->(b)
                    ON CREATE SET own.addedAt = datetime(), own.possessedSince = date()

                WITH b
                FOREACH (code IN CASE WHEN $ndc_l1 IS NOT NULL THEN [$ndc_l1] ELSE [] END |
                    MERGE (n:NDC {code: code}) ON CREATE SET n.level = 1
                )
                WITH b
                FOREACH (code IN CASE WHEN $ndc_l2 IS NOT NULL THEN [$ndc_l2] ELSE [] END |
                    MERGE (n:NDC {code: code}) ON CREATE SET n.level = 2
                )
                WITH b
                WHERE $ndc_l1 IS NOT NULL AND $ndc_l2 IS NOT NULL
                MATCH (n1:NDC {code: $ndc_l1})
                MATCH (n2:NDC {code: $ndc_l2})
                MERGE (n2)-[:BROADER]->(n1)

                WITH b
                FOREACH (code IN CASE WHEN $ndc_l3 IS NOT NULL THEN [$ndc_l3] ELSE [] END |
                    MERGE (n:NDC {code: code}) ON CREATE SET n.level = 3
                )
                WITH b
                WHERE $ndc_l2 IS NOT NULL AND $ndc_l3 IS NOT NULL
                MATCH (n2:NDC {code: $ndc_l2})
                MATCH (n3:NDC {code: $ndc_l3})
                MERGE (n3)-[:BROADER]->(n2)

                WITH b
                WHERE $ndc_full IS NOT NULL AND $ndc_full <> ""
                MERGE (nf:NDC {code: $ndc_full})
                ON CREATE SET nf.level = 4
                MERGE (b)-[:CLASSIFIED_AS]->(nf)

                WITH b, nf
                WHERE $ndc_l3 IS NOT NULL AND $ndc_full <> $ndc_l3
                MATCH (n3:NDC {code: $ndc_l3})
                MERGE (nf)-[:BROADER]->(n3)
                """,
                pid=participant_id,
                isbn=get_val("isbn"),
                title=get_val("title"),
                authors=authors_str,
                publisher=get_val("publisher"),
                published_year=get_val("published_year"),
                cover=get_val("cover"),
                spine_image=get_val("spine_image"),
                height_mm=get_val("height_mm"),
                pages=get_val("pages"),
                size_label=get_val("size_label"),
                description=get_val("description"),
                spine_color=get_val("spine_color"),
                ndc_full=ndc_full,
                ndc_l1=ndc_l1,
                ndc_l2=ndc_l2,
                ndc_l3=ndc_l3,
            )

            if author_list:
                session.run(
                    """
                    MATCH (b:Book {isbn: $isbn})
                    UNWIND $author_list AS author_name
                    MERGE (a:Author {name: author_name})
                    MERGE (b)-[:WRITTEN_BY]->(a)
                    """,
                    isbn=get_val("isbn"),
                    author_list=author_list,
                )

            if publisher:
                session.run(
                    """
                    MATCH (b:Book {isbn: $isbn})
                    MERGE (p:Publisher {name: $publisher})
                    MERGE (b)-[:PUBLISHED_BY]->(p)
                    """,
                    isbn=get_val("isbn"),
                    publisher=publisher,
                )

    def update_book_attributes(self, isbn: str, fields: dict) -> None:
        """高さ・色などの手動補正をNeo4jのBookノードにも反映する。
        add_book_with_meaning と違い、Participant/OWNSには触れない
        （補正は所有関係と無関係な、本そのものの物理属性の書き換えのため）。"""
        if not fields:
            return
        with get_session() as session:
            session.run(
                "MATCH (b:Book {isbn: $isbn}) SET b += $fields, b.updatedAt = datetime()",
                isbn=isbn,
                fields=fields,
            )

    def remove_book_ownership(self, isbn: str, participant_id: str) -> None:
        """棚から本を外したときに所有関係と棚の位置を解除する。
        Book ノード自体は他の被験者が持っている可能性があるので消さない。
        （以前は OWNS だけを外していて、棚の位置 LOCATES が残っていた）"""
        with get_session() as session:
            session.run(
                """
                MATCH (b:Book {isbn: $isbn})
                OPTIONAL MATCH (:Participant {participantId: $pid})-[own:OWNS]->(b)
                OPTIONAL MATCH (:ShelfPosition {participantId: $pid})-[loc:LOCATES]->(b)
                DELETE own, loc
                """,
                pid=participant_id,
                isbn=isbn,
            )

    def reconcile_shelf(self, participant_id: str, shelf_isbns: list[str]) -> dict:
        """画面の本棚（SQLite の ShelfLayout, present）を正として、そこにない本の
        所有関係(OWNS)と棚の位置(LOCATES)を外す。Book ノードや意味づけは消さない。
        実験準備のスクリプトなどで SQLite 側だけが作り直されると、知識グラフに
        棚にない本が残り、対話のLLMや冊数の表示に紛れ込むため。"""
        with get_session() as session:
            owns = session.run(
                """
                MATCH (:Participant {participantId: $pid})-[own:OWNS]->(b:Book)
                WHERE NOT b.isbn IN $isbns
                DELETE own
                RETURN count(own) AS c
                """,
                pid=participant_id, isbns=shelf_isbns,
            ).single()["c"]
            locates = session.run(
                """
                MATCH (:ShelfPosition {participantId: $pid})-[loc:LOCATES]->(b:Book)
                WHERE NOT b.isbn IN $isbns
                DELETE loc
                RETURN count(loc) AS c
                """,
                pid=participant_id, isbns=shelf_isbns,
            ).single()["c"]
        return {"owns_removed": owns, "locates_removed": locates}

    # ============================================================
    # NDCグルーピング
    # ============================================================

    def groups_from_neo4j(self, participant_id: str):
        with get_session() as session:
            result = session.run(
                """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                OPTIONAL MATCH (b)-[:CLASSIFIED_AS]->(n:NDC)
                WITH
                    coalesce(n.code, "未分類") AS ndc,
                    b
                ORDER BY toFloat(ndc), b.title
                RETURN
                    ndc,
                    collect({
                        isbn: b.isbn,
                        title: b.title,
                        cover: b.cover
                    }) AS books
                """,
                pid=participant_id,
            )
            groups = []
            for record in result:
                if record["books"]:
                    groups.append({"ndc": record["ndc"], "books": record["books"]})
            return groups

    # ============================================================
    # Concept（意味づけ）
    #
    # 設計書3.2に対応。意味づけの属性はノードではなくリレーションに載せる。
    #   Concept ノード   … 「何という意味づけか」（被験者ごとに独立）
    #   CONCEPT リレーション … 「その本にいつ・どういう由来で・どのくらいの
    #                          確信度で結び付けられたか」
    # ============================================================

    def save_concept(
        self,
        isbns: list[str],
        meaning: str,
        participant_id: str,
        origin: str = "user_initiated",
        confidence: str = "confirmed",
        strength: float = 1.0,
    ) -> str:
        """複数冊への意味づけを保存する。同じ被験者が同じ文言を再び使った場合は
        既存の Concept を再利用し、リレーション側の強度を上げる（再強化）。
        戻り値は Concept の ID。"""
        with get_session() as session:
            row = session.run(
                """
                MERGE (c:Concept {participantId: $pid, text: $meaning})
                    ON CREATE SET c.conceptId = randomUUID(), c.createdAt = datetime()
                WITH c
                UNWIND $isbns AS isbn
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book {isbn: isbn})
                MERGE (b)-[r:CONCEPT {participantId: $pid}]->(c)
                    ON CREATE SET
                        r.edgeId         = randomUUID(),
                        r.createdAt      = datetime(),
                        r.reinforceCount = 1,
                        r.strength       = $strength
                    ON MATCH SET
                        r.reinforceCount = coalesce(r.reinforceCount, 1) + 1,
                        // 再び同じ意味づけをされたら強くなる（上限1.0）
                        r.strength       = CASE WHEN coalesce(r.strength, 0.0) + 0.2 > 1.0
                                                THEN 1.0
                                                ELSE coalesce(r.strength, 0.0) + 0.2 END
                SET r.origin           = $origin,
                    r.confidence       = $confidence,
                    r.lastReinforcedAt = datetime()
                RETURN c.conceptId AS conceptId
                """,
                pid=participant_id,
                meaning=meaning,
                isbns=isbns,
                origin=origin,
                confidence=confidence,
                strength=strength,
            ).single()
            # 以前はここで作成ログ(GroupCreateEvent)も残していたが、グルーピングの
            # 操作ログは使わなくなったので作らない。対話から生まれた意味づけの由来は
            # MeaningProposal -[:BECAME]-> Concept で追える。
            return row["conceptId"] if row else None

    # ============================================================
    # 感想（Impression）
    #
    # 以前は Book.impression というプロパティに上書き保存していたが、
    #   - Book は全被験者で共有なので他人の感想が見えてしまう
    #   - 上書きなので設計書3.1の personal_notes[] のような履歴が残らない
    # という2点があるため、被験者ごとの Impression ノードに切り出した。
    # ============================================================

    def save_book_impression(self, isbn: str, text: str, participant_id: str) -> None:
        with get_session() as session:
            latest = session.run(
                """
                MATCH (:Book {isbn: $isbn})-[:HAS_IMPRESSION]->(i:Impression {participantId: $pid})
                RETURN i.text AS text
                ORDER BY i.createdAt DESC
                LIMIT 1
                """,
                isbn=isbn,
                pid=participant_id,
            ).single()

            # 中身が変わっていなければ履歴を増やさない（自動保存で埋まるのを防ぐ）
            if latest and (latest["text"] or "") == (text or ""):
                return

            impression_row = session.run(
                """
                MATCH (b:Book {isbn: $isbn})
                CREATE (i:Impression {
                    impressionId:  randomUUID(),
                    participantId: $pid,
                    text:          $text,
                    createdAt:     datetime()
                })
                MERGE (b)-[:HAS_IMPRESSION]->(i)
                RETURN i.impressionId AS impression_id
                """,
                isbn=isbn,
                pid=participant_id,
                text=text,
            ).single()

            event_id = self._create_event(session, "CommentEvent", participant_id, "COMMENTED_BY")
            session.run(
                """
                MATCH (e:CommentEvent {eventId: $event_id})
                MATCH (b:Book {isbn: $isbn})
                MERGE (e)-[:ABOUT_BOOK]->(b)
                WITH e
                MATCH (i:Impression {impressionId: $impression_id})
                MERGE (e)-[:ABOUT_IMPRESSION]->(i)
                """,
                event_id=event_id,
                isbn=isbn,
                impression_id=impression_row["impression_id"] if impression_row else None,
            )

    def get_book_basic(self, isbn: str, participant_id: str) -> dict | None:
        """コンパクトな詳細パネル用：書誌情報と最新の感想のみを返す軽量クエリ。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (b:Book {isbn: $isbn})
                OPTIONAL MATCH (b)-[:HAS_IMPRESSION]->(i:Impression {participantId: $pid})
                WITH b, i ORDER BY i.createdAt DESC
                WITH b, head(collect(i)) AS latest
                OPTIONAL MATCH (:Participant {participantId: $pid})-[own:OWNS]->(b)
                RETURN
                    b.isbn AS isbn, b.title AS title, b.authors AS authors,
                    b.publisher AS publisher, b.published_year AS published_year,
                    b.cover AS cover, b.spine_image AS spine_image,
                    coalesce(b.description, '') AS description,
                    coalesce(latest.text, '')   AS impression,
                    toString(own.possessedSince) AS possessed_since
                """,
                isbn=isbn,
                pid=participant_id,
            ).single()
            return dict(row) if row else None

    # ============================================================
    # 棚レイアウト更新
    #
    # TTL対応:
    #   bs:ShelfPosition → (:ShelfPosition {posId, participantId, shelfIndex,
    #                                        columnIndex, xPos, isEdge,
    #                                        isIsolated, memoryWeight})
    #   bs:locates       → [:LOCATES]
    #   bs:adjacentTo    → [:SHELF_NEXT]
    # ============================================================

    def update_shelf_layout_chain(
        self, layout_data: list[dict], participant_id: str, moved_isbns: list[str] | None = None,
        dialogue_session_id: str | None = None,
    ):
        """
        layout_data: [
            {
                "isbn": str,
                "shelf_index": int,   # 段番号（0=最上段）
                "x_pos": float,       # フロントの水平座標
                "order_index": int,   # 左から何番目か
                "pages": int,         # ページ数（背幅の計算に使用）
            },
            ...
        ]

        実行内容:
          1. ShelfPosition ノードを生成・更新し memoryWeight を付与
          2. ShelfPosition → Book の LOCATES を張り替える（常に現在位置1つだけ）
          3. 隣接 Book 間の SHELF_NEXT を「共起の履歴」として積み上げる
          4. 移動の記録（moved_isbns = ユーザーが直接ドラッグした本だけが対象。
             挿し込みで押し出されて位置がずれただけの本は記録しない）
             - 対話中（dialogue_session_id あり）: PlacementEvent を作り、
               その対話へ DURING_DIALOGUE でつなぐ。対話が生んだ移動だけを履歴に残す。
             - 対話の外: 履歴は残さない。次の対話のきっかけにするため、
               Participant.pendingMoves（"isbn|元の段|元の列"）に1冊1件だけ加える。
               最初の対話までの並べ替えは整理なので、最初の対話の開始時に捨てる
               （graph/dialogue/store.py）。
        """
        moved_set = set(moved_isbns or [])
        # ── 棚ごとにグループ化・ソート ───────────────────────────
        rows: dict[int, list[dict]] = defaultdict(list)
        for book in layout_data:
            rows[book["shelf_index"]].append(book)

        for shelf_books in rows.values():
            shelf_books.sort(key=lambda b: b.get("x_pos", 0))

        # ── isEdge / isIsolated を計算 ───────────────────────────
        # （ShelfPosition.memoryWeight の算出に必要）
        enriched: list[dict] = []
        for shelf_index, shelf_books in rows.items():
            n = len(shelf_books)
            for i, book in enumerate(shelf_books):
                is_edge     = (i == 0) or (i == n - 1)
                # 両隣が空 = このスロットだけ孤立（shelf 内で隣接本がない）
                is_isolated = n == 1
                enriched.append({**book, "is_edge": is_edge, "is_isolated": is_isolated})

        # ── SHELF_NEXT 用の隣接ペアを計算 ────────────────────────
        relations = []
        for shelf_index, shelf_books in rows.items():
            for i in range(len(shelf_books) - 1):
                a = shelf_books[i]
                b = shelf_books[i + 1]
                sw_a    = self._spine_width_px(a.get("pages", 200), a.get("height_mm"))
                gap_px  = (b.get("x_pos", 0) - a.get("x_pos", 0)) * self.PX_SCALE - sw_a
                if gap_px < self.ADJACENCY_GAP_PX:
                    relations.append({
                        "from":        a["isbn"],
                        "to":          b["isbn"],
                        "shelf_index": shelf_index,
                    })

        current_keys = [f"{rel['from']}>{rel['to']}" for rel in relations]

        # 同じISBNの本を棚に2冊以上置けるようになったため、「この本がいる位置」は
        # isbn単位では1つに定まらない。3で使う「古いLOCATESの掃除」は、この同期で
        # 書き込む全スロットを除いた本当に空いたスロットだけを対象にする必要がある
        # （そうしないと、複数冊が互いのLOCATESを消し合ってしまう）。
        isbn_pos_ids: dict[str, list[str]] = defaultdict(list)
        for item in enriched:
            pos_id = self._pos_id(participant_id, item["shelf_index"], item["order_index"])
            isbn_pos_ids[item["isbn"]].append(pos_id)

        # ── Neo4j 更新 ────────────────────────────────────────────
        with get_session() as session:
            session.run(
                "MERGE (p:Participant {participantId: $pid}) "
                "ON CREATE SET p.createdAt = datetime()",
                pid=participant_id,
            )

            for item in enriched:
                shelf_index  = item["shelf_index"]
                column_index = item["order_index"]
                is_edge      = item["is_edge"]
                is_isolated  = item["is_isolated"]
                isbn         = item["isbn"]
                pos_id       = self._pos_id(participant_id, shelf_index, column_index)
                current_pos_ids_for_isbn = isbn_pos_ids[isbn]
                memory_weight = self._calc_memory_weight(shelf_index, is_edge, is_isolated)

                # 1. 直前の位置を先に読む（移動の判定に使う）
                prev = session.run(
                    """
                    MATCH (pos:ShelfPosition {participantId: $pid})-[:LOCATES]->(:Book {isbn: $isbn})
                    RETURN pos.posId AS posId, pos.shelfIndex AS shelfIndex, pos.columnIndex AS columnIndex
                    LIMIT 1
                    """,
                    pid=participant_id,
                    isbn=isbn,
                ).single()
                prev_pos_id = prev["posId"] if prev else None

                # 2. ShelfPosition を更新し、LOCATES を現在位置だけに張り替える。
                #    以前は MERGE するだけで古い LOCATES を消しておらず、
                #    1冊が過去の位置すべてに紐づいたままになっていた。
                session.run(
                    """
                    MERGE (pos:ShelfPosition {posId: $pos_id})
                    SET
                        pos.participantId = $pid,
                        pos.shelfIndex    = $shelf_index,
                        pos.columnIndex   = $column_index,
                        pos.xPos          = $x_pos,
                        pos.isEdge        = $is_edge,
                        pos.isIsolated    = $is_isolated,
                        pos.memoryWeight  = $memory_weight,
                        pos.updatedAt     = datetime()

                    WITH pos
                    MATCH (b:Book {isbn: $isbn})
                    WITH pos, b
                    OPTIONAL MATCH (old:ShelfPosition {participantId: $pid})-[l:LOCATES]->(b)
                    WHERE NOT old.posId IN $current_pos_ids
                    DELETE l
                    WITH pos, b
                    MERGE (pos)-[:LOCATES]->(b)
                    """,
                    pid=participant_id,
                    pos_id=pos_id,
                    current_pos_ids=current_pos_ids_for_isbn,
                    shelf_index=shelf_index,
                    column_index=column_index,
                    x_pos=item.get("x_pos", 0.0),
                    is_edge=is_edge,
                    is_isolated=is_isolated,
                    memory_weight=memory_weight,
                    isbn=isbn,
                )

                # 3. 移動の記録。ユーザーが直接動かし、実際に位置が変わった本だけが対象。
                if prev_pos_id == pos_id or isbn not in moved_set:
                    continue

                if not dialogue_session_id:
                    # 対話の外: 履歴は残さず「次の対話で話題にする本」に加えるだけ
                    # （同じ本は最初に動かす前の位置を残すため、すでにあれば加えない）
                    entry = "|".join([
                        isbn,
                        "" if not prev or prev["shelfIndex"] is None else str(prev["shelfIndex"]),
                        "" if not prev or prev["columnIndex"] is None else str(prev["columnIndex"]),
                    ])
                    session.run(
                        """
                        MATCH (p:Participant {participantId: $pid})
                        WITH p, coalesce(p.pendingMoves, []) AS pm
                        WHERE none(x IN pm WHERE x STARTS WITH $prefix)
                        SET p.pendingMoves = pm + [$entry]
                        """,
                        pid=participant_id, prefix=isbn + "|", entry=entry,
                    )
                    continue

                event_id = f"evt_{participant_id}_{isbn}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                session.run(
                    """
                    CREATE (e:PlacementEvent {
                        eventId:       $event_id,
                        participantId: $pid,
                        direct:        true,
                        timestamp:     datetime(),
                        createdAt:     datetime()
                    })
                    WITH e
                    MATCH (p:Participant {participantId: $pid})
                    MERGE (e)-[:PLACED_BY]->(p)
                    WITH e
                    MATCH (s:DialogueSession {sessionId: $sid, participantId: $pid})
                    MERGE (e)-[:DURING_DIALOGUE]->(s)
                    WITH e
                    MATCH (b:Book {isbn: $isbn})
                    MERGE (e)-[:PLACED_BOOK]->(b)
                    WITH e
                    MATCH (pos:ShelfPosition {posId: $pos_id})
                    MERGE (e)-[:PLACED_AT]->(pos)
                    """,
                    event_id=event_id,
                    pid=participant_id,
                    isbn=isbn,
                    pos_id=pos_id,
                    sid=dialogue_session_id,
                )

                if prev_pos_id:
                    session.run(
                        """
                        MATCH (e:PlacementEvent {eventId: $event_id})
                        MATCH (prev:ShelfPosition {posId: $prev_pos_id})
                        MERGE (e)-[:PREVIOUS_POSITION]->(prev)
                        """,
                        event_id=event_id,
                        prev_pos_id=prev_pos_id,
                    )

            # 4. 隣接関係を「履歴として」積み上げる。
            #    以前は毎回すべて削除して張り直していたため、
            #    設計書5章の「高頻度で同時に動かされる本のペア」が計算できなかった。
            #    ここでは、隣接していなかったペアが新たに隣り合ったときだけ
            #    coOccurrenceCount を1つ進める（＝隣接が何回作り直されたか）。
            if relations:
                session.run(
                    """
                    UNWIND $relations AS rel
                    MATCH (a:Book {isbn: rel.from})
                    MATCH (b:Book {isbn: rel.to})
                    MERGE (a)-[r:SHELF_NEXT {participantId: $pid}]->(b)
                        ON CREATE SET
                            r.coOccurrenceCount = 1,
                            r.firstSeenAt       = datetime(),
                            r.formedAt          = datetime()
                        ON MATCH SET
                            r.coOccurrenceCount = coalesce(r.coOccurrenceCount, 0) +
                                CASE WHEN coalesce(r.isCurrent, false) THEN 0 ELSE 1 END,
                            r.formedAt = CASE WHEN coalesce(r.isCurrent, false)
                                              THEN r.formedAt ELSE datetime() END
                    SET r.shelf_index = rel.shelf_index,
                        r.isCurrent   = true,
                        r.lastSeenAt  = datetime()
                    """,
                    pid=participant_id,
                    relations=relations,
                )

            # 5. もう隣接していないペアは、消さずに「現在は隣ではない」印だけ付ける
            session.run(
                """
                MATCH (a:Book)-[r:SHELF_NEXT {participantId: $pid}]->(b:Book)
                WHERE coalesce(r.isCurrent, false) = true
                  AND NOT (a.isbn + '>' + b.isbn) IN $current_keys
                SET r.isCurrent = false, r.separatedAt = datetime()
                """,
                pid=participant_id,
                current_keys=current_keys,
            )

    # ============================================================
    # 本1冊を中心にした関連本の抽出（タップ時の詳細パネル用）
    # ============================================================

    def get_growth_stats(self, participant_id: str) -> dict:
        """知識グラフがどれだけ育っているかの素の数値。

        画面では数値ではなく雰囲気（照明の強さ）で見せるが、
        その元になる量はここで一度に数えて返す（設計書6.4）。
        """
        with get_session() as session:
            row = session.run(
                """
                MATCH (me:Participant {participantId: $pid})
                OPTIONAL MATCH (me)-[:OWNS]->(b:Book)
                WITH me, count(DISTINCT b) AS books
                OPTIONAL MATCH (c:Concept {participantId: $pid})
                WITH me, books, count(DISTINCT c) AS concepts
                OPTIONAL MATCH (:Book)-[r:CONCEPT {participantId: $pid}]->(:Concept)
                WITH me, books, concepts, count(r) AS concept_edges
                OPTIONAL MATCH (:Book)-[:HAS_IMPRESSION]->(i:Impression {participantId: $pid})
                WITH books, concepts, concept_edges, count(DISTINCT i) AS impressions
                RETURN books, concepts, concept_edges, impressions
                """,
                pid=participant_id,
            ).single()

            stats = dict(row) if row else {
                "books": 0, "concepts": 0, "concept_edges": 0, "impressions": 0,
            }

            # 「意味づけがどれだけ蓄積されたか」を 0.0〜1.0 に丸めた値。
            # 蔵書数ではなく主観の量で育つようにする（本を並べただけでは育たない）。
            subjective = stats["concept_edges"] + stats["impressions"]
            stats["level"] = round(min(1.0, subjective / 60.0), 3)
            return stats


# ============================================================
# モジュールレベル互換
#
# participant_id は既定値を持たせない。呼び出し側が渡し忘れたら
# 静かに他人のデータへ混ざるのではなく、その場で TypeError で落とす。
# ============================================================

_neo4j = BookshelfNeo4j()

add_book_with_meaning             = _neo4j.add_book_with_meaning
update_book_attributes            = _neo4j.update_book_attributes
remove_book_ownership             = _neo4j.remove_book_ownership
reconcile_shelf                   = _neo4j.reconcile_shelf
groups_from_neo4j                 = _neo4j.groups_from_neo4j
save_concept                      = _neo4j.save_concept
update_shelf_layout_chain         = _neo4j.update_shelf_layout_chain
get_book_basic                    = _neo4j.get_book_basic
save_book_impression              = _neo4j.save_book_impression
get_growth_stats                  = _neo4j.get_growth_stats
