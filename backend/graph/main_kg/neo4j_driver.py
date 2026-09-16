from neo4j import GraphDatabase


class Neo4jDriver:
    URI  = "neo4j://127.0.0.1:7687"
    AUTH = ("neo4j", "yukito1218")

    _instance: "Neo4jDriver | None" = None

    def __init__(self):
        self._driver = GraphDatabase.driver(self.URI, auth=self.AUTH)

    @classmethod
    def get_instance(cls) -> "Neo4jDriver":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def session(self, database: str = "neo4j"):
        return self._driver.session(database=database)


# モジュールレベル互換（既存の呼び出し元を変更なしで動作させる）
def get_session():
    return Neo4jDriver.get_instance().session()
