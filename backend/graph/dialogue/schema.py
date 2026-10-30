"""本棚対話（dialogue）用のNeo4j一意制約。

制約名は dl_ 接頭辞を付け、ほかのサブシステム（接頭辞なし・sp_・gr_・pa_）と
名前が衝突しないようにしている。
"""
from graph.main_kg.neo4j_driver import get_session

_CONSTRAINTS = [
    "CREATE CONSTRAINT dl_session_id IF NOT EXISTS FOR (s:DialogueSession) REQUIRE s.sessionId IS UNIQUE",
    "CREATE CONSTRAINT dl_turn_id IF NOT EXISTS FOR (t:DialogueTurn) REQUIRE t.turnId IS UNIQUE",
    "CREATE CONSTRAINT dl_proposal_id IF NOT EXISTS FOR (m:MeaningProposal) REQUIRE m.proposalId IS UNIQUE",
]


def ensure_dialogue_schema() -> None:
    """起動時に一度呼ぶ。制約は IF NOT EXISTS なので何度呼んでも安全。"""
    with get_session() as session:
        for statement in _CONSTRAINTS:
            session.run(statement)
