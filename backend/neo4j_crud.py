# neo4j_crud.py
from neo4j_driver import get_session

def add_book_with_meaning(book: dict):
    with get_session() as session:
        session.run(
            """
            MERGE (b:Book {isbn: $isbn})
            SET
                b.title = $title,
                b.authors = $authors,
                b.publisher = $publisher,
                b.published_year = $published_year,
                b.language = $language,
                b.description = $description,
                b.cover = $cover,
                b.updatedAt = datetime()

            // NDC（棚の基準）
            FOREACH (_ IN CASE
                WHEN $ndc_full IS NOT NULL AND $ndc_full <> ""
                THEN [1] ELSE [] END |
                MERGE (n:NDC {code: $ndc_full})
                SET n.level = 3
                MERGE (b)-[:CLASSIFIED_AS]->(n)
            )

            // NDC分類
            FOREACH (_ IN CASE
                WHEN $ndc_level1 IS NOT NULL THEN [1] ELSE [] END |
                MERGE (n1:NDC {code: $ndc_level1})
                SET n1.level = 1
            )

            FOREACH (_ IN CASE
                WHEN $ndc_level2 IS NOT NULL THEN [1] ELSE [] END |
                MERGE (n2:NDC {code: $ndc_level2})
                SET n2.level = 2
                MERGE (n2)-[:BROADER]->(:NDC {code: $ndc_level1})
            )

            FOREACH (_ IN CASE
                WHEN $ndc_level3 IS NOT NULL THEN [1] ELSE [] END |
                MERGE (n3:NDC {code: $ndc_level3})
                SET n3.level = 3
                MERGE (n3)-[:BROADER]->(:NDC {code: $ndc_level2})
            )

            // =========================
            // Subjects（NDLSH）
            // =========================
            FOREACH (s IN $subjects |
                MERGE (sub:Subject {name: s})
                MERGE (b)-[:HAS_SUBJECT]->(sub)
            )

            // =========================
            // Meaning（ユーザの意味付け）
            // =========================
            FOREACH (_ IN CASE
                WHEN $meaning IS NOT NULL AND $meaning <> ""
                THEN [1] ELSE [] END |
                CREATE (m:Meaning {
                    text: $meaning,
                    createdAt: datetime()
                })
                MERGE (b)-[:HAS_MEANING]->(m)
            )
            """,
            isbn=book.get("isbn"),
            title=book.get("title"),
            authors=", ".join(book.get("authors", [])),
            publisher=book.get("publisher"),
            published_year=book.get("published_year"),
            language=book.get("language"),
            description=book.get("description"),
            cover=book.get("cover"),

            ndc_full=book.get("ndc", {}).get("ndc_full"),
            ndc_level1=book.get("ndc", {}).get("ndc_level1"),
            ndc_level2=book.get("ndc", {}).get("ndc_level2"),
            ndc_level3=book.get("ndc", {}).get("ndc_level3"),

            subjects=book.get("subjects", []),
        )

def groups_from_neo4j():
    with get_session() as session:
        result = session.run(
            """
            MATCH (b:Book)-[:CLASSIFIED_AS]->(n:NDC)
            WHERE n.level = 3
            WITH n.code AS ndc, b
            ORDER BY ndc, b.title

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
            books = record["books"]
            if books:
                groups.append({
                    "ndc": record["ndc"],
                    "books": books
                })

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
