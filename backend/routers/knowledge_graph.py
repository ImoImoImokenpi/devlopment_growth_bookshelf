import json
import random
import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from admin_neo4j.neo4j_driver import get_session
from admin_neo4j.neo4j_crud import get_graph_overview, get_book_relations, get_book_edges, get_subgraph_for_isbns
from utils.llm_provider import get_llm_client
from utils.network_analysis import analyze_book_network
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


@router.get("/book/{isbn}")
def get_book_detail(isbn: str):
    """本棚で本をタップした時の詳細パネル用：書誌情報＋関連本（理由付き）＋部分グラフ"""
    data = get_book_relations(isbn)
    if not data:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    return data


class SubgraphRequest(BaseModel):
    isbns: list[str]


@router.post("/subgraph")
def get_subgraph(body: SubgraphRequest):
    """複数冊(本棚のAI分析の提案など)を対象に、その本たち同士のつながりだけの部分グラフを返す"""
    return get_subgraph_for_isbns(body.isbns)


# ============================================================
# 知識グラフの俯瞰分析（AIによる提案）
# ============================================================

def _clean(text: str) -> str:
    """改行・連続空白をスペース1個にまとめる（プロンプトの行構造が崩れないように）。"""
    return re.sub(r"\s+", " ", text).strip() if text else ""


def _build_network_section(network: dict) -> list[str]:
    lines = ["", "【NetworkXによる蔵書ネットワークの構造分析】"]
    stats = network["graph_stats"]
    lines.append(
        f"- 分析対象: {stats['num_nodes']}冊 / つながり{stats['num_edges']}本 / "
        f"孤立クラスタ数{stats['num_components']} / 密度{stats['density']}"
    )

    lines.append("")
    lines.append("【ハブとなっている本（多くの本とつながりを持つ中心的な1冊）】")
    if network["hub_books"]:
        for b in network["hub_books"]:
            lines.append(f"- [{b['isbn']}] {b['title']}（中心性: {b['degree_centrality']}）")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【コミュニティ検出によるテーマクラスタ】")
    if network["communities"]:
        for c in network["communities"][:5]:
            titles = "、".join(b["title"] for b in c["books"][:4])
            lines.append(f"- クラスタ{c['id']}（{c['size']}冊）: {titles}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【橋渡し役の本（除くとクラスタが分断される本）】")
    if network["bridge_books"]:
        for b in network["bridge_books"][:5]:
            lines.append(f"- [{b['isbn']}] {b['title']}")
    else:
        lines.append("- なし")

    return lines


def _build_stats_context(overview: dict, network: dict) -> list[str]:
    """会話向けの軽量な分析コンテキスト（/analyze の詳細版と違い、トークン数を抑えるため
    書誌一覧・孤立本の列挙は含めない）。"""
    lines = [f"総冊数: {overview['total_books']}冊", "", "【NDC分類の内訳】"]
    for row in overview["ndc_distribution"][:6]:
        name = NDC_L1.get(row["ndc_l1"], row["ndc_l1"] or "不明")
        lines.append(f"- {name}: {row['book_count']}冊")

    lines.append("")
    lines.append("【複数の本に共通する意味づけ】")
    if overview["concept_clusters"]:
        for row in overview["concept_clusters"][:6]:
            items = list(zip(row["isbns"][:4], row["titles"][:4]))
            titles = "、".join(f"[{isbn}]{title}" for isbn, title in items)
            lines.append(f"- 「{row['concept']}」({row['book_count']}冊): {titles}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【複数冊持っている著者】")
    if overview["favorite_authors"]:
        for row in overview["favorite_authors"][:6]:
            items = list(zip(row["isbns"][:3], row["titles"][:3]))
            titles = "、".join(f"[{isbn}]{title}" for isbn, title in items)
            lines.append(f"- {row['author']}({row['book_count']}冊): {titles}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【ユーザーが本に付けた意味づけ・感想メモ】")
    if overview["book_meanings"]:
        for row in overview["book_meanings"][:8]:
            meaning = _clean(row["meaning"])[:50]
            lines.append(f"- [{row['isbn']}] {row['title']}: 「{meaning}」")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【NetworkXによる構造分析：ハブとなる本】")
    if network["hub_books"]:
        for b in network["hub_books"][:5]:
            lines.append(f"- [{b['isbn']}] {b['title']}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【コミュニティ検出によるテーマクラスタ】")
    if network["communities"]:
        for c in network["communities"][:4]:
            titles = "、".join(f"[{b['isbn']}]{b['title']}" for b in c["books"][:4])
            lines.append(f"- クラスタ{c['id']}（{c['size']}冊）: {titles}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【橋渡し役の本】")
    if network["bridge_books"]:
        for b in network["bridge_books"][:4]:
            lines.append(f"- [{b['isbn']}] {b['title']}")
    else:
        lines.append("- なし")

    return lines


def _collect_context_isbns(overview: dict, network: dict) -> set[str]:
    """chat用コンテキストに実際に登場した本のISBN集合（related_isbnsの検証に使う）。"""
    isbns: set[str] = set()
    for row in overview["concept_clusters"]:
        isbns.update(row.get("isbns") or [])
    for row in overview["favorite_authors"]:
        isbns.update(row.get("isbns") or [])
    for row in overview["book_meanings"]:
        if row.get("isbn"):
            isbns.add(row["isbn"])
    for b in network["hub_books"]:
        isbns.add(b["isbn"])
    for c in network["communities"]:
        for b in c["books"]:
            isbns.add(b["isbn"])
    for b in network["bridge_books"]:
        isbns.add(b["isbn"])
    return isbns


# ============================================================
# 対話開始時の話題選定（12パターンのプレースホルダーから、
# その蔵書で特に「気になる」ものをスコアで選ぶ）
# ============================================================

def _pick_hub_book(overview: dict, network: dict) -> dict | None:
    books = network.get("hub_books") or []
    if not books:
        return None
    top = books[0]
    return {
        "id": "hub_book",
        "score": (top.get("degree_centrality") or 0) * 10 + 1,
        "isbns": [top["isbn"]],
        "fact": f"「{top['title']}」は、蔵書の中で他の多くの本とテーマ的につながる中心的な1冊になっています。",
    }


def _pick_bridge_book(overview: dict, network: dict) -> dict | None:
    books = network.get("bridge_books") or []
    if not books:
        return None
    top = books[0]
    return {
        "id": "bridge_book",
        "score": 6,
        "isbns": [top["isbn"]],
        "fact": f"「{top['title']}」を取り除くと、蔵書のつながりが分断されてしまう、橋渡し役の本になっています。",
    }


def _pick_community(overview: dict, network: dict, *, largest: bool) -> dict | None:
    communities = network.get("communities") or []
    if not communities:
        return None
    biggest = max(communities, key=lambda c: c["size"])
    if largest:
        target = biggest
    else:
        if len(communities) < 2:
            return None
        target = min(communities, key=lambda c: c["size"])
        if target["id"] == biggest["id"]:
            return None
    isbns = [b["isbn"] for b in target["books"][:5]]
    titles = "、".join(b["title"] for b in target["books"][:4])
    label = "大きな" if largest else "小さな"
    return {
        "id": "biggest_community" if largest else "small_community",
        "score": target["size"] * (1.5 if largest else 0.8),
        "isbns": isbns,
        "fact": f"「{titles}」など{target['size']}冊が、{label}テーマクラスタとしてつながっています。",
    }


def _pick_concept_cluster(overview: dict, network: dict, *, largest: bool) -> dict | None:
    clusters = overview.get("concept_clusters") or []
    if not clusters:
        return None
    biggest = max(clusters, key=lambda c: c["book_count"])
    if largest:
        target = biggest
    else:
        if len(clusters) < 2:
            return None
        target = min(clusters, key=lambda c: c["book_count"])
        if target["concept"] == biggest["concept"]:
            return None
    isbns = list(target["isbns"])[:5]
    titles = "、".join(target["titles"][:4])
    return {
        "id": "concept_cluster" if largest else "rare_concept_cluster",
        "score": target["book_count"] * (1.3 if largest else 0.7),
        "isbns": isbns,
        "fact": f"ユーザーが「{target['concept']}」という意味づけをした本が{target['book_count']}冊あり、「{titles}」などがつながっています。",
    }


def _pick_favorite_author(overview: dict, network: dict) -> dict | None:
    authors = overview.get("favorite_authors") or []
    if not authors:
        return None
    top = max(authors, key=lambda a: a["book_count"])
    isbns = list(top["isbns"])[:5]
    titles = "、".join(top["titles"][:3])
    return {
        "id": "favorite_author",
        "score": top["book_count"] * 1.1,
        "isbns": isbns,
        "fact": f"{top['author']}の本を{top['book_count']}冊持っていて、「{titles}」などがあります。",
    }


def _pick_ndc(overview: dict, network: dict, *, dominant: bool) -> dict | None:
    dist = overview.get("ndc_distribution") or []
    if not dist:
        return None
    target = max(dist, key=lambda r: r["book_count"]) if dominant else min(dist, key=lambda r: r["book_count"])
    if not dominant and target["book_count"] > 2:
        return None
    name = NDC_L1.get(target["ndc_l1"], target["ndc_l1"] or "不明")
    if dominant:
        fact = f"蔵書の中では「{name}」というジャンルが{target['book_count']}冊と一番多くなっています。"
    else:
        fact = f"「{name}」というジャンルは、蔵書の中でまだ{target['book_count']}冊だけです。"
    return {
        "id": "dominant_ndc" if dominant else "rare_ndc",
        "score": target["book_count"] * (0.9 if dominant else 0.5) + (0 if dominant else 3),
        "isbns": [],
        "fact": fact,
    }


def _pick_isolated_book(overview: dict, network: dict) -> dict | None:
    books = network.get("isolated_books") or []
    if not books:
        return None
    top = books[0]
    return {
        "id": "isolated_book",
        "score": 3,
        "isbns": [top["isbn"]],
        "fact": f"「{top['title']}」は、まだ他の本とのテーマ的なつながりが見つかっていません。",
    }


def _pick_book_meaning(overview: dict, network: dict) -> dict | None:
    meanings = overview.get("book_meanings") or []
    if not meanings:
        return None
    top = meanings[0]
    isbn = top.get("isbn")
    return {
        "id": "book_meaning",
        "score": 5,
        "isbns": [isbn] if isbn else [],
        "fact": f"ユーザーは「{top['title']}」について「{_clean(top['meaning'])[:40]}」という意味づけを書いていました。",
    }


def _pick_network_density(overview: dict, network: dict) -> dict | None:
    stats = network.get("graph_stats") or {}
    if not stats.get("num_nodes"):
        return None
    density = stats.get("density", 0)
    components = stats.get("num_components", 0)
    if density < 0.05:
        fact = f"蔵書全体で見ると、本同士のつながりはまだ{components}個のグループに分かれていて、あまり密ではないようです。"
    else:
        fact = f"蔵書全体がかなり密接につながっていて、{stats['num_nodes']}冊が{components}個のグループにまとまっています。"
    return {
        "id": "network_density",
        "score": 2,
        "isbns": [],
        "fact": fact,
    }


# 12パターンのプレースホルダー
_TOPIC_PATTERNS = [
    _pick_hub_book,
    _pick_bridge_book,
    lambda o, n: _pick_community(o, n, largest=True),
    lambda o, n: _pick_community(o, n, largest=False),
    lambda o, n: _pick_concept_cluster(o, n, largest=True),
    lambda o, n: _pick_concept_cluster(o, n, largest=False),
    _pick_favorite_author,
    lambda o, n: _pick_ndc(o, n, dominant=True),
    lambda o, n: _pick_ndc(o, n, dominant=False),
    _pick_isolated_book,
    _pick_book_meaning,
    _pick_network_density,
]


def _select_opening_topic(overview: dict, network: dict) -> dict | None:
    """12パターンのうち条件を満たすものを集め、スコア上位からランダムに1つ選ぶ
    （常に同じ話題にならないよう、上位3件の中から重み付き抽選する）。"""
    candidates = [r for pick in _TOPIC_PATTERNS if (r := pick(overview, network))]
    if not candidates:
        return None
    candidates.sort(key=lambda c: c["score"], reverse=True)
    top_candidates = candidates[:3]
    weights = [c["score"] + 0.1 for c in top_candidates]
    return random.choices(top_candidates, weights=weights, k=1)[0]


def _build_opening_prompt(fact: str) -> str:
    return "\n".join([
        "あなたは読書家の蔵書を分析し、対話しながら気づきを深めてくれる、気さくな伴走者です。",
        "以下は、ユーザーの蔵書ナレッジグラフから見つかった、ちょっと面白い事実です。",
        "",
        f"事実: {fact}",
        "",
        "この事実について、押しつけがましくなく、気さくにユーザーに話しかけてください。",
        "問いかけを1つ含め、日本語で2〜3文以内で。前置きや説明文は付けず、話しかける言葉だけを書いてください。",
    ])


def _build_chat_prompt(stats_lines: list[str], history: list, message: str | None) -> str:
    lines = [
        "あなたは読書家の蔵書を分析し、対話しながら気づきを深めてくれる、気さくな伴走者です。",
        "以下はユーザーの蔵書ナレッジグラフから抽出した分析結果です。これを根拠に会話してください。",
        "",
        *stats_lines,
        "",
    ]

    if not history and not message:
        lines.append("これから対話を始めます。")
        lines.append(
            "上記の分析結果の中から、ユーザーがまだ気づいていなさそうな傾向やつながりを1つ選んで話しかけてください。"
            "問いかけを1つ含め、日本語で2〜3文以内、堅苦しくない口調で。"
        )
    else:
        lines.append("これまでの対話:")
        for m in history:
            speaker = "ユーザー" if m.role == "user" else "あなた"
            lines.append(f"{speaker}: {m.text}")
        if message:
            lines.append(f"ユーザー: {message}")
        lines.append(
            "上記の分析結果を根拠にしながら、ユーザーの発言に応答してください。"
            "共感的に受け止めつつ、必要に応じて分析結果からの気づきを添え、日本語で2〜4文以内、問いかけを1つ添えてください。"
        )

    lines.append("")
    lines.append(
        "返答の中で具体的に触れた本、または関連が深い本があれば、そのISBNを related_isbns に1〜5冊程度含めてください。"
    )
    lines.append(
        "related_isbns には上記コンテキストの [ ] 内にあるISBNの文字列のみを使い、特に触れていなければ空配列にしてください。"
    )
    lines.append(
        "出力は次のJSONオブジェクトの形式のみとし、前置きや説明文、コードブロック記法は付けないでください。"
    )
    lines.append(
        '{"reply": "対話の返答文", "related_isbns": ["isbn1", "isbn2"]}'
    )
    return "\n".join(lines)


def _build_analysis_prompt(overview: dict, network: dict) -> str:
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
        for row in overview["isolated_books"][:10]:
            desc = _clean(row["description"])[:30]
            suffix = f"（概要: {desc}...）" if desc else ""
            lines.append(f"- [{row['isbn']}] {row['title']}{suffix}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【ユーザーが本に付けた意味づけ・感想メモ】")
    if overview["book_meanings"]:
        for row in overview["book_meanings"]:
            meaning = _clean(row["meaning"])[:60]
            lines.append(f"- {row['title']}: 「{meaning}」")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【蔵書の書誌情報一覧（ISBN・著者・概要）】")
    catalog = overview["book_catalog"]
    if catalog:
        CATALOG_LIMIT = 40
        for row in catalog[:CATALOG_LIMIT]:
            desc = _clean(row["description"])[:25]
            author = (row["authors"] or "").split(",")[0] or "著者不明"
            suffix = f": {desc}" if desc else ""
            lines.append(f"- [{row['isbn']}] {row['title']}（{author}）{suffix}")
        if len(catalog) > CATALOG_LIMIT:
            lines.append(f"…ほか{len(catalog) - CATALOG_LIMIT}冊")
    else:
        lines.append("- なし")

    lines.extend(_build_network_section(network))

    lines.append("")
    lines.append(
        "上記の「NetworkXによる蔵書ネットワークの構造分析」は実際のグラフ構造から機械的に算出した客観的な指標です。"
        "ハブとなる本やコミュニティ、橋渡し役の本についても積極的に言及し、提案の根拠として活用してください。"
    )
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


def _parse_chat_reply(raw: str, valid_isbns: set[str]) -> tuple[str, list[str]]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    obj_start, obj_end = text.find("{"), text.rfind("}")
    candidate = text[obj_start:obj_end + 1] if obj_start != -1 and obj_end > obj_start else text

    try:
        data = json.loads(candidate)
        reply = str(data.get("reply", "")).strip()
        raw_isbns = data.get("related_isbns") or []
        related_isbns = [i for i in raw_isbns if isinstance(i, str) and i in valid_isbns] if isinstance(raw_isbns, list) else []
        if reply:
            return reply, related_isbns
    except (json.JSONDecodeError, AttributeError):
        pass
    # パースに失敗した場合は生テキストをそのまま返す
    return text, []


class AnalysisChatMessage(BaseModel):
    role: str  # "user" | "ai"
    text: str


class AnalysisChatRequest(BaseModel):
    history: list[AnalysisChatMessage] = []
    message: str | None = None


@router.post("/analyze-chat")
def analyze_chat(body: AnalysisChatRequest, db: Session = Depends(get_db)):
    """知識グラフの分析結果を踏まえて、ユーザーとAIが対話する。
    history/message が両方空の場合は、AIから話題を切り出す「対話開始」として扱う。"""
    shelf_isbns = [r[0] for r in db.query(ShelfLayout.isbn).all()]
    if not shelf_isbns:
        raise HTTPException(status_code=400, detail="本棚に本が並んでいません")

    overview = get_graph_overview(shelf_isbns=shelf_isbns)
    if overview["total_books"] == 0:
        raise HTTPException(status_code=400, detail="本棚に本がありません")

    edges = get_book_edges(shelf_isbns=shelf_isbns)
    network = analyze_book_network(nodes=overview["book_catalog"], edges=edges)

    # 会話履歴が伸び続けてもトークン予算を圧迫しないよう、直近だけを渡す
    recent_history = body.history[-8:]

    # 対話開始（history/messageが両方空）は、12パターンから話題を1つ選び、
    # その事実だけを根拠にした軽量なプロンプトで話しかける
    if not recent_history and not body.message:
        topic = _select_opening_topic(overview, network)
        if topic is not None:
            prompt = _build_opening_prompt(topic["fact"])
            try:
                reply = _llm.generate_text(prompt, max_tokens=200).strip()
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"対話に失敗しました: {e}")
            return {"reply": reply, "related_isbns": topic["isbns"]}

    stats_lines = _build_stats_context(overview, network)
    valid_isbns = _collect_context_isbns(overview, network)
    prompt = _build_chat_prompt(stats_lines, recent_history, body.message)
    try:
        raw = _llm.generate_json(prompt, max_tokens=450)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"対話に失敗しました: {e}")

    reply, related_isbns = _parse_chat_reply(raw, valid_isbns)
    return {"reply": reply, "related_isbns": related_isbns}


@router.post("/analyze")
def analyze_graph(db: Session = Depends(get_db)):
    shelf_isbns = [r[0] for r in db.query(ShelfLayout.isbn).all()]
    if not shelf_isbns:
        raise HTTPException(status_code=400, detail="本棚に本が並んでいません")

    overview = get_graph_overview(shelf_isbns=shelf_isbns)
    if overview["total_books"] == 0:
        raise HTTPException(status_code=400, detail="本棚に本がありません")

    edges = get_book_edges(shelf_isbns=shelf_isbns)
    network = analyze_book_network(nodes=overview["book_catalog"], edges=edges)

    prompt = _build_analysis_prompt(overview, network)
    try:
        raw = _llm.generate_json(prompt, max_tokens=800)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"分析に失敗しました: {e}")

    valid_isbns = {row["isbn"] for row in overview["book_catalog"] if row.get("isbn")}
    proposals = _parse_proposals(raw, valid_isbns)
    return {"proposals": proposals, "stats": overview, "network": network}
