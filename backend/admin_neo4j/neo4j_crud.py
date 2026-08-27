# neo4j_crud.py
"""被験者ごとに分離されたナレッジグラフの読み書き。

グラフの分け方（詳細は neo4j_migrate.py の冒頭を参照）:
  - 客観データ  Book / Author / Publisher / NDC       → 全被験者で共有
  - 所有関係    (:Participant)-[:OWNS]->(:Book)       → 誰の蔵書か
  - 主観データ  Concept / Impression / ShelfPosition /
                SHELF_NEXT / PlacementEvent / Discovery → participantId で分離

読み出しは必ず OWNS か participantId を通すこと。ここを1箇所でも通し忘れると
他の被験者の本や意味づけが混ざり、研究データとして使えなくなる。
そのため participant_id は既定値を持たせず、呼び出し側に必ず渡させる。
"""
from admin_neo4j.neo4j_driver import get_session
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
    def _spine_width_px(pages: int) -> float:
        return min(100.0, max(1.0, pages * 0.08))

    @staticmethod
    def _pos_id(participant_id: str, shelf_index: int, column_index: int) -> str:
        """棚の位置IDは被験者ごとに空間を分ける。
        以前は 'pos_r0_c0' という全被験者共通の形だったため、
        20人分を1つのグラフに入れると別人の棚と衝突していた。"""
        return f"{participant_id}:r{shelf_index}c{column_index}"

    @staticmethod
    def ensure_participant(participant_id: str) -> None:
        with get_session() as session:
            session.run(
                "MERGE (p:Participant {participantId: $pid}) "
                "ON CREATE SET p.createdAt = datetime()",
                pid=participant_id,
            )

    # ============================================================
    # 書籍登録
    # ============================================================

    def add_book_with_meaning(self, book_obj, participant_id: str, meaning_text: str = None):
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
                    b.updatedAt = datetime()

                // 蔵書の所有者を登録する（これが被験者ごとのグラフの入口になる）
                WITH b
                MERGE (p:Participant {participantId: $pid})
                    ON CREATE SET p.createdAt = datetime()
                MERGE (p)-[own:OWNS]->(b)
                    ON CREATE SET own.addedAt = datetime()

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

                WITH b
                WHERE $meaning IS NOT NULL AND $meaning <> ""
                CREATE (m:Meaning {text: $meaning, participantId: $pid, createdAt: datetime()})
                MERGE (b)-[:HAS_MEANING]->(m)
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
                ndc_full=ndc_full,
                ndc_l1=ndc_l1,
                ndc_l2=ndc_l2,
                ndc_l3=ndc_l3,
                meaning=meaning_text,
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

    def remove_book_ownership(self, isbn: str, participant_id: str) -> None:
        """棚から本を外したときに所有関係を解除する。
        Book ノード自体は他の被験者が持っている可能性があるので消さない。"""
        with get_session() as session:
            session.run(
                """
                MATCH (:Participant {participantId: $pid})-[own:OWNS]->(:Book {isbn: $isbn})
                DELETE own
                """,
                pid=participant_id,
                isbn=isbn,
            )

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
            return row["conceptId"] if row else None

    def confirm_concept_edge(self, edge_id: str, participant_id: str, confirmed: bool) -> bool:
        """推測エッジ(confidence: inferred)をユーザーの応答で確定／否定する。
        設計書4章③の「弱い推測エッジ」を対話で昇格させるための操作。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (:Book)-[r:CONCEPT {edgeId: $edge_id, participantId: $pid}]->(:Concept)
                SET r.confidence       = CASE WHEN $confirmed THEN 'confirmed' ELSE 'rejected' END,
                    r.strength         = CASE WHEN $confirmed THEN 1.0 ELSE 0.0 END,
                    r.lastReinforcedAt = datetime()
                RETURN r.edgeId AS edgeId
                """,
                edge_id=edge_id,
                pid=participant_id,
                confirmed=confirmed,
            ).single()
            return row is not None

    def delete_concept_edge(self, edge_id: str, participant_id: str) -> bool:
        """本と意味づけ(Concept)の結び付きを1件消す（本詳細パネルの「消す」）。
        他に結び付く本がなくなったConceptノードは道連れに片付ける
        （participantId+textで一意なので、他の意味づけと誤って消す心配はない）。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (:Book)-[r:CONCEPT {edgeId: $edge_id, participantId: $pid}]->(c:Concept)
                DELETE r
                WITH c
                OPTIONAL MATCH (c)<-[remaining:CONCEPT]-()
                WITH c, count(remaining) AS remainingCount
                FOREACH (_ IN CASE WHEN remainingCount = 0 THEN [1] ELSE [] END | DETACH DELETE c)
                RETURN true AS deleted
                """,
                edge_id=edge_id,
                pid=participant_id,
            ).single()
            return row is not None

    def count_concept_nodes(self, participant_id: str) -> int:
        """その被験者が自由に付けた意味づけ（Concept）の累計数。
        本棚からの「強制対話」の閾値判定に使う。"""
        with get_session() as session:
            return session.run(
                "MATCH (c:Concept {participantId: $pid}) RETURN count(c) AS count",
                pid=participant_id,
            ).single()["count"]

    def get_latest_concept_topic(self, participant_id: str) -> dict | None:
        """直近で追加されたConceptと、それに紐づく本を返す。
        強制対話の開始トピックに使う。"""
        with get_session() as session:
            result = session.run(
                """
                MATCH (c:Concept {participantId: $pid})<-[:CONCEPT {participantId: $pid}]-(b:Book)
                WITH c, collect(DISTINCT b.isbn) AS isbns, collect(DISTINCT b.title) AS titles,
                     count(DISTINCT b) AS book_count
                RETURN c.text AS concept, isbns, titles, book_count
                ORDER BY c.createdAt DESC
                LIMIT 1
                """,
                pid=participant_id,
            ).single()
            return dict(result) if result else None

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

            session.run(
                """
                MATCH (b:Book {isbn: $isbn})
                CREATE (i:Impression {
                    impressionId:  randomUUID(),
                    participantId: $pid,
                    text:          $text,
                    createdAt:     datetime()
                })
                MERGE (b)-[:HAS_IMPRESSION]->(i)
                """,
                isbn=isbn,
                pid=participant_id,
                text=text,
            )

    def get_book_impressions(self, isbn: str, participant_id: str) -> list[dict]:
        """1冊の感想を新しい順に返す（設計書3.1の personal_notes[] に相当）。"""
        with get_session() as session:
            return [
                dict(r)
                for r in session.run(
                    """
                    MATCH (:Book {isbn: $isbn})-[:HAS_IMPRESSION]->(i:Impression {participantId: $pid})
                    RETURN i.impressionId AS note_id, i.text AS text,
                           toString(i.createdAt) AS created_at
                    ORDER BY i.createdAt DESC
                    """,
                    isbn=isbn,
                    pid=participant_id,
                )
            ]

    def get_book_basic(self, isbn: str, participant_id: str) -> dict | None:
        """コンパクトな詳細パネル用：書誌情報と最新の感想のみを返す軽量クエリ。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (b:Book {isbn: $isbn})
                OPTIONAL MATCH (b)-[:HAS_IMPRESSION]->(i:Impression {participantId: $pid})
                WITH b, i ORDER BY i.createdAt DESC
                WITH b, head(collect(i)) AS latest
                RETURN
                    b.isbn AS isbn, b.title AS title, b.authors AS authors,
                    b.publisher AS publisher, b.published_year AS published_year,
                    b.cover AS cover, b.spine_image AS spine_image,
                    coalesce(b.description, '') AS description,
                    coalesce(latest.text, '')   AS impression
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

    def update_shelf_layout_chain(self, layout_data: list[dict], participant_id: str):
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
          4. 実際に移動した本だけ PlacementEvent を記録する
        """
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
                sw_a    = self._spine_width_px(a.get("pages", 200))
                gap_px  = (b.get("x_pos", 0) - a.get("x_pos", 0)) * self.PX_SCALE - sw_a
                if gap_px < self.ADJACENCY_GAP_PX:
                    relations.append({
                        "from":        a["isbn"],
                        "to":          b["isbn"],
                        "shelf_index": shelf_index,
                    })

        current_keys = [f"{rel['from']}>{rel['to']}" for rel in relations]

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
                memory_weight = self._calc_memory_weight(shelf_index, is_edge, is_isolated)

                # 1. 直前の位置を先に読む（移動の判定に使う）
                prev = session.run(
                    """
                    MATCH (pos:ShelfPosition {participantId: $pid})-[:LOCATES]->(:Book {isbn: $isbn})
                    RETURN pos.posId AS posId
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
                    WHERE old.posId <> $pos_id
                    DELETE l
                    WITH pos, b
                    MERGE (pos)-[:LOCATES]->(b)
                    """,
                    pid=participant_id,
                    pos_id=pos_id,
                    shelf_index=shelf_index,
                    column_index=column_index,
                    x_pos=item.get("x_pos", 0.0),
                    is_edge=is_edge,
                    is_isolated=is_isolated,
                    memory_weight=memory_weight,
                    isbn=isbn,
                )

                # 3. 実際に位置が変わった本だけ PlacementEvent を残す。
                #    以前は同期のたびに全冊分のイベントを作っていたため、
                #    ログが蔵書数×同期回数まで膨らみ、変遷の分析に使えなかった。
                if prev_pos_id == pos_id:
                    continue

                event_id = f"evt_{participant_id}_{isbn}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                session.run(
                    """
                    CREATE (e:PlacementEvent {
                        eventId:       $event_id,
                        participantId: $pid,
                        timestamp:     datetime(),
                        createdAt:     datetime()
                    })
                    WITH e
                    MATCH (p:Participant {participantId: $pid})
                    MERGE (e)-[:PLACED_BY]->(p)
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
    # 分析クエリ（研究目的：知識体系の広がりと成長の分析）
    # ============================================================

    def query_high_memory_books(self, participant_id: str, threshold: float = 0.8) -> list[dict]:
        """
        memoryWeight が高い位置にある本を取得。
        「重要視されている知識」の分析クエリ。
        """
        with get_session() as session:
            result = session.run(
                """
                MATCH (pos:ShelfPosition {participantId: $pid})-[:LOCATES]->(b:Book)
                WHERE pos.memoryWeight >= $threshold
                OPTIONAL MATCH (b)-[:CLASSIFIED_AS]->(n:NDC)
                RETURN
                    b.title          AS title,
                    b.isbn           AS isbn,
                    n.code           AS ndc,
                    pos.posId        AS position,
                    pos.memoryWeight AS weight
                ORDER BY pos.memoryWeight DESC
                """,
                pid=participant_id,
                threshold=threshold,
            )
            return [dict(r) for r in result]

    def query_placement_history(self, isbn: str, participant_id: str) -> list[dict]:
        """
        1冊の本の配置変遷履歴を時系列で取得。
        「知識成長の追跡」クエリ。
        """
        with get_session() as session:
            result = session.run(
                """
                MATCH (e:PlacementEvent {participantId: $pid})-[:PLACED_BOOK]->(b:Book {isbn: $isbn})
                MATCH (e)-[:PLACED_AT]->(pos:ShelfPosition)
                OPTIONAL MATCH (e)-[:PREVIOUS_POSITION]->(prev:ShelfPosition)
                RETURN
                    e.eventId         AS event,
                    e.timestamp       AS timestamp,
                    pos.posId         AS to_position,
                    pos.memoryWeight  AS to_weight,
                    prev.posId        AS from_position,
                    prev.memoryWeight AS from_weight
                ORDER BY e.timestamp ASC
                """,
                pid=participant_id,
                isbn=isbn,
            )
            return [dict(r) for r in result]

    def query_knowledge_growth(self, participant_id: str) -> list[dict]:
        """
        NDC分類の広がりを集計。本棚の変遷から知識体系の成長を分析する。
        """
        with get_session() as session:
            result = session.run(
                """
                MATCH (:Participant {participantId: $pid})-[own:OWNS]->(b:Book)-[:CLASSIFIED_AS]->(n:NDC)
                WHERE n.level = 1
                RETURN
                    n.code                 AS ndc_l1,
                    count(DISTINCT b.isbn) AS book_count,
                    min(own.addedAt)       AS first_added,
                    max(own.addedAt)       AS last_added
                ORDER BY ndc_l1
                """,
                pid=participant_id,
            )
            return [dict(r) for r in result]

    def query_co_occurrence_pairs(self, participant_id: str, min_count: int = 2) -> list[dict]:
        """繰り返し隣り合わせに置き直されている本のペア。
        設計書5章「高頻度で同時に動かされる本のペア検出」＝未言語化パターンの材料。"""
        with get_session() as session:
            return [
                dict(r)
                for r in session.run(
                    """
                    MATCH (a:Book)-[r:SHELF_NEXT {participantId: $pid}]->(b:Book)
                    WHERE coalesce(r.coOccurrenceCount, 0) >= $min_count
                    RETURN a.isbn AS source_isbn, a.title AS source_title,
                           b.isbn AS target_isbn, b.title AS target_title,
                           r.coOccurrenceCount AS co_occurrence_count,
                           coalesce(r.isCurrent, false) AS is_current
                    ORDER BY r.coOccurrenceCount DESC
                    LIMIT 20
                    """,
                    pid=participant_id,
                    min_count=min_count,
                )
            ]

    def get_graph_overview(self, participant_id: str, shelf_isbns: list[str] | None = None) -> dict:
        """
        ナレッジグラフ全体を俯瞰するための統計スナップショット。
        AIによる提案生成の入力として使う。
        shelf_isbns を渡すと、book_catalog はその本棚に現在並んでいる本だけに絞り込む
        （AI提案が棚に無い本を指してしまい、ハイライトと連動できなくなるのを防ぐため）。
        """
        with get_session() as session:
            total_books = session.run(
                "MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book) RETURN count(b) AS total",
                pid=participant_id,
            ).single()["total"]

            ndc_distribution = [
                dict(r) for r in session.run(
                    """
                    MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)-[:CLASSIFIED_AS]->(n:NDC)
                    WITH substring(n.code, 0, 1) AS ndc_l1, b
                    RETURN
                        ndc_l1,
                        count(DISTINCT b)              AS book_count,
                        collect(DISTINCT b.title)[0..3] AS sample_titles
                    ORDER BY book_count DESC
                    """,
                    pid=participant_id,
                )
            ]

            concept_clusters = [
                dict(r) for r in session.run(
                    """
                    MATCH (c:Concept {participantId: $pid})<-[:CONCEPT]-(b:Book)
                    WITH c, collect(DISTINCT b.title) AS titles, collect(DISTINCT b.isbn) AS isbns,
                         count(DISTINCT b) AS book_count
                    WHERE book_count >= 2
                    RETURN c.text AS concept, titles, isbns, book_count
                    ORDER BY book_count DESC
                    LIMIT 10
                    """,
                    pid=participant_id,
                )
            ]

            favorite_authors = [
                dict(r) for r in session.run(
                    """
                    MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)-[:WRITTEN_BY]->(a:Author)
                    WITH a, count(DISTINCT b) AS book_count,
                         collect(DISTINCT b.title) AS titles, collect(DISTINCT b.isbn) AS isbns
                    WHERE book_count >= 2
                    RETURN a.name AS author, book_count, titles, isbns
                    ORDER BY book_count DESC
                    LIMIT 10
                    """,
                    pid=participant_id,
                )
            ]

            isolated_books = [
                dict(r) for r in session.run(
                    """
                    MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                    WHERE NOT (b)-[:CONCEPT {participantId: $pid}]-()
                      AND NOT (b)-[:SHELF_NEXT {participantId: $pid}]-()
                    RETURN b.title AS title, b.isbn AS isbn,
                           coalesce(b.description, '') AS description
                    LIMIT 15
                    """,
                    pid=participant_id,
                )
            ]

            book_meanings = [
                dict(r) for r in session.run(
                    """
                    MATCH (b:Book)-[r:CONCEPT {participantId: $pid}]->(c:Concept)
                    RETURN b.isbn AS isbn, b.title AS title, c.text AS meaning,
                           r.confidence AS confidence, r.origin AS origin,
                           coalesce(r.strength, 1.0) AS strength
                    ORDER BY c.createdAt DESC
                    LIMIT 12
                    """,
                    pid=participant_id,
                )
            ]

            book_catalog = [
                dict(r) for r in session.run(
                    """
                    MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                    WHERE $shelf_isbns IS NULL OR b.isbn IN $shelf_isbns
                    RETURN b.isbn AS isbn,
                           b.title AS title,
                           coalesce(b.authors, '')     AS authors,
                           coalesce(b.publisher, '')   AS publisher,
                           coalesce(b.description, '') AS description
                    ORDER BY b.title
                    """,
                    pid=participant_id,
                    shelf_isbns=shelf_isbns,
                )
            ]

            return {
                "total_books":      total_books,
                "ndc_distribution": ndc_distribution,
                "concept_clusters": concept_clusters,
                "favorite_authors": favorite_authors,
                "isolated_books":   isolated_books,
                "book_meanings":    book_meanings,
                "book_catalog":     book_catalog,
            }

    # ============================================================
    # Book-Book 関係の抽出（NetworkXによる構造分析用）
    # ============================================================

    def get_book_edges(self, participant_id: str, shelf_isbns: list[str] | None = None) -> list[dict]:
        """
        意味づけ(Concept)・著者・出版社・NDC分類・本棚での隣接、という観点で
        つながっている本のペアを収集する。NetworkXでグラフを組み立てる材料。

        著者・出版社・NDCは全被験者で共有のノードなので、
        両端が「その被験者の蔵書」であることを必ず条件に入れること。
        """
        # 所有関係のフィルタ。これを落とすと他人の本が混ざる。
        own = "MATCH (me:Participant {participantId: $pid})"
        scope = (
            "WHERE a.isbn < b.isbn "
            "AND (me)-[:OWNS]->(a) AND (me)-[:OWNS]->(b) "
            "AND ($shelf_isbns IS NULL OR (a.isbn IN $shelf_isbns AND b.isbn IN $shelf_isbns))"
        )

        queries = {
            "concept": f"""
                {own}
                MATCH (a:Book)-[:CONCEPT {{participantId: $pid}}]->(:Concept {{participantId: $pid}})
                      <-[:CONCEPT {{participantId: $pid}}]-(b:Book)
                {scope}
                RETURN DISTINCT a.isbn AS source, b.isbn AS target
            """,
            "author": f"""
                {own}
                MATCH (a:Book)-[:WRITTEN_BY]->(:Author)<-[:WRITTEN_BY]-(b:Book)
                {scope}
                RETURN DISTINCT a.isbn AS source, b.isbn AS target
            """,
            "publisher": f"""
                {own}
                MATCH (a:Book)-[:PUBLISHED_BY]->(:Publisher)<-[:PUBLISHED_BY]-(b:Book)
                {scope}
                RETURN DISTINCT a.isbn AS source, b.isbn AS target
            """,
            "ndc": f"""
                {own}
                MATCH (a:Book)-[:CLASSIFIED_AS]->(:NDC)<-[:CLASSIFIED_AS]-(b:Book)
                {scope}
                RETURN DISTINCT a.isbn AS source, b.isbn AS target
            """,
            "shelf": f"""
                {own}
                MATCH (a:Book)-[r:SHELF_NEXT {{participantId: $pid}}]-(b:Book)
                {scope} AND coalesce(r.isCurrent, true) = true
                RETURN DISTINCT a.isbn AS source, b.isbn AS target
            """,
        }

        edges: list[dict] = []
        with get_session() as session:
            for edge_type, query in queries.items():
                for r in session.run(query, pid=participant_id, shelf_isbns=shelf_isbns):
                    edges.append({"source": r["source"], "target": r["target"], "type": edge_type})
        return edges

    # ============================================================
    # 複数冊(本棚のAI分析の提案など)を対象にした部分グラフの抽出
    # ============================================================

    def get_subgraph_for_isbns(self, isbns: list[str], participant_id: str) -> dict:
        """
        与えられた本(複数冊)同士の、意味づけ(Concept)・著者・出版社・NDC分類・
        本棚での隣接、というつながりだけを抜き出した部分グラフを返す。
        AI分析の提案に対応する本たちの「知識グラフ上でのつながり」を可視化する用途。
        """
        if not isbns:
            return {"nodes": [], "links": []}

        with get_session() as session:
            book_rows = session.run(
                """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                WHERE b.isbn IN $isbns
                RETURN b.isbn AS isbn, b.title AS title, b.cover AS cover,
                       b.spine_image AS spine_image, b.authors AS authors
                """,
                pid=participant_id,
                isbns=isbns,
            )
            nodes: dict[str, dict] = {}
            for r in book_rows:
                nodes[f"book_{r['isbn']}"] = {"id": f"book_{r['isbn']}", "type": "Book", **dict(r)}

            links: list[dict] = []

            def _add_group_links(query: str, mid_prefix: str, mid_type: str, mid_label_key: str, link_type: str):
                for r in session.run(query, isbns=isbns, pid=participant_id):
                    mid_id = f"{mid_prefix}_{r['mid']}"
                    nodes.setdefault(mid_id, {"id": mid_id, "type": mid_type, **{mid_label_key: r["mid_label"]}})
                    links.append({"source": f"book_{r['a_isbn']}", "target": mid_id, "type": link_type})
                    links.append({"source": f"book_{r['b_isbn']}", "target": mid_id, "type": link_type})

            _add_group_links(
                """
                MATCH (a:Book)-[:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
                      <-[:CONCEPT {participantId: $pid}]-(b:Book)
                WHERE a.isbn IN $isbns AND b.isbn IN $isbns AND a.isbn < b.isbn
                RETURN DISTINCT a.isbn AS a_isbn, b.isbn AS b_isbn, c.conceptId AS mid, c.text AS mid_label
                """,
                "concept", "Concept", "text", "CONCEPT",
            )
            _add_group_links(
                """
                MATCH (me:Participant {participantId: $pid})
                MATCH (a:Book)-[:WRITTEN_BY]->(x:Author)<-[:WRITTEN_BY]-(b:Book)
                WHERE a.isbn IN $isbns AND b.isbn IN $isbns AND a.isbn < b.isbn
                  AND (me)-[:OWNS]->(a) AND (me)-[:OWNS]->(b)
                RETURN DISTINCT a.isbn AS a_isbn, b.isbn AS b_isbn, id(x) AS mid, x.name AS mid_label
                """,
                "author", "Author", "name", "WRITTEN_BY",
            )
            _add_group_links(
                """
                MATCH (me:Participant {participantId: $pid})
                MATCH (a:Book)-[:PUBLISHED_BY]->(x:Publisher)<-[:PUBLISHED_BY]-(b:Book)
                WHERE a.isbn IN $isbns AND b.isbn IN $isbns AND a.isbn < b.isbn
                  AND (me)-[:OWNS]->(a) AND (me)-[:OWNS]->(b)
                RETURN DISTINCT a.isbn AS a_isbn, b.isbn AS b_isbn, id(x) AS mid, x.name AS mid_label
                """,
                "publisher", "Publisher", "name", "PUBLISHED_BY",
            )
            _add_group_links(
                """
                MATCH (me:Participant {participantId: $pid})
                MATCH (a:Book)-[:CLASSIFIED_AS]->(x:NDC)<-[:CLASSIFIED_AS]-(b:Book)
                WHERE a.isbn IN $isbns AND b.isbn IN $isbns AND a.isbn < b.isbn
                  AND (me)-[:OWNS]->(a) AND (me)-[:OWNS]->(b)
                RETURN DISTINCT a.isbn AS a_isbn, b.isbn AS b_isbn, id(x) AS mid, x.code AS mid_label
                """,
                "ndc", "NDC", "code", "CLASSIFIED_AS",
            )

            for r in session.run(
                """
                MATCH (a:Book)-[r:SHELF_NEXT {participantId: $pid}]-(b:Book)
                WHERE a.isbn IN $isbns AND b.isbn IN $isbns AND a.isbn < b.isbn
                  AND coalesce(r.isCurrent, true) = true
                RETURN DISTINCT a.isbn AS a_isbn, b.isbn AS b_isbn
                """,
                pid=participant_id,
                isbns=isbns,
            ):
                links.append({"source": f"book_{r['a_isbn']}", "target": f"book_{r['b_isbn']}", "type": "SHELF_NEXT"})

            return {"nodes": list(nodes.values()), "links": links}

    # ============================================================
    # 本1冊を中心にした関連本の抽出（タップ時の詳細パネル用）
    # ============================================================

    def get_book_relations(self, isbn: str, participant_id: str) -> dict | None:
        """
        1冊を中心に、意味づけ(Concept)・著者・出版社・NDC分類・本棚での隣接、
        という観点でつながっている本を「理由」付きで取得する。
        あわせて、そのつながりを描画するための小さな部分グラフ(nodes/links)も返す。
        """
        with get_session() as session:
            book_row = session.run(
                """
                MATCH (b:Book {isbn: $isbn})
                RETURN
                    b.isbn AS isbn, b.title AS title, b.authors AS authors,
                    b.publisher AS publisher, b.published_year AS published_year,
                    b.cover AS cover, b.spine_image AS spine_image,
                    coalesce(b.description, '') AS description
                """,
                isbn=isbn,
            ).single()
            if not book_row:
                return None
            book = dict(book_row)

            reasons_by_isbn: dict[str, list[dict]] = defaultdict(list)
            related_meta: dict[str, dict] = {}
            sub_nodes: dict[str, dict] = {
                f"book_{isbn}": {"id": f"book_{isbn}", "type": "Book", **book},
            }
            sub_links: list[dict] = []

            def _register_related(row, reason, mid_id, mid_node, mid_link_type):
                oid = row["isbn"]
                if oid not in related_meta:
                    related_meta[oid] = {
                        "isbn":        oid,
                        "title":       row["title"],
                        "cover":       row["cover"],
                        "spine_image": row["spine_image"],
                        "authors":     row["authors"],
                    }
                reasons_by_isbn[oid].append(reason)
                sub_nodes.setdefault(mid_id, mid_node)
                sub_nodes.setdefault(f"book_{oid}", {"id": f"book_{oid}", "type": "Book", **related_meta[oid]})
                sub_links.append({"source": f"book_{isbn}", "target": mid_id, "type": mid_link_type})
                sub_links.append({"source": f"book_{oid}",  "target": mid_id, "type": mid_link_type})

            # 同じ意味づけ (Concept) ── 「この本は同じ意味づけをしています」
            for r in session.run(
                """
                MATCH (b:Book {isbn: $isbn})-[:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
                      <-[:CONCEPT {participantId: $pid}]-(o:Book)
                WHERE o.isbn <> $isbn
                RETURN DISTINCT o.isbn AS isbn, o.title AS title, o.cover AS cover,
                       o.spine_image AS spine_image, o.authors AS authors,
                       c.text AS concept_text, c.conceptId AS cid
                """,
                isbn=isbn,
                pid=participant_id,
            ):
                _register_related(
                    r,
                    {"type": "concept", "label": "同じ意味づけ", "detail": r["concept_text"]},
                    f"concept_{r['cid']}",
                    {"id": f"concept_{r['cid']}", "type": "Concept", "text": r["concept_text"]},
                    "CONCEPT",
                )

            # 同じ著者（自分の蔵書に限る）
            for r in session.run(
                """
                MATCH (me:Participant {participantId: $pid})
                MATCH (b:Book {isbn: $isbn})-[:WRITTEN_BY]->(a:Author)<-[:WRITTEN_BY]-(o:Book)
                WHERE o.isbn <> $isbn AND (me)-[:OWNS]->(o)
                RETURN DISTINCT o.isbn AS isbn, o.title AS title, o.cover AS cover,
                       o.spine_image AS spine_image, o.authors AS authors,
                       a.name AS author_name, id(a) AS aid
                """,
                isbn=isbn,
                pid=participant_id,
            ):
                _register_related(
                    r,
                    {"type": "author", "label": "同じ著者", "detail": r["author_name"]},
                    f"author_{r['aid']}",
                    {"id": f"author_{r['aid']}", "type": "Author", "name": r["author_name"]},
                    "WRITTEN_BY",
                )

            # 同じ出版社（自分の蔵書に限る）
            for r in session.run(
                """
                MATCH (me:Participant {participantId: $pid})
                MATCH (b:Book {isbn: $isbn})-[:PUBLISHED_BY]->(p:Publisher)<-[:PUBLISHED_BY]-(o:Book)
                WHERE o.isbn <> $isbn AND (me)-[:OWNS]->(o)
                RETURN DISTINCT o.isbn AS isbn, o.title AS title, o.cover AS cover,
                       o.spine_image AS spine_image, o.authors AS authors,
                       p.name AS publisher_name, id(p) AS pid_node
                """,
                isbn=isbn,
                pid=participant_id,
            ):
                _register_related(
                    r,
                    {"type": "publisher", "label": "同じ出版社", "detail": r["publisher_name"]},
                    f"publisher_{r['pid_node']}",
                    {"id": f"publisher_{r['pid_node']}", "type": "Publisher", "name": r["publisher_name"]},
                    "PUBLISHED_BY",
                )

            # 同じNDC分類（自分の蔵書に限る）
            for r in session.run(
                """
                MATCH (me:Participant {participantId: $pid})
                MATCH (b:Book {isbn: $isbn})-[:CLASSIFIED_AS]->(n:NDC)<-[:CLASSIFIED_AS]-(o:Book)
                WHERE o.isbn <> $isbn AND (me)-[:OWNS]->(o)
                RETURN DISTINCT o.isbn AS isbn, o.title AS title, o.cover AS cover,
                       o.spine_image AS spine_image, o.authors AS authors,
                       n.code AS ndc_code, id(n) AS nid
                """,
                isbn=isbn,
                pid=participant_id,
            ):
                _register_related(
                    r,
                    {"type": "ndc", "label": "同じNDC分類", "detail": r["ndc_code"]},
                    f"ndc_{r['nid']}",
                    {"id": f"ndc_{r['nid']}", "type": "NDC", "code": r["ndc_code"]},
                    "CLASSIFIED_AS",
                )

            # 本棚で隣接（現在隣り合っているもの）
            for r in session.run(
                """
                MATCH (b:Book {isbn: $isbn})-[rel:SHELF_NEXT {participantId: $pid}]-(o:Book)
                WHERE o.isbn <> $isbn AND coalesce(rel.isCurrent, true) = true
                RETURN DISTINCT o.isbn AS isbn, o.title AS title, o.cover AS cover,
                       o.spine_image AS spine_image, o.authors AS authors
                """,
                isbn=isbn,
                pid=participant_id,
            ):
                oid = r["isbn"]
                if oid not in related_meta:
                    related_meta[oid] = {
                        "isbn": oid, "title": r["title"], "cover": r["cover"],
                        "spine_image": r["spine_image"], "authors": r["authors"],
                    }
                reasons_by_isbn[oid].append({"type": "shelf", "label": "本棚で隣接", "detail": None})
                sub_nodes.setdefault(f"book_{oid}", {"id": f"book_{oid}", "type": "Book", **related_meta[oid]})
                sub_links.append({"source": f"book_{isbn}", "target": f"book_{oid}", "type": "SHELF_NEXT"})

            related = [
                {**meta, "reasons": reasons_by_isbn[oid]}
                for oid, meta in related_meta.items()
            ]
            related.sort(key=lambda r: -len(r["reasons"]))

            return {
                "book": book,
                "related": related[:12],
                "subgraph": {
                    "nodes": list(sub_nodes.values()),
                    "links": sub_links,
                },
            }

    def get_book_concepts(self, isbn: str, participant_id: str) -> list[dict]:
        """指定した本に紐づく意味づけ(Concept)と、それを共有する他の本のISBN一覧を返す。
        本棚でカーソルを合わせた時のホバー強調（意味づけの表示）に使う軽量クエリ。"""
        with get_session() as session:
            result = session.run(
                """
                MATCH (b:Book {isbn: $isbn})-[r:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
                OPTIONAL MATCH (c)<-[:CONCEPT {participantId: $pid}]-(o:Book)
                WHERE o.isbn <> $isbn
                WITH c, r, collect(DISTINCT o.isbn) AS related_isbns
                RETURN c.text AS text, related_isbns,
                       r.edgeId AS edge_id,
                       coalesce(r.confidence, 'confirmed') AS confidence,
                       coalesce(r.strength, 1.0) AS strength
                ORDER BY c.text
                """,
                isbn=isbn,
                pid=participant_id,
            )
            return [dict(r) for r in result]

    # ============================================================
    # グラフ全体の取得（知識グラフ画面用）
    # ============================================================

    def get_full_graph(self, participant_id: str) -> dict:
        """その被験者の知識グラフだけを返す。
        以前は MATCH (n) でDB全体を返していたため、被験者が増えると
        他人のグラフがそのまま画面に出てしまう。"""
        with get_session() as session:
            nodes = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (me:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                    OPTIONAL MATCH (b)-[:WRITTEN_BY]->(a:Author)
                    OPTIONAL MATCH (b)-[:PUBLISHED_BY]->(p:Publisher)
                    OPTIONAL MATCH (b)-[:CLASSIFIED_AS]->(n:NDC)
                    OPTIONAL MATCH (b)-[:CONCEPT {participantId: $pid}]->(c:Concept)
                    WITH collect(DISTINCT b) + collect(DISTINCT a) + collect(DISTINCT p)
                       + collect(DISTINCT n) + collect(DISTINCT c) AS all_nodes
                    UNWIND all_nodes AS node
                    WITH DISTINCT node WHERE node IS NOT NULL
                    RETURN
                        id(node)                          AS id,
                        labels(node)[0]                   AS type,
                        coalesce(node.isbn, '')           AS isbn,
                        coalesce(node.title, '')          AS title,
                        coalesce(node.authors, '')        AS authors,
                        coalesce(node.publisher, '')      AS publisher,
                        coalesce(node.published_year, '') AS published_year,
                        coalesce(node.cover, '')          AS cover,
                        coalesce(node.spine_image, '')    AS spine_image,
                        coalesce(node.description, '')    AS description,
                        coalesce(node.pages, 0)           AS pages,
                        coalesce(node.height_mm, 0)       AS height_mm,
                        coalesce(node.name, '')           AS name,
                        coalesce(node.code, '')           AS code,
                        coalesce(node.level, 0)           AS level,
                        coalesce(node.text, '')           AS text
                    """,
                    pid=participant_id,
                )
            ]

            node_ids = {n["id"] for n in nodes}

            links = [
                {"source": r["source"], "target": r["target"], "type": r["type"]}
                for r in session.run(
                    """
                    MATCH (me:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                    MATCH (b)-[r]->(x)
                    WHERE type(r) IN ['WRITTEN_BY', 'PUBLISHED_BY', 'CLASSIFIED_AS']
                       OR (type(r) IN ['CONCEPT', 'SHELF_NEXT'] AND r.participantId = $pid)
                    RETURN DISTINCT id(b) AS source, id(x) AS target, type(r) AS type
                    """,
                    pid=participant_id,
                )
                if r["source"] in node_ids and r["target"] in node_ids
            ]

            return {"nodes": nodes, "links": links}

    # ============================================================
    # Discovery（LLMの発見）── 設計書3.3
    #
    # 以前は /analyze の出力をその場で返して捨てていたため、
    # status も user_feedback も残らず、7.3のフィードバック収集が成立しなかった。
    # ============================================================

    def save_discoveries(self, discoveries: list[dict], participant_id: str) -> list[dict]:
        """発見を永続化して discovery_id を振る。
        discoveries: [{"type", "generated_question", "related_book_ids", "body"}, ...]"""
        if not discoveries:
            return []

        saved = []
        with get_session() as session:
            for d in discoveries:
                discovery_id = str(uuid.uuid4())
                session.run(
                    """
                    CREATE (d:Discovery {
                        discoveryId:       $discovery_id,
                        participantId:     $pid,
                        type:              $type,
                        title:             $title,
                        generatedQuestion: $question,
                        body:              $body,
                        status:            'pending',
                        createdAt:         datetime()
                    })
                    WITH d
                    UNWIND $isbns AS isbn
                    MATCH (b:Book {isbn: isbn})
                    MERGE (d)-[:RELATES_TO]->(b)
                    """,
                    discovery_id=discovery_id,
                    pid=participant_id,
                    type=d.get("type", "structural"),
                    title=d.get("title", ""),
                    question=d.get("generated_question", ""),
                    body=d.get("body", ""),
                    isbns=d.get("related_book_ids") or [],
                )
                saved.append({**d, "discovery_id": discovery_id, "status": "pending"})
        return saved

    def record_discovery_feedback(
        self,
        discovery_id: str,
        participant_id: str,
        status: str,
        surprise_score: float | None = None,
        agreement_score: float | None = None,
        comment: str | None = None,
    ) -> bool:
        """発見に対する納得度・驚き度を記録する（設計書7.3）。

        「そう」「一部ちがう」と答えられた発見は、ここで初めて実際の意味づけ(Concept)として
        知識グラフに書き戻す。分析（/analyze）の時点ではまだAIの仮説にすぎず、ユーザーの
        判断を経て初めて事実になる、という設計にしているため、書き戻しは発見時ではなく
        回答時に行う。これにより次回以降の分析・育成度・本詳細パネルの意味づけ一覧に反映される。
        「ちがう」は何も書き戻さない（同じ問いを繰り返さないことは asked_questions 側で担保する）。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (d:Discovery {discoveryId: $discovery_id, participantId: $pid})
                SET d.status          = $status,
                    d.surpriseScore   = $surprise,
                    d.agreementScore  = $agreement,
                    d.userComment     = $comment,
                    d.respondedAt     = datetime()
                RETURN d.discoveryId AS id, d.title AS title, d.generatedQuestion AS question
                """,
                discovery_id=discovery_id,
                pid=participant_id,
                status=status,
                surprise=surprise_score,
                agreement=agreement_score,
                comment=comment,
            ).single()
            if row is None:
                return False

            if status == "modified":
                # 訂正の一言（comment）こそが正しい意味づけなので、それを優先する。
                # まだコメント入力前（1段目のボタンだけ押した直後）は comment が空で来るので、
                # そのときは何も書き戻さず、コメント確定時の呼び出しを待つ。
                meaning = (comment or "").strip()
            elif status == "confirmed":
                meaning = (row["title"] or "").strip()
                if not meaning:
                    meaning = (row["question"] or "").strip().rstrip("?？").strip()
            else:
                meaning = ""

            if meaning:
                session.run(
                    """
                    MATCH (d:Discovery {discoveryId: $discovery_id, participantId: $pid})-[:RELATES_TO]->(b:Book)
                    WITH collect(DISTINCT b) AS books
                    MERGE (c:Concept {participantId: $pid, text: $meaning})
                        ON CREATE SET c.conceptId = randomUUID(), c.createdAt = datetime()
                    WITH c, books
                    UNWIND books AS b
                    MERGE (b)-[r:CONCEPT {participantId: $pid}]->(c)
                        ON CREATE SET r.edgeId = randomUUID(), r.createdAt = datetime(), r.reinforceCount = 1
                        ON MATCH SET r.reinforceCount = coalesce(r.reinforceCount, 1) + 1
                    SET r.confidence       = 'confirmed',
                        r.strength         = 1.0,
                        r.origin           = 'ai_discovery',
                        r.lastReinforcedAt = datetime()
                    """,
                    discovery_id=discovery_id,
                    pid=participant_id,
                    meaning=meaning,
                )
            return True

    def list_discoveries(self, participant_id: str, status: str | None = None) -> list[dict]:
        with get_session() as session:
            return [
                dict(r)
                for r in session.run(
                    """
                    MATCH (d:Discovery {participantId: $pid})
                    WHERE $status IS NULL OR d.status = $status
                    OPTIONAL MATCH (d)-[:RELATES_TO]->(b:Book)
                    // 集約したあとは ORDER BY から d を参照できないので、
                    // 先に WITH でまとめてから並べ替える
                    WITH d, collect(DISTINCT b.isbn) AS related_book_ids
                    ORDER BY d.createdAt DESC
                    LIMIT 100
                    RETURN d.discoveryId       AS discovery_id,
                           d.type              AS type,
                           coalesce(d.title, '') AS title,
                           d.generatedQuestion AS generated_question,
                           d.body              AS body,
                           d.status            AS status,
                           d.surpriseScore     AS surprise_score,
                           d.agreementScore    AS agreement_score,
                           d.userComment       AS user_comment,
                           toString(d.createdAt) AS created_at,
                           related_book_ids
                    """,
                    pid=participant_id,
                    status=status,
                )
            ]

    # ============================================================
    # 対話履歴（左ペイン「発見と対話」）
    #
    # 以前はDialoguePanelのReact stateのみで持っていたため、リロードすると
    # 消えていた。被験者ごとに機器を共有する研究運用（participant.js参照）
    # では localStorage だと別の被験者のIDに乗ってしまう恐れがあるため、
    # Discoveryと同じくバックエンド側にparticipantId付きで永続化する。
    # ============================================================

    def save_chat_message(
        self,
        participant_id: str,
        role: str,
        text: str,
        related_book_ids: list[str] | None = None,
    ) -> None:
        with get_session() as session:
            session.run(
                """
                CREATE (m:ChatMessage {
                    messageId:      $mid,
                    participantId:  $pid,
                    role:           $role,
                    text:           $text,
                    relatedBookIds: $isbns,
                    createdAt:      datetime()
                })
                """,
                mid=str(uuid.uuid4()),
                pid=participant_id,
                role=role,
                text=text,
                isbns=related_book_ids or [],
            )

    def list_chat_history(self, participant_id: str, limit: int = 300) -> list[dict]:
        with get_session() as session:
            return [
                dict(r)
                for r in session.run(
                    """
                    MATCH (m:ChatMessage {participantId: $pid})
                    RETURN m.messageId      AS message_id,
                           m.role           AS role,
                           m.text           AS text,
                           m.relatedBookIds AS related_isbns,
                           toString(m.createdAt) AS created_at
                    ORDER BY m.createdAt ASC
                    LIMIT $limit
                    """,
                    pid=participant_id,
                    limit=limit,
                )
            ]

    def clear_chat_history(self, participant_id: str) -> None:
        with get_session() as session:
            session.run(
                "MATCH (m:ChatMessage {participantId: $pid}) DETACH DELETE m",
                pid=participant_id,
            )

    def write_concept_for_books(
        self,
        participant_id: str,
        meaning: str,
        isbns: list[str],
        origin: str = "chat_summary",
    ) -> None:
        """雑談の要約をユーザーが確認した上で意味づけとして書き戻す。
        record_discovery_feedback の書き戻しと同じ形（MERGE Concept→CONCEPT edge）だが、
        根拠がDiscoveryノードではなく対話そのものなので、対象の本をISBNで直接受け取る。"""
        meaning = (meaning or "").strip()
        isbns = [i for i in isbns if i]
        if not meaning or not isbns:
            return
        with get_session() as session:
            session.run(
                """
                MERGE (c:Concept {participantId: $pid, text: $meaning})
                    ON CREATE SET c.conceptId = randomUUID(), c.createdAt = datetime()
                WITH c
                UNWIND $isbns AS isbn
                MATCH (b:Book {isbn: isbn})
                MERGE (b)-[r:CONCEPT {participantId: $pid}]->(c)
                    ON CREATE SET r.edgeId = randomUUID(), r.createdAt = datetime(), r.reinforceCount = 1
                    ON MATCH SET r.reinforceCount = coalesce(r.reinforceCount, 1) + 1
                SET r.confidence       = 'confirmed',
                    r.strength         = 1.0,
                    r.origin           = $origin,
                    r.lastReinforcedAt = datetime()
                """,
                pid=participant_id,
                meaning=meaning,
                isbns=isbns,
                origin=origin,
            )

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
                WITH me, books, concepts, concept_edges, count(DISTINCT i) AS impressions
                OPTIONAL MATCH (d:Discovery {participantId: $pid})
                WITH books, concepts, concept_edges, impressions,
                     count(d) AS discoveries,
                     count(CASE WHEN d.status = 'confirmed' THEN 1 END) AS confirmed
                RETURN books, concepts, concept_edges, impressions, discoveries, confirmed
                """,
                pid=participant_id,
            ).single()

            stats = dict(row) if row else {
                "books": 0, "concepts": 0, "concept_edges": 0,
                "impressions": 0, "discoveries": 0, "confirmed": 0,
            }

            # 「意味づけがどれだけ蓄積されたか」を 0.0〜1.0 に丸めた値。
            # 蔵書数ではなく主観の量で育つようにする（本を並べただけでは育たない）。
            subjective = stats["concept_edges"] + stats["impressions"] + stats["confirmed"] * 2
            stats["level"] = round(min(1.0, subjective / 60.0), 3)
            return stats

    def get_answered_discovery_questions(self, participant_id: str, limit: int = 30) -> list[str]:
        """すでに提示済みの質問文。同じ問いを繰り返さないためにLLMへ渡す。"""
        with get_session() as session:
            return [
                r["q"]
                for r in session.run(
                    """
                    MATCH (d:Discovery {participantId: $pid})
                    WHERE d.generatedQuestion IS NOT NULL AND d.generatedQuestion <> ''
                    RETURN d.generatedQuestion AS q
                    ORDER BY d.createdAt DESC
                    LIMIT $limit
                    """,
                    pid=participant_id,
                    limit=limit,
                )
            ]


# ============================================================
# モジュールレベル互換
#
# participant_id は既定値を持たせない。呼び出し側が渡し忘れたら
# 静かに他人のデータへ混ざるのではなく、その場で TypeError で落とす。
# ============================================================

_neo4j = BookshelfNeo4j()

ensure_participant                = _neo4j.ensure_participant
add_book_with_meaning             = _neo4j.add_book_with_meaning
remove_book_ownership             = _neo4j.remove_book_ownership
groups_from_neo4j                 = _neo4j.groups_from_neo4j
save_concept                      = _neo4j.save_concept
confirm_concept_edge              = _neo4j.confirm_concept_edge
delete_concept_edge               = _neo4j.delete_concept_edge
count_concept_nodes               = _neo4j.count_concept_nodes
get_latest_concept_topic          = _neo4j.get_latest_concept_topic
update_shelf_layout_chain         = _neo4j.update_shelf_layout_chain
query_high_memory_books           = _neo4j.query_high_memory_books
query_placement_history           = _neo4j.query_placement_history
query_knowledge_growth            = _neo4j.query_knowledge_growth
query_co_occurrence_pairs         = _neo4j.query_co_occurrence_pairs
get_graph_overview                = _neo4j.get_graph_overview
get_book_relations                = _neo4j.get_book_relations
get_book_concepts                 = _neo4j.get_book_concepts
get_book_basic                    = _neo4j.get_book_basic
save_book_impression              = _neo4j.save_book_impression
get_book_impressions              = _neo4j.get_book_impressions
get_book_edges                    = _neo4j.get_book_edges
get_subgraph_for_isbns            = _neo4j.get_subgraph_for_isbns
get_full_graph                    = _neo4j.get_full_graph
save_discoveries                  = _neo4j.save_discoveries
record_discovery_feedback         = _neo4j.record_discovery_feedback
list_discoveries                  = _neo4j.list_discoveries
get_answered_discovery_questions  = _neo4j.get_answered_discovery_questions
get_growth_stats                  = _neo4j.get_growth_stats
save_chat_message                 = _neo4j.save_chat_message
list_chat_history                 = _neo4j.list_chat_history
clear_chat_history                = _neo4j.clear_chat_history
write_concept_for_books           = _neo4j.write_concept_for_books
