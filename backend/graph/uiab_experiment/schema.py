"""新本棚UI(自由配置) vs 旧本棚UI(グリッド) 比較実験用のNeo4j一意制約。

「投影のズレ」研究(graph.main_kg他)とは別の参加者プール・別の研究なので、
Participant/Observerは既存の :Participant ラベルを再利用せず、
:UiabParticipant / :UiabObserver という別ラベルにする（IDの偶然の衝突で
2つの研究のデータが混ざる事故を避けるため）。書誌データ(:Book)だけは
客観データなので main_kg と共有する。

制約名はすべて uiab_ 接頭辞を付け、他システム（sp_/pa_/gr_ 接頭辞）と
名前が衝突しないようにしている。
"""
from graph.main_kg.neo4j_driver import get_session

_CONSTRAINTS = [
    "CREATE CONSTRAINT uiab_participant_id IF NOT EXISTS FOR (p:UiabParticipant) REQUIRE p.participantId IS UNIQUE",
    "CREATE CONSTRAINT uiab_observer_id    IF NOT EXISTS FOR (o:UiabObserver)    REQUIRE o.observerId IS UNIQUE",
    "CREATE CONSTRAINT uiab_group_id       IF NOT EXISTS FOR (g:UiabGroup)       REQUIRE g.groupId IS UNIQUE",
    "CREATE CONSTRAINT uiab_impression_id  IF NOT EXISTS FOR (i:UiabImpression)  REQUIRE i.impressionId IS UNIQUE",
    "CREATE CONSTRAINT uiab_position_id    IF NOT EXISTS FOR (s:UiabShelfPosition) REQUIRE s.posId IS UNIQUE",
    "CREATE CONSTRAINT uiab_event_id       IF NOT EXISTS FOR (e:UiabEvent)       REQUIRE e.eventId IS UNIQUE",
    "CREATE CONSTRAINT uiab_bigfive_key    IF NOT EXISTS FOR (b:UiabBigFiveResponse) REQUIRE (b.participantId, b.itemKey) IS UNIQUE",
    "CREATE CONSTRAINT uiab_assignment_key IF NOT EXISTS FOR (a:UiabObserverAssignment) REQUIRE (a.observerId, a.trialIndex) IS UNIQUE",
    "CREATE CONSTRAINT uiab_guess_id       IF NOT EXISTS FOR (g:UiabObserverGuess) REQUIRE g.guessId IS UNIQUE",
]


def ensure_uiab_experiment_schema() -> None:
    """起動時に一度呼ぶ。制約は IF NOT EXISTS なので何度呼んでも安全。"""
    with get_session() as session:
        for statement in _CONSTRAINTS:
            session.run(statement)
