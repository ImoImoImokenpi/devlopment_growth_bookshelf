"""Neo4j 側の起動時マイグレーション。

単一ユーザ前提で作られたグラフを、被験者ごとに分離されたグラフへ移行する。

移行の考え方:
  - 客観データ（Book / Author / Publisher / NDC）は全被験者で共有する。
    同じ本を複数人が持ち込んでもノードは1つでよい。
  - 主観データ（Concept / Impression / ShelfPosition / SHELF_NEXT /
    PlacementEvent / Discovery）は participantId で完全に分離する。
  - 「誰の蔵書か」は (:Participant)-[:OWNS]->(:Book) で表す。
    読み出しは必ずこの OWNS を経由させ、他人の本が混ざらないようにする。

既存データはすべて既定の被験者 (P00) のものとして扱う。
"""
import logging

from admin_neo4j.neo4j_driver import get_session
from participant import DEFAULT_PARTICIPANT_ID

logger = logging.getLogger(__name__)

PARTICIPANT_SCOPE_MIGRATION = "participant_scope_v1"

_CONSTRAINTS = [
    "CREATE CONSTRAINT participant_id IF NOT EXISTS FOR (p:Participant) REQUIRE p.participantId IS UNIQUE",
    "CREATE CONSTRAINT book_isbn IF NOT EXISTS FOR (b:Book) REQUIRE b.isbn IS UNIQUE",
    "CREATE CONSTRAINT shelfpos_id IF NOT EXISTS FOR (s:ShelfPosition) REQUIRE s.posId IS UNIQUE",
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.conceptId IS UNIQUE",
    "CREATE CONSTRAINT impression_id IF NOT EXISTS FOR (i:Impression) REQUIRE i.impressionId IS UNIQUE",
    "CREATE CONSTRAINT discovery_id IF NOT EXISTS FOR (d:Discovery) REQUIRE d.discoveryId IS UNIQUE",
    "CREATE INDEX concept_participant IF NOT EXISTS FOR (c:Concept) ON (c.participantId)",
    "CREATE INDEX shelfpos_participant IF NOT EXISTS FOR (s:ShelfPosition) ON (s.participantId)",
    "CREATE INDEX discovery_participant IF NOT EXISTS FOR (d:Discovery) ON (d.participantId)",
    "CREATE INDEX placement_participant IF NOT EXISTS FOR (e:PlacementEvent) ON (e.participantId)",
]

# participantId を持たない既存ノード／リレーションに既定の被験者を刻む。
# どれも「まだ付いていないものだけ」を対象にするので何度流しても安全。
_STAMP_QUERIES = [
    # 意味づけ（Concept）── 被験者ごとに分ける。
    # 従来は text だけで MERGE していたため、同じ文言を書いた別人の意味づけが
    # 1ノードに融合してしまっていた。conceptId を主キーにして分離する。
    """
    MATCH (c:Concept) WHERE c.participantId IS NULL
    SET c.participantId = $pid,
        c.conceptId     = coalesce(c.conceptId, randomUUID()),
        c.createdAt     = coalesce(c.createdAt, datetime())
    """,
    # 意味づけリレーション ── 設計書3.2のエッジ属性を後付けする。
    # 既存分はユーザーが明示的に入力したものなので confirmed / user_initiated 扱い。
    """
    MATCH (:Book)-[r:CONCEPT]->(:Concept) WHERE r.participantId IS NULL
    SET r.participantId    = $pid,
        r.edgeId           = coalesce(r.edgeId, randomUUID()),
        r.origin           = coalesce(r.origin, 'user_initiated'),
        r.confidence       = coalesce(r.confidence, 'confirmed'),
        r.strength         = coalesce(r.strength, 1.0),
        r.reinforceCount   = coalesce(r.reinforceCount, 1),
        r.createdAt        = coalesce(r.createdAt, datetime()),
        r.lastReinforcedAt = coalesce(r.lastReinforcedAt, datetime())
    """,
    # 棚の位置 ── posId が 'pos_r0_c0' のように全被験者で衝突する形だったので、
    # 被験者IDを前置した形式に書き換える。
    """
    MATCH (pos:ShelfPosition) WHERE pos.participantId IS NULL
    SET pos.participantId = $pid,
        pos.posId = $pid + ':r' + toString(coalesce(pos.shelfIndex, 0))
                         + 'c' + toString(coalesce(pos.columnIndex, 0))
    """,
    # 棚での隣接 ── 共起回数を持たせる（従来は毎回消して張り直していた）
    """
    MATCH (:Book)-[r:SHELF_NEXT]->(:Book) WHERE r.participantId IS NULL
    SET r.participantId     = $pid,
        r.coOccurrenceCount = coalesce(r.coOccurrenceCount, 1),
        r.firstSeenAt       = coalesce(r.firstSeenAt, datetime()),
        r.lastSeenAt        = coalesce(r.lastSeenAt, datetime())
    """,
    # 配置イベント
    """
    MATCH (e:PlacementEvent) WHERE e.participantId IS NULL
    SET e.participantId = $pid
    """,
    # 旧 Meaning ノード（add_book_with_meaning が作っていたもの）
    """
    MATCH (m:Meaning) WHERE m.participantId IS NULL
    SET m.participantId = $pid
    """,
]

# 感想を Book のプロパティから Impression ノードへ移す。
# プロパティ上書きだと履歴が残らず、しかも Book は全被験者で共有なので
# 他人の感想が見えてしまう。REMOVE するので再実行しても二重にならない。
_IMPRESSION_MIGRATION = """
MATCH (b:Book)
WHERE b.impression IS NOT NULL AND b.impression <> ''
MERGE (b)-[:HAS_IMPRESSION]->(i:Impression {participantId: $pid, text: b.impression})
ON CREATE SET i.impressionId = randomUUID(), i.createdAt = datetime()
REMOVE b.impression
RETURN count(*) AS moved
"""

# 既存の本はすべて既定の被験者の蔵書とみなす。
# 一度きりの処理なので、マイグレーション記録ノードで再実行を防ぐ。
_BACKFILL_OWNERSHIP = """
MATCH (p:Participant {participantId: $pid})
MATCH (b:Book)
MERGE (p)-[:OWNS]->(b)
RETURN count(*) AS owned
"""


def _already_applied(session, name: str) -> bool:
    row = session.run(
        "MATCH (m:_Migration {name: $name}) RETURN m.appliedAt AS at", name=name
    ).single()
    return row is not None


def _mark_applied(session, name: str) -> None:
    session.run(
        "MERGE (m:_Migration {name: $name}) ON CREATE SET m.appliedAt = datetime()",
        name=name,
    )


def run_neo4j_migrations(participant_id: str = DEFAULT_PARTICIPANT_ID) -> None:
    """起動時に呼ぶ。Neo4j に繋がらない場合は警告だけ出して起動を止めない
    （開発中に Neo4j を落としていても API サーバは立ち上がってほしいため）。"""
    try:
        with get_session() as session:
            for statement in _CONSTRAINTS:
                try:
                    session.run(statement)
                except Exception as e:
                    # 既存データが制約に違反している場合はここで落ちる。
                    # 制約が無くても動作はするので、警告に留めて先へ進む。
                    logger.warning("Neo4j制約の作成をスキップしました (%s): %s", statement.split()[2], e)

            session.run(
                "MERGE (p:Participant {participantId: $pid}) "
                "ON CREATE SET p.createdAt = datetime()",
                pid=participant_id,
            )

            for statement in _STAMP_QUERIES:
                session.run(statement, pid=participant_id)

            moved = session.run(_IMPRESSION_MIGRATION, pid=participant_id).single()
            if moved and moved["moved"]:
                logger.info("Neo4j migration: 感想 %d 件を Impression ノードへ移しました", moved["moved"])

            if not _already_applied(session, PARTICIPANT_SCOPE_MIGRATION):
                owned = session.run(_BACKFILL_OWNERSHIP, pid=participant_id).single()
                _mark_applied(session, PARTICIPANT_SCOPE_MIGRATION)
                logger.info(
                    "Neo4j migration: 既存の %d 冊を %s の蔵書として登録しました",
                    owned["owned"] if owned else 0,
                    participant_id,
                )
    except Exception as e:
        logger.warning("Neo4jのマイグレーションを実行できませんでした（Neo4jは起動していますか）: %s", e)
