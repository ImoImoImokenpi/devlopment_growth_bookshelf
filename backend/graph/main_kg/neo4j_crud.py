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
    def _spine_width_px(pages: int) -> float:
        return min(100.0, max(1.0, pages * 0.08))

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
            concept_id = row["conceptId"] if row else None

            if concept_id:
                event_id = self._create_event(session, "GroupCreateEvent", participant_id, "CREATED_BY")
                session.run(
                    """
                    MATCH (e:GroupCreateEvent {eventId: $event_id})
                    MATCH (c:Concept {conceptId: $concept_id})
                    MERGE (e)-[:CREATED_GROUP]->(c)
                    WITH e
                    UNWIND $isbns AS isbn
                    MATCH (b:Book {isbn: isbn})
                    MERGE (e)-[:INCLUDED_BOOK]->(b)
                    """,
                    event_id=event_id, concept_id=concept_id, isbns=isbns,
                )

            return concept_id

    def delete_concept_edge(self, edge_id: str, participant_id: str) -> bool:
        """意味づけ(Concept)そのものを削除する（本詳細パネルの「消す」）。
        Conceptはparticipantid+textで一意な「その意味づけ自体」を表すノードなので、
        edge_idから辿れるConceptをDETACH DELETEすれば、それを共有する本すべてから
        まとめて消える（1冊だけの結び付きを外す操作ではない。フロント側は削除前に
        related_isbnsの件数を見て確認ダイアログを出す）。
        グルーピングモードの左パネルからの削除は conceptId で呼べる delete_group を使うこと。
        こちらは互換のため残している。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (:Book)-[:CONCEPT {edgeId: $edge_id, participantId: $pid}]->(c:Concept)
                DETACH DELETE c
                RETURN true AS deleted
                """,
                edge_id=edge_id,
                pid=participant_id,
            ).single()
            return row is not None

    # ============================================================
    # グループ管理（グルーピングモード用）
    #
    # 「グループ」は新規のノード種別ではなく、既存の Concept（意味づけ）を
    # そのまま使う。左パネルの一覧・リネーム・統合・メンバー追加削除・削除は
    # すべて Concept ノードと CONCEPT リレーションへの操作として実装する。
    # ============================================================

    def list_participant_groups(self, participant_id: str) -> list[dict]:
        """参加者が持つ全グループ(=Concept)を、所属冊数・メンバー一覧付きで返す。
        グルーピングモードの左パネルの一覧表示に使う。"""
        with get_session() as session:
            result = session.run(
                """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                      -[r:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
                WITH c, collect({isbn: b.isbn, title: b.title, cover: b.cover, edge_id: r.edgeId}) AS members
                RETURN c.conceptId AS concept_id, c.text AS text, toString(c.createdAt) AS created_at,
                       size(members) AS book_count, members
                ORDER BY c.text
                """,
                pid=participant_id,
            )
            return [dict(r) for r in result]

    def remove_group_member(self, concept_id: str, isbn: str, participant_id: str) -> bool:
        """グループから本を1冊だけ外す。delete_concept_edgeと違い、他の本には影響しない。
        外した結果メンバーが0冊になった場合は、そのConceptごと片付ける。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (b:Book {isbn: $isbn})-[r:CONCEPT {participantId: $pid}]->
                      (c:Concept {conceptId: $concept_id, participantId: $pid})
                DELETE r
                WITH c
                OPTIONAL MATCH (c)<-[remaining:CONCEPT {participantId: $pid}]-(:Book)
                WITH c, count(remaining) AS n
                FOREACH (_ IN CASE WHEN n = 0 THEN [1] ELSE [] END | DETACH DELETE c)
                RETURN true AS ok
                """,
                concept_id=concept_id, isbn=isbn, pid=participant_id,
            ).single()
            if row is None:
                return False

            event_id = self._create_event(
                session, "GroupEditEvent", participant_id, "EDITED_BY",
                {"action": "remove_member", "conceptId": concept_id, "isbn": isbn},
            )
            session.run(
                """
                MATCH (e:GroupEditEvent {eventId: $event_id})
                MATCH (b:Book {isbn: $isbn})
                MERGE (e)-[:AFFECTED_BOOK]->(b)
                WITH e
                OPTIONAL MATCH (c:Concept {conceptId: $concept_id})
                FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (e)-[:EDITED_GROUP]->(c)
                )
                """,
                event_id=event_id, isbn=isbn, concept_id=concept_id,
            )
            return True

    def add_group_members(self, concept_id: str, isbns: list[str], participant_id: str) -> int:
        """既存グループ(conceptId起点)に本を追加する。save_concept と同じ再強化ロジック。
        棚からグループへドラッグして追加する操作に使う。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (c:Concept {conceptId: $concept_id, participantId: $pid})
                UNWIND $isbns AS isbn
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book {isbn: isbn})
                MERGE (b)-[r:CONCEPT {participantId: $pid}]->(c)
                    ON CREATE SET
                        r.edgeId         = randomUUID(),
                        r.createdAt      = datetime(),
                        r.reinforceCount = 1,
                        r.strength       = 1.0
                    ON MATCH SET
                        r.reinforceCount = coalesce(r.reinforceCount, 1) + 1,
                        r.strength       = CASE WHEN coalesce(r.strength, 0.0) + 0.2 > 1.0
                                                THEN 1.0
                                                ELSE coalesce(r.strength, 0.0) + 0.2 END
                SET r.origin           = "user_initiated",
                    r.confidence       = "confirmed",
                    r.lastReinforcedAt = datetime()
                RETURN count(r) AS n
                """,
                concept_id=concept_id, isbns=isbns, pid=participant_id,
            ).single()
            n = row["n"] if row else 0

            if n:
                event_id = self._create_event(
                    session, "GroupEditEvent", participant_id, "EDITED_BY",
                    {"action": "add_member", "conceptId": concept_id},
                )
                session.run(
                    """
                    MATCH (e:GroupEditEvent {eventId: $event_id})
                    MATCH (c:Concept {conceptId: $concept_id})
                    MERGE (e)-[:EDITED_GROUP]->(c)
                    WITH e
                    UNWIND $isbns AS isbn
                    MATCH (b:Book {isbn: isbn})
                    MERGE (e)-[:AFFECTED_BOOK]->(b)
                    """,
                    event_id=event_id, concept_id=concept_id, isbns=isbns,
                )
            return n

    def remove_group_members(self, concept_id: str, isbns: list[str], participant_id: str) -> int:
        """グループから本を複数まとめて外す。remove_group_member の複数冊版。
        棚でグループハイライト中に複数選択してまとめて除外する操作に使う。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (c:Concept {conceptId: $concept_id, participantId: $pid})
                UNWIND $isbns AS isbn
                OPTIONAL MATCH (b:Book {isbn: isbn})-[r:CONCEPT {participantId: $pid}]->(c)
                DELETE r
                WITH c, count(r) AS removed
                OPTIONAL MATCH (c)<-[remaining:CONCEPT {participantId: $pid}]-(:Book)
                WITH c, removed, count(remaining) AS n
                FOREACH (_ IN CASE WHEN n = 0 THEN [1] ELSE [] END | DETACH DELETE c)
                RETURN removed
                """,
                concept_id=concept_id, isbns=isbns, pid=participant_id,
            ).single()
            removed = row["removed"] if row else 0

            if removed:
                event_id = self._create_event(
                    session, "GroupEditEvent", participant_id, "EDITED_BY",
                    {"action": "remove_member", "conceptId": concept_id},
                )
                session.run(
                    """
                    MATCH (e:GroupEditEvent {eventId: $event_id})
                    OPTIONAL MATCH (c:Concept {conceptId: $concept_id})
                    FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
                        MERGE (e)-[:EDITED_GROUP]->(c)
                    )
                    WITH e
                    UNWIND $isbns AS isbn
                    MATCH (b:Book {isbn: isbn})
                    MERGE (e)-[:AFFECTED_BOOK]->(b)
                    """,
                    event_id=event_id, concept_id=concept_id, isbns=isbns,
                )
            return removed

    def _merge_concepts(self, session, participant_id: str, source_concept_ids: list[str], target_text: str) -> dict | None:
        """リネーム・統合の共通下請け。target_text へ get-or-create した Concept に、
        各 source の CONCEPT エッジを付け替え、空になった source は削除する。
        呼び出し側のセッション内で実行する（イベント記録とトランザクションを揃えるため）。"""
        target_row = session.run(
            """
            MERGE (target:Concept {participantId: $pid, text: $target_text})
                ON CREATE SET target.conceptId = randomUUID(), target.createdAt = datetime()
            RETURN target.conceptId AS concept_id
            """,
            pid=participant_id, target_text=target_text,
        ).single()
        if not target_row:
            return None
        target_concept_id = target_row["concept_id"]

        for source_id in source_concept_ids:
            if source_id == target_concept_id:
                continue
            session.run(
                """
                MATCH (target:Concept {conceptId: $target_concept_id})
                MATCH (source:Concept {conceptId: $source_id, participantId: $pid})
                OPTIONAL MATCH (b:Book)-[r:CONCEPT {participantId: $pid}]->(source)
                FOREACH (_ IN CASE WHEN b IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (b)-[nr:CONCEPT {participantId: $pid}]->(target)
                        ON CREATE SET
                            nr.edgeId         = coalesce(r.edgeId, randomUUID()),
                            nr.createdAt      = coalesce(r.createdAt, datetime()),
                            nr.reinforceCount = coalesce(r.reinforceCount, 1),
                            nr.strength       = coalesce(r.strength, 1.0),
                            nr.origin         = coalesce(r.origin, "user_initiated"),
                            nr.confidence     = coalesce(r.confidence, "confirmed")
                        ON MATCH SET
                            nr.reinforceCount = coalesce(nr.reinforceCount, 1) + coalesce(r.reinforceCount, 1),
                            nr.strength       = CASE WHEN coalesce(nr.strength, 0.0) >= coalesce(r.strength, 0.0)
                                                    THEN nr.strength ELSE r.strength END
                )
                WITH source, r
                WHERE r IS NOT NULL
                DELETE r
                """,
                target_concept_id=target_concept_id, source_id=source_id, pid=participant_id,
            )
            session.run(
                """
                MATCH (source:Concept {conceptId: $source_id, participantId: $pid})
                WHERE NOT (source)<-[:CONCEPT {participantId: $pid}]-(:Book)
                DETACH DELETE source
                """,
                source_id=source_id, pid=participant_id,
            )

        count_row = session.run(
            """
            MATCH (target:Concept {conceptId: $target_concept_id})
            OPTIONAL MATCH (target)<-[:CONCEPT {participantId: $pid}]-(b:Book)
            RETURN target.text AS text, count(DISTINCT b) AS book_count
            """,
            target_concept_id=target_concept_id, pid=participant_id,
        ).single()
        return {
            "concept_id": target_concept_id,
            "text": count_row["text"] if count_row else target_text,
            "book_count": count_row["book_count"] if count_row else 0,
        }

    def rename_group(self, concept_id: str, new_text: str, participant_id: str) -> dict | None:
        """グループ名を変更する。既存の別グループと同名になる場合は実質的な統合になる
        （merge_concepts と同じ下請けを使うため）。"""
        with get_session() as session:
            result = self._merge_concepts(session, participant_id, [concept_id], new_text)
            if result:
                event_id = self._create_event(
                    session, "GroupEditEvent", participant_id, "EDITED_BY",
                    {"action": "rename", "newText": new_text},
                )
                session.run(
                    """
                    MATCH (e:GroupEditEvent {eventId: $event_id})
                    MATCH (c:Concept {conceptId: $concept_id})
                    MERGE (e)-[:EDITED_GROUP]->(c)
                    """,
                    event_id=event_id, concept_id=result["concept_id"],
                )
            return result

    def merge_groups(self, source_concept_ids: list[str], target_text: str, participant_id: str) -> dict | None:
        """2つ以上のグループをドラッグ&ドロップ等で統合する。"""
        with get_session() as session:
            # 統合元へのリレーションは、統合処理で source が消える前に張る必要がある。
            event_id = self._create_event(
                session, "GroupMergeEvent", participant_id, "MERGED_BY",
                {"targetText": target_text},
            )
            session.run(
                """
                MATCH (e:GroupMergeEvent {eventId: $event_id})
                UNWIND $source_ids AS sid
                MATCH (source:Concept {conceptId: sid, participantId: $pid})
                MERGE (e)-[:MERGE_SOURCE]->(source)
                """,
                event_id=event_id, source_ids=source_concept_ids, pid=participant_id,
            )

            result = self._merge_concepts(session, participant_id, source_concept_ids, target_text)
            if result:
                session.run(
                    """
                    MATCH (e:GroupMergeEvent {eventId: $event_id})
                    MATCH (target:Concept {conceptId: $target_concept_id})
                    MERGE (e)-[:MERGE_RESULT]->(target)
                    """,
                    event_id=event_id, target_concept_id=result["concept_id"],
                )
            return result

    def delete_group(self, concept_id: str, participant_id: str) -> dict | None:
        """グループを削除する（=対象Conceptを全所属本から一括で外す）。
        削除前に本文とメンバーisbnをイベントへスナップショットしておく
        （対象ノードが消えた後もログとUndo用に情報を残すため）。"""
        with get_session() as session:
            snapshot = session.run(
                """
                MATCH (c:Concept {conceptId: $concept_id, participantId: $pid})
                OPTIONAL MATCH (c)<-[:CONCEPT {participantId: $pid}]-(b:Book)
                RETURN c.text AS text, collect(DISTINCT b.isbn) AS member_isbns
                """,
                concept_id=concept_id, pid=participant_id,
            ).single()
            if not snapshot:
                return None

            self._create_event(
                session, "GroupDeleteEvent", participant_id, "DELETED_BY",
                {"conceptId": concept_id, "text": snapshot["text"], "memberIsbns": snapshot["member_isbns"]},
            )

            session.run(
                """
                MATCH (c:Concept {conceptId: $concept_id, participantId: $pid})
                DETACH DELETE c
                """,
                concept_id=concept_id, pid=participant_id,
            )
            return {
                "concept_id": concept_id,
                "text": snapshot["text"],
                "member_isbns": snapshot["member_isbns"],
            }

    def log_group_highlight_event(self, concept_id: str, action: str, participant_id: str) -> None:
        """左パネルからのハイライト操作を記録する（表示のオン/オフ）。"""
        with get_session() as session:
            event_id = self._create_event(
                session, "GroupHighlightEvent", participant_id, "HIGHLIGHTED_BY",
                {"action": action, "conceptId": concept_id},
            )
            session.run(
                """
                MATCH (e:GroupHighlightEvent {eventId: $event_id})
                OPTIONAL MATCH (c:Concept {conceptId: $concept_id})
                FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (e)-[:HIGHLIGHTED_GROUP]->(c)
                )
                """,
                event_id=event_id, concept_id=concept_id,
            )

    def log_mode_switch_event(self, mode: str, participant_id: str) -> None:
        """通常モード⇄グルーピングモードの切り替えを記録する。"""
        with get_session() as session:
            self._create_event(
                session, "ModeSwitchEvent", participant_id, "SWITCHED_BY", {"mode": mode},
            )

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

    def set_possessed_since(self, isbn: str, participant_id: str, possessed_since: str) -> bool:
        """「所持している日数」の褪せ表現の元になる日付を手動で設定する。
        OWNS関係のプロパティなので、同じ本でも参加者ごとに別の日付を持てる。"""
        with get_session() as session:
            row = session.run(
                """
                MATCH (:Participant {participantId: $pid})-[own:OWNS]->(:Book {isbn: $isbn})
                SET own.possessedSince = date($possessed_since)
                RETURN true AS ok
                """,
                pid=participant_id,
                isbn=isbn,
                possessed_since=possessed_since,
            ).single()
            return row is not None

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
groups_from_neo4j                 = _neo4j.groups_from_neo4j
save_concept                      = _neo4j.save_concept
delete_concept_edge               = _neo4j.delete_concept_edge
update_shelf_layout_chain         = _neo4j.update_shelf_layout_chain
get_graph_overview                = _neo4j.get_graph_overview
get_book_relations                = _neo4j.get_book_relations
get_book_concepts                 = _neo4j.get_book_concepts
get_book_basic                    = _neo4j.get_book_basic
set_possessed_since               = _neo4j.set_possessed_since
save_book_impression              = _neo4j.save_book_impression
get_book_edges                    = _neo4j.get_book_edges
get_growth_stats                  = _neo4j.get_growth_stats
list_participant_groups            = _neo4j.list_participant_groups
remove_group_member                = _neo4j.remove_group_member
remove_group_members               = _neo4j.remove_group_members
add_group_members                  = _neo4j.add_group_members
rename_group                      = _neo4j.rename_group
merge_groups                      = _neo4j.merge_groups
delete_group                      = _neo4j.delete_group
log_group_highlight_event         = _neo4j.log_group_highlight_event
log_mode_switch_event             = _neo4j.log_mode_switch_event
