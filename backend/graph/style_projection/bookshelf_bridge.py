"""既存の本棚UI（SpineShelfView、背表紙表示＝proposed_ui）から
投影スタイル分析システム（style_projection）への橋渡し。

配置完了イベント（/bookshelf/sync-layout。ドラッグ操作から10秒のデバウンスを
経て呼ばれる）のタイミングで、SQLite側の配置情報とNeo4j側の既存の意味づけ
（Concept）・感想（Impression）を読み、style_projectionのスキーマへupsertし、
StyleProfileを1件追記する。呼び出し側でしか使わないため、失敗しても
本棚の保存自体は止めない（呼び出し側で例外を握りつぶす想定）。

用語対応:
  Book(isbn)                             → Work(work_id=isbn)
  ShelfLayout行(participant_id, isbn)    → ShelvedBook(shelved_id="{pid}:{isbn}")
  Concept(意味づけ)                       → Group（同じConceptに紐づく本が、
                                             そのまま構造上のグルーピングとみなせるため。
                                             Group.nameにConceptの文言を写すが、
                                             構造指標側はGroup.nameを一切参照しない）
  Impression(感想)                        → Comment
  condition                              → "proposed_ui" 固定
                                             （このエンドポイントは背表紙UIからしか
                                             呼ばれないため。グリッド表示＝統制UIは
                                             自由配置ができず sync-layout を呼ばない）
  SHELF_NEXT(isCurrent)                   → ADJACENT_TO
                                             （「本棚で隣か」の定義を1つに統一する。
                                             以前はここでKNN/座標ベースの隣接を
                                             独自に再計算していたが、主KG側が
                                             update_shelf_layout_chainで実際の
                                             背表紙の隙間から確定させた隣接と
                                             食い違う恐れがあったため、その結果を
                                             そのまま読んで渡す）
"""
from __future__ import annotations

import logging
import math

from sqlalchemy.orm import Session

from graph.main_kg.neo4j_driver import get_session as get_neo4j_session
from models import ShelfLayout, RegisteredBook
from graph.style_projection.ingest import ingest_shelf_snapshot
from graph.style_projection.metrics import save_style_profile

logger = logging.getLogger(__name__)

# 段と段のおおよその間隔（KNN/距離閾値の判定をx_posと同じ土俵に乗せるための目安値）
SHELF_PITCH_MM = 250.0


def _shelved_id(participant_id: str, isbn: str) -> str:
    return f"{participant_id}:{isbn}"


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fetch_concept_groups(participant_id: str, isbns: list[str]) -> tuple[list[dict], dict[str, list[str]]]:
    """既存の意味づけ(Concept)を投影スタイル分析のGroupとして読み出す。
    戻り値: (groups, isbn -> group_id一覧)。参照は投入時のみで、
    構造指標の計算側ではGroup.nameを読まない設計は変わらない。"""
    with get_neo4j_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                  -[:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
            WHERE b.isbn IN $isbns
            RETURN c.conceptId AS group_id, c.text AS name, collect(DISTINCT b.isbn) AS isbns
            """,
            pid=participant_id,
            isbns=isbns,
        )
        groups: list[dict] = []
        group_ids_by_isbn: dict[str, list[str]] = {}
        for r in rows:
            if not r["group_id"]:
                continue
            groups.append({"group_id": r["group_id"], "name": r["name"], "created_by": "manual"})
            for isbn in r["isbns"]:
                group_ids_by_isbn.setdefault(isbn, []).append(r["group_id"])
        return groups, group_ids_by_isbn


def _fetch_current_shelf_next_pairs(participant_id: str, isbns: list[str]) -> list[tuple[str, str]]:
    """主KG（graph.main_kg.neo4j_crud）側で既に確定している現在の隣接
    (SHELF_NEXT, isCurrent=true) をそのまま読み出す。update_shelf_layout_chain が
    /bookshelf/sync-layout の中でこの関数より前に同期的に呼ばれ、実際の背表紙の
    隙間から張り替え済みである前提（routers/bookshelf.py:sync_layout を参照）。"""
    with get_neo4j_session() as session:
        rows = session.run(
            """
            MATCH (a:Book)-[r:SHELF_NEXT {participantId: $pid, isCurrent: true}]->(b:Book)
            WHERE a.isbn IN $isbns AND b.isbn IN $isbns
            RETURN a.isbn AS a, b.isbn AS b
            """,
            pid=participant_id,
            isbns=isbns,
        )
        return [(r["a"], r["b"]) for r in rows]


def _fetch_comments(participant_id: str, isbns: list[str]) -> dict[str, list[dict]]:
    """既存の感想(Impression)を投影スタイル分析のCommentとして読み出す。
    Impression.impressionIdをそのままcomment_idに使い、再送しても重複しないようにする。"""
    with get_neo4j_session() as session:
        rows = session.run(
            """
            MATCH (b:Book)-[:HAS_IMPRESSION]->(i:Impression {participantId: $pid})
            WHERE b.isbn IN $isbns
            RETURN b.isbn AS isbn, i.impressionId AS comment_id,
                   i.text AS text, toString(i.createdAt) AS created_at
            """,
            pid=participant_id,
            isbns=isbns,
        )
        comments_by_isbn: dict[str, list[dict]] = {}
        for r in rows:
            comments_by_isbn.setdefault(r["isbn"], []).append({
                "comment_id": r["comment_id"],
                "text": r["text"],
                "created_at": r["created_at"],
            })
        return comments_by_isbn


def sync_from_bookshelf(db: Session, participant_id: str) -> dict | None:
    """現在のSQLite本棚状態を投影スタイル分析システムへ反映し、StyleProfileを1件追記する。
    棚に本がなければ何もしない（Noneを返す）。"""
    layouts = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.participant_id == participant_id)
        .all()
    )
    if not layouts:
        return None

    isbns = [l.isbn for l in layouts]
    reg_books = {
        rb.isbn: rb
        for rb in db.query(RegisteredBook).filter(RegisteredBook.isbn.in_(isbns)).all()
    }

    groups, group_ids_by_isbn = _fetch_concept_groups(participant_id, isbns)
    comments_by_isbn = _fetch_comments(participant_id, isbns)

    books = []
    for l in layouts:
        rb = reg_books.get(l.isbn)
        books.append({
            "shelved_id": _shelved_id(participant_id, l.isbn),
            "x": float(l.x_pos or 0),
            "y": float(l.shelf_index or 0) * SHELF_PITCH_MM,
            "shelf_id": f"shelf_{l.shelf_index}",
            "condition": "proposed_ui",
            "work": {
                "work_id": l.isbn,
                "title": rb.title if rb else None,
                "author": rb.authors if rb else None,
                "published_year": _to_int(rb.published_year) if rb else None,
                "genre": rb.ndc if rb else None,
            },
            "group_ids": group_ids_by_isbn.get(l.isbn, []),
            "comments": comments_by_isbn.get(l.isbn, []),
        })

    payload = {
        "participant_id": participant_id,
        "role": "owner",
        "groups": groups,
        "books": books,
    }

    xy_by_isbn = {b["work"]["work_id"]: (b["x"], b["y"]) for b in books}
    explicit_pairs = [
        {
            "a": _shelved_id(participant_id, a_isbn),
            "b": _shelved_id(participant_id, b_isbn),
            "distance": math.hypot(
                xy_by_isbn[a_isbn][0] - xy_by_isbn[b_isbn][0],
                xy_by_isbn[a_isbn][1] - xy_by_isbn[b_isbn][1],
            ),
        }
        for a_isbn, b_isbn in _fetch_current_shelf_next_pairs(participant_id, isbns)
        if a_isbn in xy_by_isbn and b_isbn in xy_by_isbn
    ]

    ingest_shelf_snapshot(payload, adjacency_mode="explicit", explicit_adjacency_pairs=explicit_pairs)
    return save_style_profile(participant_id)
