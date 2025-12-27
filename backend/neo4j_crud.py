# neo4j_crud.py
from neo4j_driver import get_session

def add_book_with_meaning(book: dict):
    with get_session() as session:
        session.run(
            """
            MERGE (b:Book {book_id: $book_id})
            SET
                b.title = $title,
                b.authors = $authors,
                b.isbn = $isbn,
                b.published_date = $published_date,
                b.description = $description,
                b.cover = $cover

            WITH b
            UNWIND $concepts AS concept_name
                MERGE (c:Concept {name: concept_name})
                MERGE (b)-[:HAS_CONCEPT]->(c)
            """,
            **book
        )

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
