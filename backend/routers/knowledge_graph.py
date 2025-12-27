from fastapi import APIRouter
from neo4j_driver import get_session

router = APIRouter(prefix="/knowledge_graph")

@router.get("/")
def get_graph():
    with get_session() as session:
        result = session.run("""
        MATCH (n)
        OPTIONAL MATCH (n)-[r]->(m)
        RETURN
            collect(DISTINCT {
            id: id(n),
            label: labels(n)[0],
            title: coalesce(n.title, n.name),
            type: labels(n)[0]
            }) AS nodes,
            collect(DISTINCT {
            source: id(startNode(r)),
            target: id(endNode(r)),
            type: type(r)
            }) AS links
        """)
        record = result.single()
        return {
            "nodes": record["nodes"],
            "links": record["links"]
        }
