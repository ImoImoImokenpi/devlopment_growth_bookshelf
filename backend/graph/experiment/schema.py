"""実験運用システム（GuessRecord等）用のNeo4j一意制約。

制約名はすべて gr_ 接頭辞を付け、既存の意味づけナレッジグラフ側
（graph.main_kg.neo4j_migrate._CONSTRAINTS）・投影スタイル分析側
（style_projection.schema._CONSTRAINTS、sp_ 接頭辞）と名前が衝突しないようにしている。
"""
from graph.main_kg.neo4j_driver import get_session

_CONSTRAINTS = [
    "CREATE CONSTRAINT gr_guess_id IF NOT EXISTS FOR (g:GuessRecord) REQUIRE g.guessId IS UNIQUE",
]


def ensure_experiment_schema() -> None:
    """起動時に一度呼ぶ。制約は IF NOT EXISTS なので何度呼んでも安全。"""
    with get_session() as session:
        for statement in _CONSTRAINTS:
            session.run(statement)
