"""投影スタイル分析システム用のNeo4j一意制約。

制約名はすべて sp_ 接頭辞を付け、既存の意味づけナレッジグラフ側の制約
（graph.main_kg.neo4j_migrate._CONSTRAINTS）と名前が衝突しないようにしている。

Participant ノードの一意制約はここでは張らない。Participant は本棚配置システム
（graph.main_kg.neo4j_migrate）側と共有しており、その一意制約
（名前は "participant_id" だが対象は p.participantId）が既にある。
"""
from graph.main_kg.neo4j_driver import get_session

_CONSTRAINTS = [
    "CREATE CONSTRAINT sp_work_id IF NOT EXISTS FOR (w:Work) REQUIRE w.work_id IS UNIQUE",
    "CREATE CONSTRAINT sp_shelved_id IF NOT EXISTS FOR (s:ShelvedBook) REQUIRE s.shelved_id IS UNIQUE",
    "CREATE CONSTRAINT sp_group_id IF NOT EXISTS FOR (g:Group) REQUIRE g.group_id IS UNIQUE",
    "CREATE CONSTRAINT sp_comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.comment_id IS UNIQUE",
    "CREATE CONSTRAINT sp_profile_id IF NOT EXISTS FOR (sp:StyleProfile) REQUIRE sp.profile_id IS UNIQUE",
]


def ensure_style_projection_schema() -> None:
    """起動時に一度呼ぶ。制約は IF NOT EXISTS なので何度呼んでも安全。"""
    with get_session() as session:
        for statement in _CONSTRAINTS:
            session.run(statement)
