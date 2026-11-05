"""本棚対話の知識グラフ読み書き。

対話は「ユーザーが並べ替えを終えて対話ボタンを押す」ことで始まる。
LLMには知識グラフから読んだ次の材料を渡す（組み立ては routers/dialogue.py）:
  - 今の本棚（段ごとの並び・著者・内容テーマ・これまでの意味づけ）
  - 前回の対話以降にユーザーが直接動かした本（Participant.pendingMoves）と、
    新しく本棚に加えた本（OWNS.addedAt）
  - この対話の中で動かした本（PlacementEvent -[:DURING_DIALOGUE]-> DialogueSession）

移動の記録の方針（neo4j_crud.update_shelf_layout_chain）:
  - 対話の外の並べ替えは履歴に残さない。次の対話のきっかけ用に pendingMoves へ
    「動かした本と元の位置」だけを溜め、対話を始めたら空にする。
  - 最初の対話までの並べ替えは整理なので、最初の対話ではきっかけに使わず捨てる。
  - 対話中の並べ替えだけを PlacementEvent として残し、その対話へつなぐ。

対話そのものもグラフに残す:
  (:DialogueSession)-[:HELD_BY]->(:Participant)
  (:DialogueSession)-[:HAS_TURN]->(:DialogueTurn {role, text, index})
  (:DialogueSession)-[:DISCUSSED_BOOK]->(:Book)          きっかけになった本
  (:PlacementEvent)-[:DURING_DIALOGUE]->(:DialogueSession) 対話の中で動かした本
  (:MeaningProposal)-[:PROPOSED_IN]->(:DialogueSession)   LLMが会話から取り出した意味づけ候補
  (:MeaningProposal)-[:FROM_TURN]->(:DialogueTurn)        どの発話から取り出したか
  (:MeaningProposal)-[:SUGGESTS]->(:Book)
  (:MeaningProposal)-[:BECAME]->(:Concept)                ユーザーが採用した結果

すべて participantId で分離する（neo4j_crud.py 冒頭の方針と同じ）。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session
from graph.recommendation.store import normalize_recommended_for

MAX_CHANGED_BOOKS = 8


def get_shelf_books(participant_id: str) -> list[dict]:
    """今の本棚にある本を、段→左からの順に返す。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                  <-[:LOCATES]-(pos:ShelfPosition {participantId: $pid})
            OPTIONAL MATCH (b)-[:WRITTEN_BY]->(a:Author)
            WITH b, pos, collect(DISTINCT a.name) AS authors
            OPTIONAL MATCH (b)-[:HAS_THEME {participantId: $pid}]->(t:Theme {participantId: $pid})
            WITH b, pos, authors, collect(DISTINCT t.name) AS themes
            OPTIONAL MATCH (b)-[:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
            WITH b, pos, authors, themes, collect(DISTINCT c.text) AS concepts
            RETURN b.isbn AS isbn, b.title AS title,
                   b.height_mm AS height_mm, b.spine_color AS spine_color,
                   pos.shelfIndex AS shelf_index, pos.columnIndex AS column_index,
                   authors, themes, concepts
            ORDER BY shelf_index, column_index
            """,
            pid=participant_id,
        )
        books = []
        seen = set()
        for r in result:
            # 同じ本が複数冊ある場合は、最初の位置だけを使う（会話の材料としては1冊で十分）
            if r["isbn"] in seen:
                continue
            seen.add(r["isbn"])
            books.append(dict(r))
        return books


def get_changes_since_last_dialogue(participant_id: str) -> dict:
    """前回の対話以降に、直接動かした本（pendingMoves）と新しく加えた本を返す。
    はじめての対話では、それまでの並べ替え・追加は整理なので扱わない。"""
    with get_session() as session:
        row = session.run(
            """
            MATCH (p:Participant {participantId: $pid})
            OPTIONAL MATCH (s:DialogueSession {participantId: $pid})
            RETURN max(s.startedAt) AS since, coalesce(p.pendingMoves, []) AS pending
            """,
            pid=participant_id,
        ).single()
        since = row["since"] if row else None
        pending = row["pending"] if row else []

        if since is None:
            return {"is_first_dialogue": True, "moved": [], "added_isbns": [], "recommended": {}, "removed": []}

        moved = []
        for entry in pending[-MAX_CHANGED_BOOKS:]:
            isbn, shelf, col = (entry.split("|") + ["", ""])[:3]
            moved.append({
                "isbn": isbn,
                "from_pos": {
                    "shelf_index": int(shelf) if shelf else None,
                    "column_index": int(col) if col else None,
                },
            })

        added = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[own:OWNS]->(b:Book)
            WHERE own.addedAt > $since
            RETURN b.isbn AS isbn, own.addedBy AS added_by, own.recommendedFor AS recommended_for
            ORDER BY own.addedAt DESC
            LIMIT $limit
            """,
            pid=participant_id, since=since, limit=MAX_CHANGED_BOOKS,
        )
        added_isbns, recommended = [], {}
        for r in added:
            added_isbns.append(r["isbn"])
            # 意味づけからのおすすめで加わった本（持ち主が選んで置いた本ではない）
            if r["added_by"] == "recommendation":
                recommended[r["isbn"]] = normalize_recommended_for(r["recommended_for"])

    # 前回の対話より後に持ち主が外したおすすめ（どこが合わなかったかを対話で聞くきっかけにする）
    from graph.recommendation.store import get_removed_recommendations
    removed = get_removed_recommendations(participant_id, limit=MAX_CHANGED_BOOKS, since=since)
    return {"is_first_dialogue": False, "moved": moved, "added_isbns": added_isbns,
            "recommended": recommended, "removed": removed}


def get_recent_dialogues(participant_id: str, limit: int = 5) -> list[dict]:
    """これまでの対話（新しい順）。同じ問いを繰り返さないよう、対話のLLMに渡す。
    各対話の最初の問い・話題にした本（きっかけの本と最初に尋ねた本）・加わった意味づけを返す。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (s:DialogueSession {participantId: $pid})
            WITH s ORDER BY s.startedAt DESC LIMIT $limit
            OPTIONAL MATCH (s)-[:HAS_TURN]->(t:DialogueTurn {role: 'assistant'})
            WITH s, t ORDER BY t.index
            WITH s, head(collect(t.text)) AS first_question
            OPTIONAL MATCH (s)-[:DISCUSSED_BOOK|OPENED_WITH]->(b:Book)
            WITH s, first_question, collect(DISTINCT {isbn: b.isbn, title: b.title}) AS books
            OPTIONAL MATCH (m:MeaningProposal {participantId: $pid, status: 'accepted'})-[:PROPOSED_IN]->(s)
            WITH s.startedAt AS started_at, first_question, books,
                 collect(DISTINCT coalesce(m.finalText, m.text)) AS meanings
            RETURN toString(date(started_at)) AS date, first_question,
                   [x IN books WHERE x.isbn IS NOT NULL] AS books, meanings
            ORDER BY started_at DESC
            """,
            pid=participant_id, limit=limit,
        )
        return [dict(r) for r in result]


def create_session(
    participant_id: str, session_id: str, discussed_isbns: list[str], changes_text: str,
    opened_with_isbns: list[str] | None = None, history_text: str = "",
) -> None:
    """changes_text: 対話のきっかけ（動かした本・加えた本）をLLM向けに書いた文。
    history_text: これまでの対話をLLM向けに書いた文（同じ問いを繰り返さないため）。
    会話の途中でも同じきっかけ・履歴を渡し続けるため、開始時に固定して保存する。
    opened_with_isbns: 最初の問いで尋ねた本（次の対話で「もう話題にした本」として使う）。
    きっかけに使った「前回の対話以降に動かした本」(pendingMoves) はここで空にする。
    はじめての対話なら、それまでの整理中に積み上がった隣り合わせの履歴もリセットする。"""
    with get_session() as session:
        is_first = session.run(
            "MATCH (s:DialogueSession {participantId: $pid}) RETURN count(s) = 0 AS first",
            pid=participant_id,
        ).single()["first"]
        if is_first:
            reset_adjacency_history(session, participant_id)
        session.run(
            """
            MERGE (p:Participant {participantId: $pid})
                ON CREATE SET p.createdAt = datetime()
            SET p.pendingMoves = []
            CREATE (s:DialogueSession {
                sessionId: $sid, participantId: $pid,
                status: 'active', changesText: $changes_text, historyText: $history_text,
                startedAt: datetime(), createdAt: datetime()
            })
            MERGE (s)-[:HELD_BY]->(p)
            WITH s
            CALL (s) {
                UNWIND $isbns AS isbn
                MATCH (b:Book {isbn: isbn})
                MERGE (s)-[:DISCUSSED_BOOK]->(b)
            }
            CALL (s) {
                UNWIND $opened AS isbn
                MATCH (b:Book {isbn: isbn})
                MERGE (s)-[:OPENED_WITH]->(b)
            }
            """,
            pid=participant_id, sid=session_id, isbns=discussed_isbns, changes_text=changes_text,
            opened=opened_with_isbns or [], history_text=history_text,
        )


def reset_adjacency_history(session, participant_id: str) -> None:
    """隣り合わせの履歴(SHELF_NEXT)を「今の並び」から数え直す。
    最初の対話までの並べ替えは整理なので、隣になった回数に数えない。
    今隣り合っている組は1回目として残し、以前隣だった組の記録は消す。"""
    session.run(
        """
        MATCH (:Book)-[r:SHELF_NEXT {participantId: $pid}]->(:Book)
        WHERE NOT coalesce(r.isCurrent, false)
        DELETE r
        """,
        pid=participant_id,
    )
    session.run(
        """
        MATCH (:Book)-[r:SHELF_NEXT {participantId: $pid}]->(:Book)
        SET r.coOccurrenceCount = 1,
            r.firstSeenAt = datetime(), r.formedAt = datetime(), r.lastSeenAt = datetime()
        REMOVE r.separatedAt
        """,
        pid=participant_id,
    )


def supersede_pending_proposals(participant_id: str, session_id: str) -> int:
    """締めくくりのあと持ち主が「もう少し話す」を選んだとき、確認中だった意味づけの候補を
    「置き換え(superseded)」にする。次の締めくくりで対話全体から改めてまとめ直すため。"""
    with get_session() as session:
        return session.run(
            """
            MATCH (m:MeaningProposal {participantId: $pid, status: 'pending'})
                  -[:PROPOSED_IN]->(:DialogueSession {sessionId: $sid, participantId: $pid})
            SET m.status = 'superseded', m.resolvedAt = datetime()
            RETURN count(m) AS c
            """,
            pid=participant_id, sid=session_id,
        ).single()["c"]


def get_session_moves(participant_id: str, session_id: str) -> list[dict]:
    """この対話の中で持ち主が直接動かした本（古い順、同じ本は最初の元位置と回数）。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (e:PlacementEvent {participantId: $pid})-[:DURING_DIALOGUE]->
                  (:DialogueSession {sessionId: $sid, participantId: $pid})
            MATCH (e)-[:PLACED_BOOK]->(b:Book)
            OPTIONAL MATCH (e)-[:PREVIOUS_POSITION]->(prev:ShelfPosition)
            WITH b, e, prev ORDER BY e.timestamp ASC
            WITH b, collect({shelf_index: prev.shelfIndex, column_index: prev.columnIndex}) AS hist,
                 count(e) AS move_count, min(e.timestamp) AS first_at
            RETURN b.isbn AS isbn, hist[0] AS from_pos, move_count
            ORDER BY first_at
            """,
            pid=participant_id, sid=session_id,
        )
        return [dict(r) for r in result]


def get_session_info(participant_id: str, session_id: str) -> dict | None:
    with get_session() as session:
        row = session.run(
            """
            MATCH (s:DialogueSession {sessionId: $sid, participantId: $pid})
            OPTIONAL MATCH (s)-[:DISCUSSED_BOOK]->(b:Book)
            RETURN s.status AS status, s.changesText AS changes_text,
                   coalesce(s.historyText, '') AS history_text,
                   collect(b.isbn) AS discussed_isbns
            """,
            pid=participant_id, sid=session_id,
        ).single()
        return dict(row) if row and row["status"] else None


def add_turn(
    participant_id: str, session_id: str, turn_id: str, role: str, text: str,
    is_wrap_up: bool = False,
) -> None:
    """is_wrap_up: LLMが会話を締めくくった発言か（締めくくり後に続けた場合の数え直しに使う）。"""
    with get_session() as session:
        session.run(
            """
            MATCH (s:DialogueSession {sessionId: $sid, participantId: $pid})
            OPTIONAL MATCH (s)-[:HAS_TURN]->(prev:DialogueTurn)
            WITH s, count(prev) AS n
            CREATE (t:DialogueTurn {
                turnId: $tid, participantId: $pid, role: $role, text: $text,
                isWrapUp: $wrap, index: n, createdAt: datetime()
            })
            MERGE (s)-[:HAS_TURN]->(t)
            """,
            pid=participant_id, sid=session_id, tid=turn_id, role=role, text=text, wrap=is_wrap_up,
        )


def get_turns(participant_id: str, session_id: str) -> list[dict]:
    with get_session() as session:
        result = session.run(
            """
            MATCH (:DialogueSession {sessionId: $sid, participantId: $pid})-[:HAS_TURN]->(t:DialogueTurn)
            RETURN t.role AS role, t.text AS text, coalesce(t.isWrapUp, false) AS is_wrap_up
            ORDER BY t.index
            """,
            pid=participant_id, sid=session_id,
        )
        return [dict(r) for r in result]


def get_accepted_meanings(participant_id: str, session_id: str) -> list[dict]:
    """この対話で持ち主が採用した意味づけ（採用時に直した名前・本で返す）。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (m:MeaningProposal {participantId: $pid, status: 'accepted'})
                  -[:PROPOSED_IN]->(:DialogueSession {sessionId: $sid, participantId: $pid})
            RETURN coalesce(m.finalText, m.text) AS text, coalesce(m.finalIsbns, m.isbns) AS isbns
            ORDER BY m.resolvedAt
            """,
            pid=participant_id, sid=session_id,
        )
        return [dict(r) for r in result]


def add_proposal(
    participant_id: str, session_id: str, turn_id: str,
    proposal_id: str, meaning: str, isbns: list[str], reason: str,
) -> None:
    with get_session() as session:
        session.run(
            """
            MATCH (s:DialogueSession {sessionId: $sid, participantId: $pid})
            MATCH (t:DialogueTurn {turnId: $tid})
            CREATE (m:MeaningProposal {
                proposalId: $prid, participantId: $pid,
                text: $meaning, reason: $reason, isbns: $isbns,
                status: 'pending', createdAt: datetime()
            })
            MERGE (m)-[:PROPOSED_IN]->(s)
            MERGE (m)-[:FROM_TURN]->(t)
            WITH m
            UNWIND $isbns AS isbn
            MATCH (b:Book {isbn: isbn})
            MERGE (m)-[:SUGGESTS]->(b)
            """,
            pid=participant_id, sid=session_id, tid=turn_id, prid=proposal_id,
            meaning=meaning, reason=reason, isbns=isbns,
        )


def get_proposal(participant_id: str, proposal_id: str) -> dict | None:
    with get_session() as session:
        row = session.run(
            """
            MATCH (m:MeaningProposal {proposalId: $prid, participantId: $pid})
            RETURN m.text AS text, m.isbns AS isbns, m.status AS status
            """,
            pid=participant_id, prid=proposal_id,
        ).single()
        return dict(row) if row else None


def resolve_proposal(
    participant_id: str, proposal_id: str, status: str,
    final_text: str | None = None, final_isbns: list[str] | None = None,
    concept_id: str | None = None,
) -> None:
    """提案の結果を記録する。status は accepted / rejected。
    採用時はユーザーが直した文言・冊を final_* に残し、できた Concept へ BECAME を張る。"""
    with get_session() as session:
        session.run(
            """
            MATCH (m:MeaningProposal {proposalId: $prid, participantId: $pid})
            SET m.status = $status, m.resolvedAt = datetime(),
                m.finalText = $final_text, m.finalIsbns = $final_isbns
            WITH m
            OPTIONAL MATCH (c:Concept {conceptId: $cid, participantId: $pid})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
                MERGE (m)-[:BECAME]->(c)
            )
            """,
            pid=participant_id, prid=proposal_id, status=status,
            final_text=final_text, final_isbns=final_isbns, cid=concept_id,
        )


def end_session(participant_id: str, session_id: str) -> None:
    with get_session() as session:
        session.run(
            """
            MATCH (s:DialogueSession {sessionId: $sid, participantId: $pid})
            SET s.status = 'ended', s.endedAt = datetime()
            """,
            pid=participant_id, sid=session_id,
        )
