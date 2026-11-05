"""おすすめ（recommendation）の知識グラフ読み書き。

おすすめは必ず知識グラフのノードを根拠(basis)にして探す。根拠は次の3種類。
  - concept: 意味づけ(Concept)
  - theme:   内容テーマ(Theme)
  - book:    本棚の本(Book)
根拠につながるノードからキーワードを集める材料を読み、選ばれた本を本棚に加えた結果を残す。

おすすめのきっかけ(trigger)は2つ。
  - concept: 対話の締めくくりで加わった意味づけから、自動で1冊
  - request: 対話の中で持ち主に「本を入れて」と頼まれて、冊数ぶん

  (:Recommendation)-[:FROM_CONCEPT|FROM_THEME|FROM_BOOK]->(根拠)
  (:Recommendation)-[:RECOMMENDS]->(:Book)        選ばれた本
  (:Recommendation)-[:RECOMMENDED_TO]->(:Participant)
  (:Recommendation)-[:NEXT_TO]->(:Book)           置き場所の基準にした隣の本
  (:Recommendation)-[:DURING_DIALOGUE]->(:DialogueSession)  頼まれた対話
  (:Book)-[:CONCEPT {origin: "recommendation", confidence: "suggested"}]->(:Concept)  根拠が意味づけのとき
  (:Participant)-[:OWNS {addedBy: "recommendation", recommendedFor: 根拠の名前}]->(:Book)

すべて participantId で分離する（neo4j_crud.py 冒頭の方針と同じ）。
"""
from __future__ import annotations

import uuid

from graph.main_kg.neo4j_driver import get_session

_CONSTRAINTS = [
    "CREATE CONSTRAINT rc_recommendation_id IF NOT EXISTS "
    "FOR (r:Recommendation) REQUIRE r.recommendationId IS UNIQUE",
]

BASIS_KINDS = ("concept", "theme", "book")


def ensure_recommendation_schema() -> None:
    """起動時に一度呼ぶ。制約は IF NOT EXISTS なので何度呼んでも安全。"""
    with get_session() as session:
        for statement in _CONSTRAINTS:
            session.run(statement)


def basis_label(kind: str, text: str) -> str:
    """根拠を人が読める名前にする（例: 意味づけ「旅に出たくなる本」）。"""
    if kind == "theme":
        return f"内容テーマ「{text}」"
    if kind == "book":
        return f"『{text}』"
    return f"意味づけ「{text}」"


def normalize_recommended_for(value: str | None) -> str:
    """OWNS.recommendedFor を表示用にそろえる。以前は意味づけの言葉だけを保存していた。"""
    value = (value or "").strip()
    if not value or value.startswith(("意味づけ「", "内容テーマ「", "『")):
        return value
    return f"意味づけ「{value}」"


# ============================================================
# 根拠と、そのつながり
# ============================================================

# 根拠につながる本ごとに、著者・内容テーマ・意味づけ・NDCを集める（concept/theme/book 共通）
_BOOK_DETAILS = """
OPTIONAL MATCH (b)-[:WRITTEN_BY]->(a:Author)
WITH b, collect(DISTINCT a.name) AS authors
OPTIONAL MATCH (b)-[:HAS_THEME {participantId: $pid}]->(t:Theme {participantId: $pid})
WITH b, authors, collect(DISTINCT t.name) AS themes
OPTIONAL MATCH (b)-[:CONCEPT {participantId: $pid}]->(o:Concept {participantId: $pid})
WITH b, authors, themes, collect(DISTINCT o.text) AS concepts
OPTIONAL MATCH (b)-[:CLASSIFIED_AS]->(n:NDC)
RETURN b.isbn AS isbn, b.title AS title, authors, themes, concepts AS other_concepts,
       head(collect(n.code)) AS ndc
ORDER BY b.title
"""


def get_basis_context(participant_id: str, kind: str, key: str) -> dict | None:
    """根拠のノードと、それにつながる本を返す。
    戻り値: {kind, key, text, label, books: [{isbn, title, authors, themes, other_concepts, ndc}]}"""
    with get_session() as session:
        if kind == "concept":
            head = session.run(
                "MATCH (c:Concept {participantId: $pid, conceptId: $key}) RETURN c.text AS text",
                pid=participant_id, key=key,
            ).single()
            match = """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                      -[:CONCEPT {participantId: $pid}]->(:Concept {participantId: $pid, conceptId: $key})
                WITH DISTINCT b
            """
        elif kind == "theme":
            head = session.run(
                "MATCH (t:Theme {participantId: $pid, name: $key}) RETURN t.name AS text",
                pid=participant_id, key=key,
            ).single()
            match = """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                      -[:HAS_THEME {participantId: $pid}]->(:Theme {participantId: $pid, name: $key})
                WITH DISTINCT b
            """
        elif kind == "book":
            head = session.run(
                "MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book {isbn: $key}) RETURN b.title AS text",
                pid=participant_id, key=key,
            ).single()
            match = """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book {isbn: $key})
                WITH DISTINCT b
            """
        else:
            return None
        if not head:
            return None
        books = [dict(r) for r in session.run(match + _BOOK_DETAILS, pid=participant_id, key=key)]

    # 意味づけ以外が根拠のときは、本についている意味づけもそのまま「つながり」として使う
    if kind == "concept":
        for b in books:
            b["other_concepts"] = [c for c in b["other_concepts"] if c != head["text"]]
    text = head["text"] or ""
    return {"kind": kind, "key": key, "text": text, "label": basis_label(kind, text), "books": books}


def get_graph_overview(participant_id: str) -> dict:
    """お願いされたときの計画用に、知識グラフの全体（意味づけ・内容テーマ・分野の偏り）を返す。"""
    with get_session() as session:
        concepts = [dict(r) for r in session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                  -[:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
            RETURN c.conceptId AS key, c.text AS text, collect(DISTINCT b.title) AS titles
            ORDER BY size(titles) DESC, text
            """,
            pid=participant_id,
        )]
        themes = [dict(r) for r in session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                  -[:HAS_THEME {participantId: $pid}]->(t:Theme {participantId: $pid})
            RETURN t.name AS key, t.name AS text, count(DISTINCT b) AS count
            ORDER BY count DESC, text
            """,
            pid=participant_id,
        )]
        ndc = [dict(r) for r in session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
            OPTIONAL MATCH (b)-[:CLASSIFIED_AS]->(n:NDC)
            WITH b, head(collect(n.code)) AS code
            RETURN CASE WHEN code IS NULL THEN '' ELSE substring(code, 0, 1) END AS l1, count(b) AS count
            ORDER BY count DESC
            """,
            pid=participant_id,
        )]
    return {"concepts": concepts, "themes": themes, "ndc": ndc}


def get_owned_isbns(participant_id: str) -> set[str]:
    with get_session() as session:
        result = session.run(
            "MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book) RETURN b.isbn AS isbn",
            pid=participant_id,
        )
        return {r["isbn"] for r in result}


# ============================================================
# 書き込み
# ============================================================

def mark_recommended_ownership(participant_id: str, isbn: str, label: str) -> None:
    """おすすめで加わった本だと分かるよう、所有関係に印を付ける。
    次の対話で「持ち主が選んで置いた本」と取り違えないようにするため。"""
    with get_session() as session:
        session.run(
            """
            MATCH (:Participant {participantId: $pid})-[own:OWNS]->(:Book {isbn: $isbn})
            SET own.addedBy = 'recommendation', own.recommendedFor = $label
            """,
            pid=participant_id, isbn=isbn, label=label,
        )


_BASIS_REL = {"concept": "FROM_CONCEPT", "theme": "FROM_THEME", "book": "FROM_BOOK"}
_BASIS_MATCH = {
    "concept": "MATCH (basis:Concept {participantId: $pid, conceptId: $basis_key})",
    "theme": "MATCH (basis:Theme {participantId: $pid, name: $basis_key})",
    "book": "MATCH (basis:Book {isbn: $basis_key})",
}


def save_recommendation(
    participant_id: str, basis_kind: str, basis_key: str, isbn: str, *,
    reason: str, placement_reason: str, anchor_isbn: str | None, side: str | None,
    queries: list[str], candidate_count: int,
    trigger: str = "concept", wish: str | None = None, aim: str | None = None,
    dialogue_session_id: str | None = None,
) -> str:
    recommendation_id = str(uuid.uuid4())
    with get_session() as session:
        session.run(
            f"""
            MATCH (p:Participant {{participantId: $pid}})
            {_BASIS_MATCH[basis_kind]}
            MATCH (b:Book {{isbn: $isbn}})
            CREATE (r:Recommendation {{
                recommendationId: $rid, participantId: $pid,
                trigger: $trigger, basisKind: $basis_kind, wish: $wish, aim: $aim,
                reason: $reason, placementReason: $placement_reason, side: $side,
                queries: $queries, candidateCount: $candidate_count,
                status: 'placed', createdAt: datetime()
            }})
            MERGE (r)-[:{_BASIS_REL[basis_kind]}]->(basis)
            MERGE (r)-[:RECOMMENDS]->(b)
            MERGE (r)-[:RECOMMENDED_TO]->(p)
            WITH r
            OPTIONAL MATCH (anchor:Book {{isbn: $anchor}})
            FOREACH (_ IN CASE WHEN anchor IS NULL THEN [] ELSE [1] END |
                MERGE (r)-[:NEXT_TO]->(anchor)
            )
            WITH r
            OPTIONAL MATCH (s:DialogueSession {{sessionId: $sid, participantId: $pid}})
            FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
                MERGE (r)-[:DURING_DIALOGUE]->(s)
            )
            """,
            pid=participant_id, basis_key=basis_key, isbn=isbn, rid=recommendation_id,
            trigger=trigger, basis_kind=basis_kind, wish=wish, aim=aim,
            reason=reason, placement_reason=placement_reason, side=side,
            queries=queries, candidate_count=candidate_count,
            anchor=anchor_isbn or "", sid=dialogue_session_id or "",
        )
    return recommendation_id


def mark_removed(participant_id: str, recommendation_id: str) -> bool:
    """おすすめで置いた本を持ち主が外した（受け入れなかった記録として残す）。"""
    with get_session() as session:
        row = session.run(
            """
            MATCH (r:Recommendation {recommendationId: $rid, participantId: $pid})
            SET r.status = 'removed', r.removedAt = datetime()
            RETURN count(r) AS c
            """,
            rid=recommendation_id, pid=participant_id,
        ).single()
        return bool(row and row["c"])


# ============================================================
# 読み出し（画面・対話用）
# ============================================================

def get_book_recommendation(participant_id: str, isbn: str) -> dict | None:
    """本の詳細パネル用。この本がおすすめで加わった本なら、いちばん新しいおすすめの記録を返す。"""
    with get_session() as session:
        row = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[own:OWNS {addedBy: 'recommendation'}]->(b:Book {isbn: $isbn})
            MATCH (r:Recommendation {participantId: $pid, status: 'placed'})-[:RECOMMENDS]->(b)
            OPTIONAL MATCH (r)-[:FROM_CONCEPT]->(c:Concept)
            OPTIONAL MATCH (r)-[:FROM_THEME]->(t:Theme)
            OPTIONAL MATCH (r)-[:FROM_BOOK]->(fb:Book)
            OPTIONAL MATCH (r)-[:NEXT_TO]->(anchor:Book)
            RETURN r.recommendationId AS recommendation_id,
                   coalesce(r.basisKind, 'concept') AS basis_kind,
                   coalesce(c.text, t.name, fb.title) AS basis_text,
                   coalesce(r.trigger, 'concept') AS trigger, r.wish AS wish, r.aim AS aim,
                   r.reason AS reason, r.placementReason AS placement_reason,
                   r.side AS side, anchor.title AS anchor_title,
                   toString(date(r.createdAt)) AS created_at
            ORDER BY r.createdAt DESC
            LIMIT 1
            """,
            pid=participant_id, isbn=isbn,
        ).single()
        if not row:
            return None
        data = dict(row)
        data["basis"] = basis_label(data["basis_kind"], data.pop("basis_text") or "")
        # 以前の画面との互換（意味づけが根拠のときだけ）
        data["concept"] = data["basis"][len("意味づけ「"):-1] if data["basis_kind"] == "concept" else None
        return data


def get_session_requested_books(participant_id: str, session_id: str) -> list[dict]:
    """この対話で頼まれて加わった本（対話のLLMに渡す）。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (r:Recommendation {participantId: $pid, trigger: 'request', status: 'placed'})
                  -[:DURING_DIALOGUE]->(:DialogueSession {sessionId: $sid, participantId: $pid})
            MATCH (r)-[:RECOMMENDS]->(b:Book)
            RETURN b.isbn AS isbn, b.title AS title, r.wish AS wish, r.reason AS reason
            ORDER BY r.createdAt
            """,
            pid=participant_id, sid=session_id,
        )
        return [dict(r) for r in result]


# ============================================================
# 知識グラフの育ち具合に合わせた自動のおすすめ（routers/recommend.py の /recommend/auto）
# ============================================================
#
# 育ち具合は「持ち主が本に付けた意味づけのつながり（Book-[:CONCEPT]->Concept）」の数で測る。
# おすすめが付けたつながり（origin='recommendation'）は数えない（おすすめが自分で育ち具合を押し上げないように）。
# 前回おすすめを足したときの数を Participant.recommendCheckpoint に残し、そこから一定数増えたら1冊足す。

def count_meaning_links(participant_id: str) -> int:
    with get_session() as session:
        row = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(:Book)
                  -[r:CONCEPT {participantId: $pid}]->(:Concept {participantId: $pid})
            WHERE coalesce(r.origin, '') <> 'recommendation'
            RETURN count(r) AS n
            """,
            pid=participant_id,
        ).single()
        return row["n"] if row else 0


def get_recommend_checkpoint(participant_id: str) -> int:
    with get_session() as session:
        row = session.run(
            "MATCH (p:Participant {participantId: $pid}) RETURN coalesce(p.recommendCheckpoint, 0) AS n",
            pid=participant_id,
        ).single()
        return row["n"] if row else 0


def set_recommend_checkpoint(participant_id: str, links: int) -> None:
    with get_session() as session:
        session.run(
            "MERGE (p:Participant {participantId: $pid}) SET p.recommendCheckpoint = $n",
            pid=participant_id, n=links,
        )


def pick_auto_concepts(participant_id: str, min_books: int, prefer: list[str] | None = None,
                       limit: int = 3) -> list[dict]:
    """おすすめの根拠にできる意味づけを、ふさわしい順に返す。
    - 持ち主の本が min_books 冊以上つながっている（手がかりが少ないと外れやすいため）
    - まだその意味づけからおすすめを出していない
    並びは、この対話で加わった・育った意味づけ（prefer）→ つながる本が多い → 新しい の順。
    戻り値: [{concept_id, text, books}]"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                  -[r:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
            WHERE coalesce(r.origin, '') <> 'recommendation'
            WITH c, count(DISTINCT b) AS books
            WHERE books >= $min_books
              AND NOT EXISTS { MATCH (:Recommendation {participantId: $pid})-[:FROM_CONCEPT]->(c) }
            RETURN c.conceptId AS concept_id, c.text AS text, books, c.createdAt AS created_at
            """,
            pid=participant_id, min_books=min_books,
        )
        found = [dict(r) for r in rows]
    preferred = set(prefer or [])
    found.sort(key=lambda r: (
        r["concept_id"] not in preferred, -r["books"],
        -(r["created_at"].to_native().timestamp() if r["created_at"] else 0),
    ))
    return [{k: r[k] for k in ("concept_id", "text", "books")} for r in found[:limit]]


# ============================================================
# 外したおすすめ（受け入れられなかった記録を、次のおすすめと対話に生かす）
# ============================================================

def mark_removed_by_isbn(participant_id: str, isbn: str) -> int:
    """本棚から本を外したとき、その本がおすすめで置いた本なら「外した」にする。
    （対話の画面の「外す」以外、たとえば本棚のゴミ箱で外したときも記録するため）"""
    with get_session() as session:
        row = session.run(
            """
            MATCH (r:Recommendation {participantId: $pid, status: 'placed'})-[:RECOMMENDS]->(:Book {isbn: $isbn})
            SET r.status = 'removed', r.removedAt = datetime()
            RETURN count(r) AS c
            """,
            pid=participant_id, isbn=isbn,
        ).single()
        return row["c"] if row else 0


def get_removed_recommendations(participant_id: str, limit: int = 8, since=None) -> list[dict]:
    """外したおすすめ（新しい順）。since を渡すと、それより後に外したものだけ。
    戻り値: [{isbn, title, authors, basis, reason, removed_at}]"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (r:Recommendation {participantId: $pid, status: 'removed'})-[:RECOMMENDS]->(b:Book)
            WHERE $since IS NULL OR r.removedAt > $since
            OPTIONAL MATCH (r)-[:FROM_CONCEPT]->(c:Concept)
            OPTIONAL MATCH (r)-[:FROM_THEME]->(t:Theme)
            OPTIONAL MATCH (r)-[:FROM_BOOK]->(fb:Book)
            OPTIONAL MATCH (b)-[:WRITTEN_BY]->(a:Author)
            WITH r, b, coalesce(r.basisKind, 'concept') AS kind, coalesce(c.text, t.name, fb.title) AS basis_text,
                 collect(DISTINCT a.name) AS authors
            RETURN b.isbn AS isbn, b.title AS title, authors, kind, basis_text,
                   r.reason AS reason, toString(date(r.removedAt)) AS removed_at
            ORDER BY r.removedAt DESC
            LIMIT $limit
            """,
            pid=participant_id, since=since, limit=limit,
        )
        out = []
        for r in result:
            d = dict(r)
            d["basis"] = basis_label(d.pop("kind"), d.pop("basis_text") or "")
            out.append(d)
        return out


def get_removed_isbns(participant_id: str) -> list[str]:
    """外したおすすめの本（二度とおすすめしない）。"""
    with get_session() as session:
        return [r["isbn"] for r in session.run(
            """
            MATCH (r:Recommendation {participantId: $pid, status: 'removed'})-[:RECOMMENDS]->(b:Book)
            RETURN DISTINCT b.isbn AS isbn
            """,
            pid=participant_id,
        )]
