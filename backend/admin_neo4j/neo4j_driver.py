from neo4j import GraphDatabase

URI = "neo4j://127.0.0.1:7687"  # ← ここ重要
AUTH = (
    "neo4j",
    "yukito1218"
)
_driver = None

def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            URI,
            auth=AUTH,
        )
    return _driver

def get_session():
    return get_driver().session(database="neo4j")
