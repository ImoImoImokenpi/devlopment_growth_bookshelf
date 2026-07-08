# neo4j_crud.py
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

    # ============================================================
    # 書籍登録（既存）
    # ============================================================

    def add_book_with_meaning(self, book_obj, meaning_text: str = None):
        """
        SQLAlchemyのオブジェクト(MyHand/MyBookshelf) または dict を受け取り、
        Neo4jのナレッジグラフを更新・作成する。
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
                CREATE (m:Meaning {text: $meaning, createdAt: datetime()})
                MERGE (b)-[:HAS_MEANING]->(m)
                """,
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

    # ============================================================
    # NDCグルーピング（既存）
    # ============================================================

    def groups_from_neo4j(self):
        with get_session() as session:
            result = session.run(
                """
                MATCH (b:Book)
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
                """
            )
            groups = []
            for record in result:
                if record["books"]:
                    groups.append({"ndc": record["ndc"], "books": record["books"]})
            return groups

    # ============================================================
    # Concept（既存）
    # ============================================================

    def save_concept(self, isbns: list[str], meaning: str):
        with get_session() as session:
            session.run(
                """
                MERGE (c:Concept {text: $meaning})
                ON CREATE SET c.createdAt = datetime()
                WITH c
                UNWIND $isbns AS isbn
                MATCH (b:Book {isbn: isbn})
                MERGE (b)-[:CONCEPT]->(c)
                """,
                meaning=meaning,
                isbns=isbns,
            )

    # ============================================================
    # 棚レイアウト更新（既存 + ShelfPosition を追加）
    #
    # TTL対応:
    #   bs:ShelfPosition → (:ShelfPosition {posId, shelfIndex, columnIndex,
    #                                        xPos, isEdge, isIsolated, memoryWeight})
    #   bs:locates       → [:LOCATES]
    #   bs:adjacentTo    → [:SHELF_NEXT]  ← 既存リレーションをそのまま流用
    # ============================================================

    def update_shelf_layout_chain(self, layout_data: list[dict]):
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
          2. ShelfPosition → Book の LOCATES リレーションを張る
          3. 隣接 Book 間に SHELF_NEXT リレーションを張る（既存ロジック）
          4. PlacementEvent を自動記録する（変遷ログ）
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

        # ── Neo4j 更新 ────────────────────────────────────────────
        with get_session() as session:

            # 1. ShelfPosition ノードを MERGE・memoryWeight をセット
            #    LOCATES リレーションも同時に張る
            for item in enriched:
                shelf_index  = item["shelf_index"]
                column_index = item["order_index"]
                is_edge      = item["is_edge"]
                is_isolated  = item["is_isolated"]
                pos_id       = f"pos_r{shelf_index}_c{column_index}"
                memory_weight = self._calc_memory_weight(shelf_index, is_edge, is_isolated)

                session.run(
                    """
                    // bs:ShelfPosition ノード
                    MERGE (pos:ShelfPosition {posId: $pos_id})
                    SET
                        pos.shelfIndex   = $shelf_index,
                        pos.columnIndex  = $column_index,
                        pos.xPos         = $x_pos,
                        pos.isEdge       = $is_edge,
                        pos.isIsolated   = $is_isolated,
                        pos.memoryWeight = $memory_weight,
                        pos.updatedAt    = datetime()

                    // bs:locates → [:LOCATES]
                    WITH pos
                    MATCH (b:Book {isbn: $isbn})
                    MERGE (pos)-[:LOCATES]->(b)
                    """,
                    pos_id=pos_id,
                    shelf_index=shelf_index,
                    column_index=column_index,
                    x_pos=item.get("x_pos", 0.0),
                    is_edge=is_edge,
                    is_isolated=is_isolated,
                    memory_weight=memory_weight,
                    isbn=item["isbn"],
                )

            # 2. SHELF_NEXT を全削除して張り直す（既存ロジックをそのまま維持）
            #    bs:adjacentTo に対応
            session.run("MATCH ()-[r:SHELF_NEXT]-() DELETE r")
            if relations:
                session.run(
                    """
                    UNWIND $relations AS rel
                    MATCH (a:Book {isbn: rel.from})
                    MATCH (b:Book {isbn: rel.to})
                    MERGE (a)-[:SHELF_NEXT {shelf_index: rel.shelf_index}]->(b)
                    """,
                    relations=relations,
                )

            # 3. PlacementEvent を記録（bs:PlacementEvent / 変遷ログ）
            #    既存の ShelfPosition と比較して「移動」があった場合のみ
            #    previousPosition を記録する
            for item in enriched:
                isbn         = item["isbn"]
                pos_id       = f"pos_r{item['shelf_index']}_c{item['order_index']}"
                event_id     = f"evt_{isbn}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

                # 直前の配置位置を取得（移動検出）
                prev = session.run(
                    """
                    MATCH (prev_pos:ShelfPosition)-[:LOCATES]->(b:Book {isbn: $isbn})
                    WHERE prev_pos.posId <> $pos_id
                    RETURN prev_pos.posId AS prevPosId
                    LIMIT 1
                    """,
                    isbn=isbn,
                    pos_id=pos_id,
                ).single()

                prev_pos_id = prev["prevPosId"] if prev else None

                session.run(
                    """
                    // bs:PlacementEvent ノード
                    CREATE (e:PlacementEvent {
                        eventId:   $event_id,
                        timestamp: datetime(),
                        createdAt: datetime()
                    })

                    // bs:placedBook → [:PLACED_BOOK]
                    WITH e
                    MATCH (b:Book {isbn: $isbn})
                    MERGE (e)-[:PLACED_BOOK]->(b)

                    // bs:placedAt → [:PLACED_AT]
                    WITH e
                    MATCH (pos:ShelfPosition {posId: $pos_id})
                    MERGE (e)-[:PLACED_AT]->(pos)
                    """,
                    event_id=event_id,
                    isbn=isbn,
                    pos_id=pos_id,
                )

                # bs:previousPosition → [:PREVIOUS_POSITION]（移動の場合のみ）
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

    # ============================================================
    # 分析クエリ（研究目的：知識体系の広がりと成長の分析）
    # ============================================================

    def query_high_memory_books(self, threshold: float = 0.8) -> list[dict]:
        """
        memoryWeight が高い位置にある本を取得。
        「重要視されている知識」の分析クエリ。
        """
        with get_session() as session:
            result = session.run(
                """
                MATCH (pos:ShelfPosition)-[:LOCATES]->(b:Book)
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
                threshold=threshold,
            )
            return [dict(r) for r in result]

    def query_placement_history(self, isbn: str) -> list[dict]:
        """
        1冊の本の配置変遷履歴を時系列で取得。
        「知識成長の追跡」クエリ。
        """
        with get_session() as session:
            result = session.run(
                """
                MATCH (e:PlacementEvent)-[:PLACED_BOOK]->(b:Book {isbn: $isbn})
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
                isbn=isbn,
            )
            return [dict(r) for r in result]

    def query_knowledge_growth(self, user_id: str = None) -> list[dict]:
        """
        NDC分類の広がりを集計。
        本棚の変遷から知識体系の成長を分析する。
        user_id を渡すと特定ユーザーに絞る（省略で全体集計）。
        """
        with get_session() as session:
            if user_id:
                result = session.run(
                    """
                    MATCH (e:PlacementEvent)-[:PLACED_BY]->(u:User {userId: $user_id})
                    MATCH (e)-[:PLACED_BOOK]->(b:Book)-[:CLASSIFIED_AS]->(n:NDC)
                    WHERE n.level = 1
                    RETURN
                        n.code                     AS ndc_l1,
                        count(DISTINCT b.isbn)     AS book_count,
                        min(e.timestamp)           AS first_placed,
                        max(e.timestamp)           AS last_placed
                    ORDER BY ndc_l1
                    """,
                    user_id=user_id,
                )
            else:
                result = session.run(
                    """
                    MATCH (b:Book)-[:CLASSIFIED_AS]->(n:NDC)
                    WHERE n.level = 1
                    RETURN
                        n.code                 AS ndc_l1,
                        count(DISTINCT b.isbn) AS book_count
                    ORDER BY ndc_l1
                    """
                )
            return [dict(r) for r in result]

    def get_graph_overview(self, shelf_isbns: list[str] | None = None) -> dict:
        """
        ナレッジグラフ全体を俯瞰するための統計スナップショット。
        AIによる提案生成の入力として使う。
        shelf_isbns を渡すと、book_catalog はその本棚に現在並んでいる本だけに絞り込む
        （AI提案が棚に無い本を指してしまい、ハイライトと連動できなくなるのを防ぐため）。
        """
        with get_session() as session:
            total_books = session.run(
                "MATCH (b:Book) RETURN count(b) AS total"
            ).single()["total"]

            ndc_distribution = [
                dict(r) for r in session.run(
                    """
                    MATCH (b:Book)-[:CLASSIFIED_AS]->(n:NDC)
                    WITH substring(n.code, 0, 1) AS ndc_l1, b
                    RETURN
                        ndc_l1,
                        count(DISTINCT b)              AS book_count,
                        collect(DISTINCT b.title)[0..3] AS sample_titles
                    ORDER BY book_count DESC
                    """
                )
            ]

            concept_clusters = [
                dict(r) for r in session.run(
                    """
                    MATCH (c:Concept)<-[:CONCEPT]-(b:Book)
                    WITH c, collect(DISTINCT b.title) AS titles, count(DISTINCT b) AS book_count
                    WHERE book_count >= 2
                    RETURN c.text AS concept, titles, book_count
                    ORDER BY book_count DESC
                    LIMIT 10
                    """
                )
            ]

            favorite_authors = [
                dict(r) for r in session.run(
                    """
                    MATCH (b:Book)-[:WRITTEN_BY]->(a:Author)
                    WITH a, count(DISTINCT b) AS book_count, collect(DISTINCT b.title) AS titles
                    WHERE book_count >= 2
                    RETURN a.name AS author, book_count, titles
                    ORDER BY book_count DESC
                    LIMIT 10
                    """
                )
            ]

            isolated_books = [
                dict(r) for r in session.run(
                    """
                    MATCH (b:Book)
                    WHERE NOT (b)-[:CONCEPT]-() AND NOT (b)-[:SHELF_NEXT]-()
                    RETURN b.title AS title, b.isbn AS isbn,
                           coalesce(b.description, '') AS description
                    LIMIT 15
                    """
                )
            ]

            book_meanings = [
                dict(r) for r in session.run(
                    """
                    MATCH (b:Book)-[:HAS_MEANING]->(m:Meaning)
                    RETURN b.title AS title, m.text AS meaning
                    ORDER BY m.createdAt DESC
                    LIMIT 20
                    """
                )
            ]

            book_catalog = [
                dict(r) for r in session.run(
                    """
                    MATCH (b:Book)
                    WHERE $shelf_isbns IS NULL OR b.isbn IN $shelf_isbns
                    RETURN b.isbn AS isbn,
                           b.title AS title,
                           coalesce(b.authors, '')     AS authors,
                           coalesce(b.publisher, '')   AS publisher,
                           coalesce(b.description, '') AS description
                    ORDER BY b.title
                    """,
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
# モジュールレベル互換（既存の呼び出し元を変更なしで動作させる）
# ============================================================

_neo4j = BookshelfNeo4j()

add_book_with_meaning      = _neo4j.add_book_with_meaning
groups_from_neo4j          = _neo4j.groups_from_neo4j
save_concept               = _neo4j.save_concept
update_shelf_layout_chain  = _neo4j.update_shelf_layout_chain
query_high_memory_books    = _neo4j.query_high_memory_books
query_placement_history    = _neo4j.query_placement_history
query_knowledge_growth     = _neo4j.query_knowledge_growth
get_graph_overview         = _neo4j.get_graph_overview
