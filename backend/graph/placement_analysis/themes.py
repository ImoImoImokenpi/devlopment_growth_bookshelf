"""あらすじ(description)から、参加者の蔵書をLLMで内容テーマに分類する。

NDC（客観的な分類コード）とは違い、この参加者が持っている本の集合を
実際に読んで、内容・雰囲気が近い本同士をまとめた「内容テーマ」をLLMに
一括で作らせる。1冊ずつ別々に呼ぶとテーマの呼び方が本ごとにバラバラになり
比較できなくなるため、必ず参加者の蔵書全体を1回のプロンプトで渡す。

Themeは参加者ごとに独立（Concept同様、他の参加者の蔵書には影響しない）。
配置（並べ方）が変わるたびに再生成する必要はないので、置き場（enrich_positions
や compute_and_save_placement_profile）の自動フローには含めず、参加者が
明示的に呼んだときだけ実行する。
"""
from __future__ import annotations

import json
import re

from graph.main_kg.neo4j_driver import get_session
from graph.placement_analysis.books import attach_titles

MIN_BOOKS_WITH_DESCRIPTION = 4  # これ未満ならテーマ分けする意味が薄いのでスキップ
MAX_BOOKS_PER_PROMPT = 60       # プロンプト長を抑えるための上限


def _fetch_books_with_description(participant_id: str) -> list[dict]:
    with get_session() as session:
        return session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
            WHERE b.description IS NOT NULL AND b.description <> ""
            RETURN b.isbn AS isbn, b.title AS title, b.description AS description
            """,
            pid=participant_id,
        ).data()


def _build_theme_prompt(books: list[dict]) -> str:
    lines = [
        "あなたは、読書家の蔵書のあらすじを読んで、内容が近い本同士をグループ化する",
        "書誌分析家です。以下の本のタイトルとあらすじから、内容的なまとまり",
        "（例:「喪失と再生」「実務寄りの仕事論」「都市を舞台にした人間関係」のような、",
        "NDCのような形式的な分類ではなくテーマ・雰囲気による分類）を3〜8個作り、",
        "それぞれに短い名前（10字程度）を付けて、すべての本をいずれか1つのテーマに",
        "割り当ててください。内容的に似た本が無ければ無理にまとめず、テーマ数は",
        "少なくても構いません。",
        "",
    ]
    for b in books:
        desc = (b.get("description") or "")[:200]
        lines.append(f"- [{b['isbn']}] {b['title']}: {desc}")
    lines.append("")
    lines.append("出力は次のJSON形式のみとし、前置きや説明文、コードブロック記法は付けないでください。")
    lines.append('{"themes": [{"name": "テーマ名", "isbns": ["isbn1", "isbn2"]}, ...]}')
    return "\n".join(lines)


def _parse_theme_response(raw: str, valid_isbns: set[str]) -> list[dict]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    obj_start, obj_end = text.find("{"), text.rfind("}")
    candidate = text[obj_start:obj_end + 1] if obj_start != -1 and obj_end > obj_start else text
    try:
        data = json.loads(candidate)
        themes = data.get("themes") if isinstance(data, dict) else None
        if not isinstance(themes, list):
            return []
        result = []
        for t in themes:
            if not isinstance(t, dict):
                continue
            name = str(t.get("name", "")).strip()
            raw_isbns = t.get("isbns") or []
            isbns = [i for i in raw_isbns if isinstance(i, str) and i in valid_isbns]
            if name and isbns:
                result.append({"name": name, "isbns": isbns})
        return result
    except (json.JSONDecodeError, AttributeError):
        return []


def save_book_themes(participant_id: str, themes: list[dict]) -> None:
    """既存のこの参加者のHAS_THEMEを一旦消してから張り直す（テーマ分けは
    "現在の蔵書全体を見た上での分類"なので、配置の履歴のような追記式ではなく
    最新の分類で置き換える）。使われなくなったThemeノードも一緒に消す。"""
    with get_session() as session:
        session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(:Book)
                  -[r:HAS_THEME {participantId: $pid}]->(t:Theme {participantId: $pid})
            DELETE r
            WITH DISTINCT t
            WHERE NOT (t)<-[:HAS_THEME]-()
            DELETE t
            """,
            pid=participant_id,
        )
        for theme in themes:
            session.run(
                """
                MERGE (t:Theme {participantId: $pid, name: $name})
                ON CREATE SET t.themeId = randomUUID(), t.createdAt = datetime()
                WITH t
                UNWIND $isbns AS isbn
                MATCH (b:Book {isbn: isbn})
                MERGE (b)-[:HAS_THEME {participantId: $pid, origin: 'llm_generated'}]->(t)
                """,
                pid=participant_id,
                name=theme["name"],
                isbns=theme["isbns"],
            )


def generate_book_themes(llm, participant_id: str) -> dict:
    """参加者の蔵書のあらすじから内容テーマを生成し、保存する。
    description付きの本が少なすぎる場合は何もしない（skipped=True）。"""
    books = _fetch_books_with_description(participant_id)
    if len(books) < MIN_BOOKS_WITH_DESCRIPTION:
        return {"skipped": True, "reason": "あらすじのある本が少なすぎます", "theme_count": 0, "themes": []}

    valid_isbns = {b["isbn"] for b in books}
    prompt = _build_theme_prompt(books[:MAX_BOOKS_PER_PROMPT])
    raw = llm.generate_json(prompt, max_tokens=1200)
    themes = _parse_theme_response(raw, valid_isbns)

    save_book_themes(participant_id, themes)
    return {"skipped": False, "theme_count": len(themes), "themes": themes}


def get_theme_summary(participant_id: str) -> list[dict]:
    """現在保存されているテーマ一覧（名前・冊数）。分析パネル表示用。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                  -[:HAS_THEME {participantId: $pid}]->(t:Theme {participantId: $pid})
            RETURN t.name AS name, collect(b.isbn) AS isbns
            ORDER BY size(isbns) DESC
            """,
            pid=participant_id,
        ).data()
        summary = [{"name": r["name"], "isbns": r["isbns"], "count": len(r["isbns"])} for r in rows]
        return attach_titles(summary)
