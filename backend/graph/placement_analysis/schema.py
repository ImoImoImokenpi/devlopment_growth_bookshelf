"""本棚の物理配置分析システム（placement_analysis）用のNeo4j一意制約。

制約名はすべて pa_ 接頭辞を付け、既存の意味づけナレッジグラフ側
（graph.main_kg.neo4j_migrate、接頭辞なし）・投影スタイル分析側
（style_projection.schema、sp_ 接頭辞）・実験運用側（experiment.schema、gr_ 接頭辞）
と名前が衝突しないようにしている。
"""
from graph.main_kg.neo4j_driver import get_session

_CONSTRAINTS = [
    "CREATE CONSTRAINT pa_profile_id IF NOT EXISTS FOR (p:PlacementProfile) REQUIRE p.profile_id IS UNIQUE",
    "CREATE CONSTRAINT pa_evidence_id IF NOT EXISTS FOR (e:DesignEvidence) REQUIRE e.evidence_id IS UNIQUE",
    # Theme はLLMがあらすじから生成する内容テーマ（参加者ごと）。
    # 同じ参加者内で同じ名前のテーマは1ノードに集約する。
    "CREATE CONSTRAINT pa_theme_key IF NOT EXISTS FOR (t:Theme) REQUIRE (t.participantId, t.name) IS UNIQUE",
]


def ensure_placement_analysis_schema() -> None:
    """起動時に一度呼ぶ。制約は IF NOT EXISTS なので何度呼んでも安全。"""
    with get_session() as session:
        for statement in _CONSTRAINTS:
            session.run(statement)
