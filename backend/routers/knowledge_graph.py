from fastapi import APIRouter
from admin_neo4j.neo4j_driver import get_session

router = APIRouter(prefix="/knowledge_graph")

@router.get("/")
def get_graph():
    with get_session() as session:
        nodes_result = session.run("""
            MATCH (n)
            RETURN
                id(n)                         AS id,
                labels(n)[0]                  AS type,
                coalesce(n.isbn, '')           AS isbn,
                coalesce(n.title, '')          AS title,
                coalesce(n.authors, '')        AS authors,
                coalesce(n.publisher, '')      AS publisher,
                coalesce(n.published_year, '') AS published_year,
                coalesce(n.cover, '')          AS cover,
                coalesce(n.spine_image, '')    AS spine_image,
                coalesce(n.description, '')    AS description,
                coalesce(n.pages, 0)           AS pages,
                coalesce(n.height_mm, 0)       AS height_mm,
                coalesce(n.name, '')           AS name,
                coalesce(n.code, '')           AS code,
                coalesce(n.level, 0)           AS level,
                coalesce(n.text, '')           AS text
        """)
        nodes = [dict(r) for r in nodes_result]

        links_result = session.run("""
            MATCH (a)-[r]->(b)
            RETURN id(a) AS source, id(b) AS target, type(r) AS type
        """)
        links = [
            {"source": r["source"], "target": r["target"], "type": r["type"]}
            for r in links_result
        ]

        return {"nodes": nodes, "links": links}
