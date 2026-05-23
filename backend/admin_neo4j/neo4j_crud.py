# neo4j_crud.py
from admin_neo4j.neo4j_driver import get_session

def add_book_with_meaning(book_obj, meaning_text: str = None):
    """
    SQLAlchemyのオブジェクト(MyHand/MyBookshelf) または dict を受け取り、
    Neo4jのナレッジグラフを更新・作成する。
    """
    # 1. オブジェクトと辞書の両方に対応させる
    def get_val(key, default=None):
        if isinstance(book_obj, dict):
            return book_obj.get(key, default)
        return getattr(book_obj, key, default)

    # 2. NDCから各レベルを抽出 (例: "913.6" -> L1: "9", L2: "91", L3: "913")
    ndc_full = get_val("ndc") or ""
    ndc_l1 = ndc_full[0] if len(ndc_full) >= 1 and ndc_full[0].isdigit() else None
    ndc_l2 = ndc_full[:2] if len(ndc_full) >= 2 and ndc_full[:2].isdigit() else None
    ndc_l3 = ndc_full[:3] if len(ndc_full) >= 3 and ndc_full[:3].isdigit() else None

    # 3. 著者リストの正規化
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
            // 1. 本の基本情報を保存
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

            // ── 2. NDC L1 ────────────────────────────────────
            WITH b
            FOREACH (code IN CASE WHEN $ndc_l1 IS NOT NULL THEN [$ndc_l1] ELSE [] END |
                MERGE (n:NDC {code: code}) ON CREATE SET n.level = 1
            )

            // ── 3. NDC L2 + L1→L2 リレーション ───────────────
            WITH b
            FOREACH (code IN CASE WHEN $ndc_l2 IS NOT NULL THEN [$ndc_l2] ELSE [] END |
                MERGE (n:NDC {code: code}) ON CREATE SET n.level = 2
            )
            // ✅ FOREACHの外でMATCHしてリレーション作成
            WITH b
            WHERE $ndc_l1 IS NOT NULL AND $ndc_l2 IS NOT NULL
            MATCH (n1:NDC {code: $ndc_l1})
            MATCH (n2:NDC {code: $ndc_l2})
            MERGE (n2)-[:BROADER]->(n1)

            // ── 4. NDC L3 + L2→L3 リレーション ───────────────
            WITH b
            FOREACH (code IN CASE WHEN $ndc_l3 IS NOT NULL THEN [$ndc_l3] ELSE [] END |
                MERGE (n:NDC {code: code}) ON CREATE SET n.level = 3
            )
            WITH b
            WHERE $ndc_l2 IS NOT NULL AND $ndc_l3 IS NOT NULL
            MATCH (n2:NDC {code: $ndc_l2})
            MATCH (n3:NDC {code: $ndc_l3})
            MERGE (n3)-[:BROADER]->(n2)

            // ── 5. 本とフルNDCの紐付け + 細目→目のBROADERリンク ──
            WITH b
            WHERE $ndc_full IS NOT NULL AND $ndc_full <> ""
            MERGE (nf:NDC {code: $ndc_full})
            ON CREATE SET nf.level = 4
            MERGE (b)-[:CLASSIFIED_AS]->(nf)

            // ndc_full が3桁超（細目）の場合のみ ndc_l3 とリンク
            WITH b, nf
            WHERE $ndc_l3 IS NOT NULL AND $ndc_full <> $ndc_l3
            MATCH (n3:NDC {code: $ndc_l3})
            MERGE (nf)-[:BROADER]->(n3)

            // ── 6. Meaning ────────────────────────────────────
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
            meaning=meaning_text
        )

        # ── 著者ノード + WRITTEN_BY リレーション ──────────────
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

        # ── 出版社ノード + PUBLISHED_BY リレーション ──────────
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

def groups_from_neo4j():
    with get_session() as session:
        result = session.run(
            """
            MATCH (b:Book)
            // OPTIONAL MATCH にすることで、NDCがない本も落とさない
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
                groups.append({
                    "ndc": record["ndc"],
                    "books": record["books"]
                })
        return groups

def get_shelf_books():
    """フロントエンドの棚表示用データを取得"""
    with get_session() as session:
        # SQLiteにある座標(ShelfLayout)と、Neo4jにある本情報を結合して返す設計が理想ですが、
        # Neo4j単体で座標を管理している場合は以下になります
        result = session.run(
            """
            MATCH (b:Book)
            RETURN
                b.isbn AS id,  // book_idをisbnに統一
                b.title AS title,
                b.cover AS cover,
                coalesce(b.shelfRow, 0) AS row,
                coalesce(b.shelfCol, 0) AS col
            ORDER BY row, col
            """
        )

        return {
            "rows": 5,
            "cols": 10,
            "cells": [
                {
                    "row": r["row"],
                    "col": r["col"],
                    "book": {
                        "id": r["id"],
                        "title": r["title"],
                        "cover": r["cover"]
                    }
                }
                for r in result
            ]
        }

def save_concept(isbns: list[str], meaning: str):
    """
    Concept ノードを作成し、指定した本たちを [:CONCEPT] リレーションで繋ぐ。
    同じ意味テキストが既にあれば再利用し、本との関係を追加する。
    """
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


from collections import defaultdict

def update_shelf_layout_chain(layout_data: list[dict]):
    """
    layout_data: [{"isbn": ..., "shelf_index": ..., "x_pos": ..., "order_index": ...}, ...]
    棚ごとに x_pos 順（実際の物理位置）で並べ、隣接する本の間に SHELF_NEXT リレーションを張る。
    左右スタック間の大きなギャップは隣接とみなさない。
    """
    # x_pos はフロントの (pxX - FRAME) / 1.2 で格納されている
    # 本1冊の幅は概ね 5〜80 x_pos 単位なので、100 を超えるギャップはスタック間の空白
    ADJACENCY_THRESHOLD = 100

    # 1. 棚ごとにグループ化
    rows: dict[int, list[dict]] = defaultdict(list)
    for book in layout_data:
        rows[book["shelf_index"]].append(book)

    # 2. 各棚で x_pos 順に並べ、ギャップが小さいペアだけ隣接とする
    relations = []
    for shelf_index, shelf_books in rows.items():
        shelf_books.sort(key=lambda b: b.get("x_pos", 0))

        for i in range(len(shelf_books) - 1):
            a = shelf_books[i]
            b = shelf_books[i + 1]
            gap = b.get("x_pos", 0) - a.get("x_pos", 0)
            if gap <= ADJACENCY_THRESHOLD:
                relations.append({
                    "from": a["isbn"],
                    "to":   b["isbn"],
                    "shelf_index": shelf_index,
                })

    # 3. Neo4j 更新
    with get_session() as session:
        # 既存チェーンを全削除
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