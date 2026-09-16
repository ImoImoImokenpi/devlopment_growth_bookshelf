"""本棚配置データ（座標・グループ所属・コメント）の投入API。

すべて upsert 方式（本の再配置・グループ変更の再送に対応）。
座標を伴う投入のたびに、その参加者のADJACENT_TOエッジを自動で再計算する。

想定する入力JSON:
{
  "participant_id": "p001",
  "role": "owner",                      # "owner" | "viewer"
  "groups": [
    {"group_id": "g1", "name": "SF", "created_by": "manual", "parent_group_id": null},
    {"group_id": "g2", "name": "ハードSF", "created_by": "manual", "parent_group_id": "g1"}
  ],
  "books": [
    {
      "shelved_id": "s001",
      "x": 12.3, "y": 4.5, "shelf_id": "shelf_1", "condition": "proposed_ui",
      "work": {"work_id": "9784...", "title": "...", "author": "...",
               "published_year": 2020, "genre": "SF"},
      "group_ids": ["g2"],
      "comments": [{"comment_id": "c001", "text": "面白かった", "created_at": "2026-08-01T10:00:00"}]
    },
    ...
  ]
}

comment_id を省略した場合はサーバ側でUUIDを発行する（既存コメントを編集したい
場合は前回返された comment_id を含めて送り直せば上書きになる）。
"""
from __future__ import annotations

import itertools
import math
import uuid
from datetime import datetime

from graph.main_kg.neo4j_driver import get_session
from graph.style_projection.groups import recompute_group_depths

DEFAULT_K_NEIGHBORS = 3


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()


def _ensure_participant(session, participant_id: str, role: str | None) -> None:
    session.run(
        """
        MERGE (p:Participant {participantId: $pid})
        ON CREATE SET p.role = $role
        ON MATCH SET p.role = coalesce($role, p.role)
        """,
        pid=participant_id,
        role=role,
    )


def _upsert_groups(session, participant_id: str, groups: list[dict]) -> None:
    if not groups:
        return

    session.run(
        """
        UNWIND $groups AS grp
        MERGE (g:Group {group_id: grp.group_id})
        SET g.name = grp.name, g.created_by = grp.created_by
        WITH g
        MATCH (p:Participant {participantId: $pid})
        MERGE (p)-[:CREATED]->(g)
        """,
        groups=[
            {"group_id": g["group_id"], "name": g.get("name"), "created_by": g.get("created_by", "manual")}
            for g in groups
        ],
        pid=participant_id,
    )

    child_edges = [
        {"parent": g["parent_group_id"], "child": g["group_id"]}
        for g in groups
        if g.get("parent_group_id")
    ]
    if child_edges:
        session.run(
            """
            UNWIND $edges AS e
            MERGE (parent:Group {group_id: e.parent})
            MERGE (child:Group {group_id: e.child})
            MERGE (parent)-[:HAS_SUBGROUP]->(child)
            """,
            edges=child_edges,
        )


def _upsert_book(session, participant_id: str, book: dict) -> None:
    work = book.get("work") or {}
    session.run(
        """
        MERGE (w:Work {work_id: $work_id})
        SET w.title = $title, w.author = $author,
            w.published_year = $published_year, w.genre = $genre

        WITH w
        MERGE (s:ShelvedBook {shelved_id: $shelved_id})
        SET s.x = $x, s.y = $y, s.shelf_id = $shelf_id, s.condition = $condition
        MERGE (s)-[:INSTANCE_OF]->(w)

        WITH s
        MATCH (p:Participant {participantId: $pid})
        MERGE (p)-[:OWNS]->(s)
        """,
        work_id=work.get("work_id"),
        title=work.get("title"),
        author=work.get("author"),
        published_year=work.get("published_year"),
        genre=work.get("genre"),
        shelved_id=book["shelved_id"],
        x=book.get("x", 0.0),
        y=book.get("y", 0.0),
        shelf_id=book.get("shelf_id"),
        condition=book.get("condition"),
        pid=participant_id,
    )

    group_ids = book.get("group_ids") or []
    session.run(
        """
        MATCH (s:ShelvedBook {shelved_id: $shelved_id})
        OPTIONAL MATCH (s)-[old:BELONGS_TO]->(og:Group)
        WHERE NOT og.group_id IN $group_ids
        DELETE old
        WITH DISTINCT s
        UNWIND $group_ids AS gid
        MATCH (g:Group {group_id: gid})
        MERGE (s)-[:BELONGS_TO]->(g)
        """,
        shelved_id=book["shelved_id"],
        group_ids=group_ids,
    )

    comments = book.get("comments") or []
    if comments:
        session.run(
            """
            MATCH (s:ShelvedBook {shelved_id: $shelved_id})
            UNWIND $comments AS c
            MERGE (cm:Comment {comment_id: c.comment_id})
            SET cm.text = c.text, cm.created_at = c.created_at
            MERGE (s)-[:HAS_COMMENT]->(cm)
            """,
            shelved_id=book["shelved_id"],
            comments=[
                {
                    "comment_id": c.get("comment_id") or str(uuid.uuid4()),
                    "text": c.get("text", ""),
                    "created_at": _parse_datetime(c.get("created_at")),
                }
                for c in comments
            ],
        )


def _distance(a: dict, b: dict) -> float:
    return math.hypot((a["x"] or 0.0) - (b["x"] or 0.0), (a["y"] or 0.0) - (b["y"] or 0.0))


def _compute_adjacency_pairs(
    books: list[dict],
    mode: str,
    k_neighbors: int,
    distance_threshold: float | None,
) -> list[dict]:
    """本の座標一覧から隣接ペアを計算する。ADJACENT_TOは無向として扱うため、
    shelved_id の昇順で (a, b) を一意に1本だけ生成する。"""
    pairs: dict[tuple[str, str], float] = {}

    def _add(id_a: str, id_b: str, dist: float) -> None:
        key = (id_a, id_b) if id_a < id_b else (id_b, id_a)
        pairs[key] = dist

    if mode == "threshold":
        if distance_threshold is None:
            raise ValueError("distance_threshold は threshold モードで必須です")
        for a, b in itertools.combinations(books, 2):
            dist = _distance(a, b)
            if dist <= distance_threshold:
                _add(a["shelved_id"], b["shelved_id"], dist)
    elif mode == "knn":
        for a in books:
            others = sorted(
                (b for b in books if b["shelved_id"] != a["shelved_id"]),
                key=lambda b: _distance(a, b),
            )
            for b in others[:k_neighbors]:
                _add(a["shelved_id"], b["shelved_id"], _distance(a, b))
    else:
        raise ValueError(f"未知の adjacency_mode: {mode}")

    return [{"a": a, "b": b, "distance": dist} for (a, b), dist in pairs.items()]


def recompute_adjacency(
    session,
    participant_id: str,
    mode: str = "knn",
    k_neighbors: int = DEFAULT_K_NEIGHBORS,
    distance_threshold: float | None = None,
    explicit_pairs: list[dict] | None = None,
) -> int:
    """参加者の現在の全ShelvedBookに対して、ADJACENT_TOエッジを完全に張り直す。
    戻り値は生成したエッジ数。

    mode="explicit": 座標からの再計算をせず、explicit_pairs（[{"a", "b", "distance"}, ...]）
    をそのまま使う。本棚UI側（graph.main_kg.neo4j_crud.update_shelf_layout_chain）が
    実際の背表紙の隙間から既に確定している隣接(SHELF_NEXT)をそのまま反映したい
    ときに使う経路（bookshelf_bridge.sync_from_bookshelf）。これが無いと、
    「本棚で隣か」の定義がKNN座標ベースのものと二重に存在してしまう。"""
    session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(a:ShelvedBook)
        MATCH (a)-[r:ADJACENT_TO]-(b:ShelvedBook)<-[:OWNS]-(:Participant {participantId: $pid})
        DELETE r
        """,
        pid=participant_id,
    )

    if mode == "explicit":
        pairs = explicit_pairs or []
    else:
        books = [
            dict(r)
            for r in session.run(
                """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)
                RETURN s.shelved_id AS shelved_id, s.x AS x, s.y AS y
                """,
                pid=participant_id,
            )
        ]
        if len(books) < 2:
            return 0
        pairs = _compute_adjacency_pairs(books, mode, k_neighbors, distance_threshold)

    if pairs:
        session.run(
            """
            UNWIND $pairs AS pair
            MATCH (a:ShelvedBook {shelved_id: pair.a})
            MATCH (b:ShelvedBook {shelved_id: pair.b})
            MERGE (a)-[r:ADJACENT_TO]->(b)
            SET r.distance = pair.distance
            """,
            pairs=pairs,
        )
    return len(pairs)


def ingest_shelf_snapshot(
    payload: dict,
    adjacency_mode: str = "knn",
    k_neighbors: int = DEFAULT_K_NEIGHBORS,
    distance_threshold: float | None = None,
    explicit_adjacency_pairs: list[dict] | None = None,
) -> dict:
    """本棚配置データ一式をupsertする。「配置完了イベント」のタイミングで
    呼ぶことを想定（構造指標のバッチ再計算はこの後 metrics.save_style_profile を
    別途呼ぶ）。

    adjacency_mode="explicit" のとき、座標からの再計算をせず
    explicit_adjacency_pairsをそのまま隣接関係として使う
    （recompute_adjacencyのmode="explicit"と同じ用途。呼び出し元は
    bookshelf_bridge.sync_from_bookshelf）。"""
    participant_id = payload.get("participant_id")
    if not participant_id:
        raise ValueError("participant_id は必須です")

    books = payload.get("books") or []
    groups = payload.get("groups") or []

    with get_session() as session:
        _ensure_participant(session, participant_id, payload.get("role"))
        _upsert_groups(session, participant_id, groups)
        for book in books:
            _upsert_book(session, participant_id, book)

        adjacent_edges = recompute_adjacency(
            session, participant_id,
            mode=adjacency_mode, k_neighbors=k_neighbors, distance_threshold=distance_threshold,
            explicit_pairs=explicit_adjacency_pairs,
        )

    updated_groups = recompute_group_depths(participant_id)

    return {
        "participant_id": participant_id,
        "books_upserted": len(books),
        "groups_upserted": len(groups),
        "group_depths_updated": updated_groups,
        "adjacent_edges": adjacent_edges,
    }
