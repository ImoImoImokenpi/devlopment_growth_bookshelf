# neo4j_crud.py
from neo4j_driver import get_session

def add_book_with_meaning(book: dict):
    with get_session() as session:
        session.run(
            """
            MERGE (b:Book {book_id: $book_id})
            SET
                b.title = $title,
                b.subtitle = $subtitle,
                b.authors = $authors,
                b.publisher = $publisher,
                b.publishedDate = $publishedDate,
                b.description = $description,
                b.printType = $printType,
                b.language = $language,
                b.cover = $cover,
                b.categories = $categories,   // ← 書誌情報としてのみ保持
                b.updatedAt = datetime()

            // ===== mainCategory（棚の基準）=====
            FOREACH (_ IN CASE
                WHEN $mainCategory IS NOT NULL AND $mainCategory <> ""
                THEN [1] ELSE [] END |
                MERGE (cat:Category {name: $mainCategory})
                MERGE (b)-[:HAS_MAIN_CATEGORY]->(cat)
            )
            """,
            **book
        )

def groups_from_neo4j():
    with get_session() as session:
        result = session.run(
            """
            MATCH (b:Book)
            OPTIONAL MATCH (b)-[:HAS_MAIN_CATEGORY]->(cat:Category)
            WITH
                coalesce(cat.name, "Uncategorized") AS category,
                b
            ORDER BY category, b.title

            RETURN
                category,
                collect({
                    book_id: b.book_id,
                    title: b.title,
                    cover: b.cover
                }) AS books
            """
        )

        groups = []

        for record in result:
            books = record["books"]
            if books:
                groups.append(books)

        return groups


def get_shelf_books():
    with get_session() as session:
        result = session.run(
            """
                MATCH (b:Book)
                RETURN
                b.book_id AS id,
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
