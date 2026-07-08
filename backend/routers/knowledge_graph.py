import json
import re

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from admin_neo4j.neo4j_driver import get_session
from admin_neo4j.neo4j_crud import get_graph_overview
from utils.llm_provider import get_llm_client
from database import get_db
from models import ShelfLayout

router = APIRouter(prefix="/knowledge_graph")

_llm = get_llm_client()

NDC_L1 = {
    "0": "総記", "1": "哲学", "2": "歴史・地理", "3": "社会科学",
    "4": "自然科学", "5": "技術", "6": "産業", "7": "芸術", "8": "言語", "9": "文学",
}

@router.get("/")
def get_graph():
    with get_session() as session:
        nodes_result = session.run("""
            MATCH (n)
            RETURN
                id(n)                         AS id,
                labels(n)[0]                  AS type,
                coalesce(n.isbn, '')           AS isbn,
                coalesce(n.title, '')          AS title,
                coalesce(n.authors, '')        AS authors,
                coalesce(n.publisher, '')      AS publisher,
                coalesce(n.published_year, '') AS published_year,
                coalesce(n.cover, '')          AS cover,
                coalesce(n.spine_image, '')    AS spine_image,
                coalesce(n.description, '')    AS description,
                coalesce(n.pages, 0)           AS pages,
                coalesce(n.height_mm, 0)       AS height_mm,
                coalesce(n.name, '')           AS name,
                coalesce(n.code, '')           AS code,
                coalesce(n.level, 0)           AS level,
                coalesce(n.text, '')           AS text
        """)
        nodes = [dict(r) for r in nodes_result]

        links_result = session.run("""
            MATCH (a)-[r]->(b)
            RETURN id(a) AS source, id(b) AS target, type(r) AS type
        """)
        links = [
            {"source": r["source"], "target": r["target"], "type": r["type"]}
            for r in links_result
        ]

        return {"nodes": nodes, "links": links}


# ============================================================
# 知識グラフの俯瞰分析（AIによる提案）
# ============================================================

def _clean(text: str) -> str:
    """改行・連続空白をスペース1個にまとめる（プロンプトの行構造が崩れないように）。"""
    return re.sub(r"\s+", " ", text).strip() if text else ""


def _build_analysis_prompt(overview: dict) -> str:
    lines = [
        "あなたは読書家の蔵書を分析するアシスタントです。",
        "以下はユーザーの蔵書ナレッジグラフ（Neo4j）から抽出した統計情報です。",
        "この情報を俯瞰し、ユーザー自身では気づきにくい傾向・偏り・つながりを見つけて、",
        "今後の読書や本棚整理に役立つ提案を3〜4個、日本語で簡潔に提示してください。",
        "NDCによる分類上の近さだけでなく、各本の概要（description）や著者・出版社、",
        "ユーザーが付けた意味づけメモの内容にも着目し、ジャンルを横断した意味的なつながりも積極的に見つけてください。",
        "",
        f"総冊数: {overview['total_books']}冊",
        "",
        "【NDC分類の内訳（上位カテゴリ別）】",
    ]
    for row in overview["ndc_distribution"]:
        name = NDC_L1.get(row["ndc_l1"], row["ndc_l1"] or "不明")
        titles = "、".join(row["sample_titles"])
        lines.append(f"- {name}: {row['book_count']}冊（例: {titles}）")

    lines.append("")
    lines.append("【複数の本に共通する意味づけ（テーマクラスタ）】")
    if overview["concept_clusters"]:
        for row in overview["concept_clusters"]:
            titles = "、".join(row["titles"])
            lines.append(f"- 「{row['concept']}」({row['book_count']}冊): {titles}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【複数冊持っている著者】")
    if overview["favorite_authors"]:
        for row in overview["favorite_authors"]:
            titles = "、".join(row["titles"])
            lines.append(f"- {row['author']}({row['book_count']}冊): {titles}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【他の本と意味的なつながりがまだない本（孤立している本）】")
    if overview["isolated_books"]:
        for row in overview["isolated_books"]:
            desc = _clean(row["description"])[:50]
            suffix = f"（概要: {desc}...）" if desc else ""
            lines.append(f"- [{row['isbn']}] {row['title']}{suffix}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【ユーザーが本に付けた意味づけ・感想メモ】")
    if overview["book_meanings"]:
        for row in overview["book_meanings"]:
            lines.append(f"- {row['title']}: 「{_clean(row['meaning'])}」")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【蔵書の書誌情報一覧（ISBN・著者・概要）】")
    if overview["book_catalog"]:
        for row in overview["book_catalog"]:
            desc = _clean(row["description"])[:35]
            author = (row["authors"] or "").split(",")[0] or "著者不明"
            suffix = f": {desc}" if desc else ""
            lines.append(f"- [{row['isbn']}] {row['title']}（{author}）{suffix}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append(
        "各提案について、その提案の根拠となった本のISBNを related_isbns に1〜5冊程度含めてください。"
    )
    lines.append(
        "related_isbns には上記リストの [ ] 内にあるISBNの文字列のみを使い、関連本が特定できない提案では空配列にしてください。"
    )
    lines.append(
        "出力は次のJSONオブジェクトの形式のみとし、前置きや説明文、コードブロック記法は付けないでください。"
    )
    lines.append(
        '{"proposals": [{"title": "提案の短い見出し", "description": "1〜2文の簡潔な説明", "related_isbns": ["isbn1", "isbn2"]}, ...]}'
    )
    return "\n".join(lines)


def _parse_proposals(raw: str, valid_isbns: set[str]) -> list[dict]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    # モデルが前後に余計な文章・句読点を付け足すことがあるため、
    # JSON本体らしき範囲だけを取り出す
    obj_start, obj_end = text.find("{"), text.rfind("}")
    arr_start, arr_end = text.find("["), text.rfind("]")
    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        candidate = text[obj_start:obj_end + 1]
    elif arr_start != -1 and arr_end != -1 and arr_end > arr_start:
        candidate = text[arr_start:arr_end + 1]
    else:
        candidate = text

    try:
        data = json.loads(candidate)
        items = data.get("proposals") if isinstance(data, dict) else data
        if isinstance(items, list):
            proposals = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_isbns = item.get("related_isbns") or []
                if not isinstance(raw_isbns, list):
                    raw_isbns = []
                related_isbns = [i for i in raw_isbns if isinstance(i, str) and i in valid_isbns]
                proposals.append({
                    "title": str(item.get("title", "")),
                    "description": str(item.get("description", "")),
                    "related_isbns": related_isbns,
                })
            return proposals
    except (json.JSONDecodeError, AttributeError):
        pass
    # パースに失敗した場合は生テキストをそのまま1件の提案として返す
    return [{"title": "分析結果", "description": text, "related_isbns": []}]


@router.post("/analyze")
def analyze_graph(db: Session = Depends(get_db)):
    shelf_isbns = [r[0] for r in db.query(ShelfLayout.isbn).all()]
    if not shelf_isbns:
        raise HTTPException(status_code=400, detail="本棚に本が並んでいません")

    overview = get_graph_overview(shelf_isbns=shelf_isbns)
    if overview["total_books"] == 0:
        raise HTTPException(status_code=400, detail="本棚に本がありません")

    prompt = _build_analysis_prompt(overview)
    try:
        raw = _llm.generate_json(prompt, max_tokens=1000)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"分析に失敗しました: {e}")

    valid_isbns = {row["isbn"] for row in overview["book_catalog"] if row.get("isbn")}
    proposals = _parse_proposals(raw, valid_isbns)
    return {"proposals": proposals, "stats": overview}
