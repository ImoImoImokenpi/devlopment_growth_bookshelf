"""1人分の知識グラフ(Neo4j)を、LLMに渡す軽いテキストに変換し、トークン数を測る。

使い方（backend/ で）:
    venv/Scripts/python scripts/kg_to_text.py                # 既定の参加者
    venv/Scripts/python scripts/kg_to_text.py --pid P00 --out-dir ../tmp

出力する2種類:
    full    : 本のあらすじまで含める
    compact : 本のあらすじを除く

ANTHROPIC_API_KEY があれば Messages API の count_tokens（無料）で正確なトークン数を測る。
なければ文字数だけを出す（文字数はトークン数の代わりにはならない）。

含めるもの: その参加者が所有する本(OWNS)と書誌・著者・出版社・NDC、棚の位置(LOCATES)、
隣接の履歴(SHELF_NEXT)、意味づけ(Concept)、感想(Impression)、最新の配置傾向
(PlacementProfile/DesignEvidence)、対話の中で動かした本(DURING_DIALOGUE の PlacementEvent)。
対話の外の並べ替えは整理なので移動履歴に含めない（以前の記録が残っていても読まない）。
含めないもの: 他の参加者のデータ、実験運用データ(GuessRecord, Uiab*, Style/Group/Work 系)、
画面操作ログ(GroupHighlightEvent, ModeSwitchEvent)。
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.getLogger("neo4j").setLevel(logging.ERROR)

from graph.main_kg.neo4j_driver import get_session  # noqa: E402
from participant import DEFAULT_PARTICIPANT_ID  # noqa: E402

MODEL = "claude-opus-5-5"


def fetch(pid: str) -> dict:
    with get_session() as s:
        books = [dict(r) for r in s.run(
            """
            MATCH (:Participant {participantId: $pid})-[own:OWNS]->(b:Book)
            OPTIONAL MATCH (b)-[:WRITTEN_BY]->(a:Author)
            OPTIONAL MATCH (b)-[:PUBLISHED_BY]->(pub:Publisher)
            OPTIONAL MATCH (b)-[:CLASSIFIED_AS]->(n:NDC)
            RETURN b.isbn AS isbn, b.title AS title, b.published_year AS year,
                   b.height_mm AS height, b.pages AS pages, b.spine_color AS color,
                   b.description AS description,
                   collect(DISTINCT coalesce(a.canonicalName, a.name)) AS authors,
                   collect(DISTINCT pub.name) AS publishers,
                   collect(DISTINCT n.code) AS ndc,
                   toString(own.addedAt) AS added_at
            ORDER BY b.title
            """, pid=pid)]
        positions = [dict(r) for r in s.run(
            """
            MATCH (pos:ShelfPosition {participantId: $pid})-[:LOCATES]->(b:Book)
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b)
            RETURN b.isbn AS isbn, pos.shelfIndex AS shelf, pos.columnIndex AS col
            ORDER BY shelf, col
            """, pid=pid)]
        adjacency = [dict(r) for r in s.run(
            """
            MATCH (a:Book)-[r:SHELF_NEXT {participantId: $pid}]->(b:Book)
            RETURN a.isbn AS a, b.isbn AS b, coalesce(r.isCurrent, false) AS current,
                   coalesce(r.coOccurrenceCount, 1) AS times
            ORDER BY current DESC, times DESC
            """, pid=pid)]
        concepts = [dict(r) for r in s.run(
            """
            MATCH (b:Book)-[r:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
            RETURN c.text AS text, collect(b.isbn) AS isbns,
                   collect(coalesce(r.origin, '')) AS origins
            ORDER BY size(isbns) DESC, text
            """, pid=pid)]
        impressions = [dict(r) for r in s.run(
            """
            MATCH (b:Book)-[:HAS_IMPRESSION]->(i:Impression {participantId: $pid})
            RETURN b.isbn AS isbn, i.text AS text
            """, pid=pid)]
        profile = s.run(
            """
            MATCH (:Participant {participantId: $pid})-[:HAS_PLACEMENT_PROFILE]->(p:PlacementProfile)
            RETURN p ORDER BY p.computed_at DESC LIMIT 1
            """, pid=pid).single()
        evidence = [dict(r) for r in s.run(
            """
            MATCH (:Participant {participantId: $pid})-[:HAS_DESIGN_EVIDENCE]->(e:DesignEvidence)
            WITH e ORDER BY e.computedAt DESC
            WITH e.shelfIndex AS shelf, e.evidenceType AS type, collect(e)[0] AS e
            RETURN shelf, type, e.label AS label, e.score AS score
            ORDER BY shelf, type
            """, pid=pid)]
        events = [dict(r) for r in s.run(
            """
            MATCH (e:PlacementEvent {participantId: $pid})-[:DURING_DIALOGUE]->(:DialogueSession)
            MATCH (e)-[:PLACED_BOOK]->(b:Book)
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b)
            OPTIONAL MATCH (e)-[:PLACED_AT]->(to:ShelfPosition)
            OPTIONAL MATCH (e)-[:PREVIOUS_POSITION]->(fr:ShelfPosition)
            RETURN b.isbn AS isbn, toString(e.timestamp) AS at,
                   fr.shelfIndex AS fs, fr.columnIndex AS fc,
                   to.shelfIndex AS ts, to.columnIndex AS tc
            ORDER BY e.timestamp
            """, pid=pid)]
    return {
        "books": books, "positions": positions, "adjacency": adjacency,
        "concepts": concepts, "impressions": impressions,
        "profile": dict(profile["p"]) if profile else None,
        "evidence": evidence, "events": events,
    }


def to_text(g: dict, variant: str) -> str:
    ids = {b["isbn"]: f"B{i + 1}" for i, b in enumerate(g["books"])}
    out: list[str] = []

    out.append("# 本（ID|書名|著者|出版社|年|NDC|高さmm|頁|背の色）")
    for b in g["books"]:
        out.append("|".join(str(x) for x in [
            ids[b["isbn"]], b["title"] or "", "、".join(b["authors"]), "、".join(b["publishers"]),
            b["year"] or "", ",".join(b["ndc"]), b["height"] or "", b["pages"] or "", b["color"] or "",
        ]))
        if variant == "full" and b.get("description"):
            out.append(f"  あらすじ: {b['description']}")

    out.append("\n# 今の棚（上から何段目: 左からの並び）")
    rows: dict[int, list[str]] = defaultdict(list)
    for p in g["positions"]:
        if p["isbn"] in ids:
            rows[p["shelf"]].append(ids[p["isbn"]])
    for shelf in sorted(rows):
        out.append(f"{shelf + 1}段目: {' '.join(rows[shelf])}")
    placed = {p["isbn"] for p in g["positions"]}
    unplaced = [ids[b["isbn"]] for b in g["books"] if b["isbn"] not in placed]
    if unplaced:
        out.append(f"棚に置いていない所有本: {' '.join(unplaced)}")

    out.append("\n# 隣り合わせの履歴（左-右|今も隣か|隣になった回数）")
    for a in g["adjacency"]:
        if a["a"] in ids and a["b"] in ids:
            out.append(f"{ids[a['a']]}-{ids[a['b']]}|{'今' if a['current'] else '過去'}|{a['times']}")

    out.append("\n# 持ち主の意味づけ（名前: 本）")
    for c in g["concepts"]:
        members = " ".join(ids[i] for i in c["isbns"] if i in ids)
        out.append(f"{c['text']}: {members}")

    if g["impressions"]:
        out.append("\n# 感想")
        for i in g["impressions"]:
            if i["isbn"] in ids:
                out.append(f"{ids[i['isbn']]}: {i['text']}")

    if g["profile"]:
        out.append("\n# 並べ方の傾向（最新・0〜1または-1〜1）")
        skip = {"participantId", "profile_id", "computed_at"}
        out.append(" ".join(
            f"{k}={round(v, 2) if isinstance(v, float) else v}"
            for k, v in sorted(g["profile"].items()) if k not in skip and v is not None
        ))
    if g["evidence"]:
        out.append("\n# 段ごとのデザイン根拠（段|種類|内容|スコア）")
        for e in g["evidence"]:
            score = round(e["score"], 2) if isinstance(e["score"], float) else e["score"]
            out.append(f"{(e['shelf'] or 0) + 1}|{e['type']}|{e['label']}|{score}")

    events = [e for e in g["events"] if e["isbn"] in ids]
    if events:
        out.append("\n# 対話の中で動かした本（日時|本|移動前→移動後(段,列)）")
        for e in events:
            fr = f"{e['fs'] + 1},{e['fc'] + 1}" if e["fs"] is not None else "新規"
            to = f"{e['ts'] + 1},{e['tc'] + 1}" if e["ts"] is not None else "?"
            out.append(f"{(e['at'] or '')[:16]}|{ids[e['isbn']]}|{fr}→{to}")

    return "\n".join(out) + "\n"


def count_tokens(text: str) -> int | None:
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.count_tokens(model=MODEL, messages=[{"role": "user", "content": text}])
    return resp.input_tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", default=DEFAULT_PARTICIPANT_ID)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent.parent / "kg_text"))
    args = ap.parse_args()

    g = fetch(args.pid)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"参加者 {args.pid}: 本{len(g['books'])} 棚の位置{len(g['positions'])} 隣接{len(g['adjacency'])} "
          f"意味づけ{len(g['concepts'])} 感想{len(g['impressions'])} 対話中の移動{len(g['events'])}")
    for variant in ("full", "compact"):
        text = to_text(g, variant)
        path = out_dir / f"kg_{args.pid}_{variant}.txt"
        path.write_text(text, encoding="utf-8")
        tokens = count_tokens(text)
        tok = f"{tokens:,} tokens ({MODEL})" if tokens is not None else "トークン数: 未計測（ANTHROPIC_API_KEY 未設定）"
        print(f"{variant:8s} {len(text):>7,} 文字  {tok}  -> {path}")


if __name__ == "__main__":
    main()
