import json
import os
import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from admin_neo4j.neo4j_driver import get_session
from admin_neo4j.neo4j_crud import (
    get_graph_overview, get_book_relations, get_book_concepts, get_book_basic, save_book_impression,
    get_book_impressions, get_book_edges, get_subgraph_for_isbns, get_full_graph,
    count_concept_nodes, get_latest_concept_topic, confirm_concept_edge,
    save_discoveries, record_discovery_feedback, list_discoveries,
    get_answered_discovery_questions, query_co_occurrence_pairs, get_growth_stats,
)
from utils.llm_provider import get_llm_client
from utils.network_analysis import analyze_book_network
from utils.shelf_pattern_analysis import analyze_shelf_patterns
from database import get_db
from participant import resolve_participant_id
from models import ShelfLayout, RegisteredBook, ShelfDesign

router = APIRouter(prefix="/knowledge_graph")

_llm = get_llm_client()

# ユーザーが自由に付けた意味づけ（Concept）が、これだけ新しく増えるたびに
# 本棚側から強制的に話しかける（対話が完全に受け身にならないようにするため）
CONCEPT_WHISPER_THRESHOLD = 3

NDC_L1 = {
    "0": "総記", "1": "哲学", "2": "歴史・地理", "3": "社会科学",
    "4": "自然科学", "5": "技術", "6": "産業", "7": "芸術", "8": "言語", "9": "文学",
}

# 設計書5章のLLM発見エンジンが扱う4種類の発見
DISCOVERY_TYPES = {"commonality", "contradiction", "implicit_pattern", "structural"}

# 分析プロンプトに載せる書誌一覧の上限。
# 小さめのモデル（Groqの無料枠など）では入力トークンの上限に当たりやすく、
# 蔵書が増えるほどここが最初に溢れる。ANALYSIS_CATALOG_LIMIT で調整できる。
CATALOG_LIMIT = int(os.environ.get("ANALYSIS_CATALOG_LIMIT", "24"))

@router.get("/")
def get_graph(participant_id: str = Depends(resolve_participant_id)):
    """その被験者の知識グラフだけを返す。
    以前はDB全体を返していたため、被験者が増えると他人のグラフが混ざっていた。"""
    return get_full_graph(participant_id)


@router.get("/book/{isbn}")
def get_book_detail(isbn: str, participant_id: str = Depends(resolve_participant_id)):
    """本棚で本をタップした時の詳細パネル用：書誌情報＋関連本（理由付き）＋部分グラフ"""
    data = get_book_relations(isbn, participant_id=participant_id)
    if not data:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    return data


@router.get("/book/{isbn}/concepts")
def get_book_concepts_endpoint(isbn: str, participant_id: str = Depends(resolve_participant_id)):
    """本棚でカーソルを合わせた時のホバー強調用：
    その本の意味づけ(Concept)一覧と、それぞれを共有する本のISBNを返す。"""
    return {"concepts": get_book_concepts(isbn, participant_id=participant_id)}


@router.get("/book/{isbn}/basic")
def get_book_basic_endpoint(isbn: str, participant_id: str = Depends(resolve_participant_id)):
    """コンパクトな詳細パネル用：書誌情報と感想のみを返す（関連本の探索はしない）。"""
    data = get_book_basic(isbn, participant_id=participant_id)
    if not data:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    return data


class ImpressionRequest(BaseModel):
    text: str


@router.post("/book/{isbn}/impression")
def save_book_impression_endpoint(
    isbn: str,
    body: ImpressionRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """意味づけ(Concept)とは別に、1冊ごとの個人的な感想を保存する。
    上書きではなく追記なので、感想の変遷が履歴として残る。"""
    save_book_impression(isbn, body.text, participant_id=participant_id)
    return {"ok": True}


@router.get("/book/{isbn}/impressions")
def get_book_impressions_endpoint(isbn: str, participant_id: str = Depends(resolve_participant_id)):
    """1冊に対する感想の履歴（設計書3.1の personal_notes[] に相当）。"""
    return {"impressions": get_book_impressions(isbn, participant_id=participant_id)}


class SubgraphRequest(BaseModel):
    isbns: list[str]


@router.post("/subgraph")
def get_subgraph(
    body: SubgraphRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """複数冊(本棚のAI分析の提案など)を対象に、その本たち同士のつながりだけの部分グラフを返す"""
    return get_subgraph_for_isbns(body.isbns, participant_id=participant_id)


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


def _fetch_shelf_rows(db: Session, participant_id: str) -> dict[int, list[dict]]:
    """本棚の物理配置（高さ・ジャンル・色・著者など）をshelf_index別に集める。
    並べ方ルールの機械的な検出（shelf_pattern_analysis）の入力になる。"""
    rows = (
        db.query(ShelfLayout, RegisteredBook)
        .join(RegisteredBook, RegisteredBook.isbn == ShelfLayout.isbn)
        .filter(ShelfLayout.participant_id == participant_id)
        .all()
    )
    shelves: dict[int, list[dict]] = {}
    for layout, book in rows:
        shelves.setdefault(layout.shelf_index, []).append({
            "isbn": layout.isbn,
            "title": book.title,
            "shelf_index": layout.shelf_index,
            "x_pos": layout.x_pos,
            "height_mm": layout.height_mm or book.height_mm,
            "pages": layout.pages or book.pages,
            "ndc": book.ndc,
            "authors": book.authors,
            "spine_color": book.spine_color,
        })
    return shelves


def _build_shelf_pattern_section(shelf_patterns: dict) -> list[str]:
    lines = ["", "【本棚の物理的な配置から機械的に検出された、並べ方のルール】"]
    findings = shelf_patterns["findings"]
    if findings:
        for f in findings:
            lines.append(f"- [{f['label']}] {f['fact']}")
    else:
        lines.append("- 特に強いルールは検出されませんでした。")

    lines.append("")
    lines.append("【並べ方のルールとして考えられる12パターン（参考。検出されていないものも含む）】")
    for i, p in enumerate(shelf_patterns["reference_patterns"], start=1):
        lines.append(f"{i}. {p}")

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


def _ensure_trailing_question(text: str) -> str:
    """LLMが指示を無視して問いかけを付け忘れた場合の保険。
    既に「？」「?」があればそのまま返し、無ければ最後に補う。"""
    text = text.strip()
    if "？" in text or "?" in text:
        return text
    return f"{text.rstrip('。')}。ここまで読んで、どう感じますか？"


def _build_opening_prompt(fact: str, intent: str) -> str:
    return "\n".join([
        "あなたは読書家の蔵書を分析し、対話しながら気づきを深めてくれる、気さくな伴走者です。",
        "以下は、ユーザーの蔵書ナレッジグラフから見つかった、ちょっと面白い事実です。",
        "",
        f"事実: {fact}",
        f"聞きたいこと: {intent}",
        "",
        "上記の「聞きたいこと」を意識しつつ、押しつけがましくなく、気さくにユーザーに話しかけてください。",
        "日本語で2〜3文以内、前置きや説明文は付けず、話しかける言葉だけを書いてください。",
        "【重要】必ず最後の1文をユーザーへの問いかけにし、文末を「？」で終えてください。問いかけの無い返答は不可です。",
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
            "日本語で2〜3文以内、堅苦しくない口調で。"
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
            "共感的に受け止めつつ、必要に応じて分析結果からの気づきを添え、日本語で2〜4文以内で応答してください。"
        )

    lines.append("")
    lines.append(
        "【重要】reply の最後の1文は必ずユーザーへの問いかけにし、文末を「？」で終えてください。問いかけの無い返答は不可です。"
    )
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


def _build_co_occurrence_section(co_occurrence: list[dict]) -> list[str]:
    """繰り返し隣り合わせに置き直されている本のペア。
    ユーザーが言葉にしていない関連（設計書5章の未言語化パターン）の手がかり。"""
    lines = ["", "【何度も隣り合わせに置き直されている本のペア（本人が言語化していない関連の可能性）】"]
    if co_occurrence:
        for row in co_occurrence[:5]:
            lines.append(
                f"- [{row['source_isbn']}]{row['source_title']} ↔ "
                f"[{row['target_isbn']}]{row['target_title']}（{row['co_occurrence_count']}回）"
            )
    else:
        lines.append("- まだ十分な配置の履歴がありません。")
    return lines


def _build_asked_questions_section(asked_questions: list[str]) -> list[str]:
    if not asked_questions:
        return []
    lines = ["", "【すでにユーザーへ提示済みの問いかけ（同じ内容を繰り返さないこと）】"]
    lines.extend(f"- {q}" for q in asked_questions[:6])
    return lines


def _build_analysis_prompt(
    overview: dict,
    network: dict,
    shelf_patterns: dict,
    co_occurrence: list[dict] | None = None,
    asked_questions: list[str] | None = None,
) -> str:
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
        for row in overview["concept_clusters"][:6]:
            titles = "、".join(row["titles"][:4])
            lines.append(f"- 「{row['concept']}」({row['book_count']}冊): {titles}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【複数冊持っている著者】")
    if overview["favorite_authors"]:
        for row in overview["favorite_authors"][:5]:
            titles = "、".join(row["titles"][:3])
            lines.append(f"- {row['author']}({row['book_count']}冊): {titles}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【他の本と意味的なつながりがまだない本（孤立している本）】")
    if overview["isolated_books"]:
        for row in overview["isolated_books"][:6]:
            lines.append(f"- [{row['isbn']}] {row['title']}")
    else:
        lines.append("- なし")

    lines.append("")
    lines.append("【ユーザーが本に付けた意味づけ・感想メモ】")
    if overview["book_meanings"]:
        for row in overview["book_meanings"][:8]:
            meaning = _clean(row["meaning"])[:40]
            lines.append(f"- {row['title']}: 「{meaning}」")
    else:
        lines.append("- なし")

    # 書誌一覧は提案がISBNを引くための索引なので、概要は落として冊数も絞る。
    # ここが一番かさむため、モデルの入力上限に当たるときは真っ先に削る対象。
    lines.append("")
    lines.append("【蔵書の書誌情報一覧（ISBN・タイトル・著者）】")
    catalog = overview["book_catalog"]
    if catalog:
        for row in catalog[:CATALOG_LIMIT]:
            author = (row["authors"] or "").split(",")[0] or "著者不明"
            lines.append(f"- [{row['isbn']}] {row['title']}（{author}）")
        if len(catalog) > CATALOG_LIMIT:
            lines.append(f"…ほか{len(catalog) - CATALOG_LIMIT}冊")
    else:
        lines.append("- なし")

    lines.extend(_build_network_section(network))
    lines.extend(_build_shelf_pattern_section(shelf_patterns))
    lines.extend(_build_co_occurrence_section(co_occurrence or []))
    lines.extend(_build_asked_questions_section(asked_questions or []))

    lines.append("")
    lines.append(
        "上記の「NetworkXによる蔵書ネットワークの構造分析」は実際のグラフ構造から機械的に算出した客観的な指標です。"
        "ハブとなる本やコミュニティ、橋渡し役の本についても積極的に言及し、提案の根拠として活用してください。"
    )
    lines.append(
        "「本棚の物理的な配置から機械的に検出された、並べ方のルール」については、断定せず"
        "「〜のように見えますが、意識されていますか？」のように、実際にユーザーが意識しているか確認する提案を1つ以上含めてください。"
        "また、機械的には検出されなかったが、ジャンル・著者・色・高さなどの書誌情報から新たに見つかる並べ方の工夫やつながりがあれば、"
        "12パターンの参考リストも手がかりにしながら積極的に提案してください。"
    )
    lines.append(
        "各提案について、その提案の根拠となった本のISBNを related_isbns に1〜5冊程度含めてください。"
    )
    lines.append(
        "related_isbns には上記リストの [ ] 内にあるISBNの文字列のみを使い、関連本が特定できない提案では空配列にしてください。"
    )
    lines.append(
        "各提案には discovery_type を付けてください。値は次の4つのいずれかです。"
        "commonality（複数の本に共通する要素の発見）、"
        "contradiction（意味づけと実際の配置の食い違い）、"
        "implicit_pattern（本人が言語化していない配置の癖）、"
        "structural（グラフ構造からの発見）。"
    )
    # 質問カードは本棚の上に吹き出しとして出るので、見出しではなく
    # そのまま出せる短い問いかけ文が要る。Yes/Noで一次応答できる形にする。
    lines.append(
        "さらに各提案には question を付けてください。question は本棚がユーザーに話しかける"
        "短い問いかけ文（40字以内）で、必ず「？」で終え、"
        "「はい／いいえ」で一次的に答えられる聞き方にしてください。"
        "例:「この3冊、共通しているのは“仕事の道具”という感覚ですか？」"
    )
    lines.append(
        "出力は次のJSONオブジェクトの形式のみとし、前置きや説明文、コードブロック記法は付けないでください。"
    )
    lines.append(
        '{"proposals": [{"title": "提案の短い見出し", "description": "1〜2文の簡潔な説明", '
        '"question": "ユーザーへの短い問いかけ？", '
        '"discovery_type": "commonality", "related_isbns": ["isbn1", "isbn2"]}, ...]}'
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
                discovery_type = str(item.get("discovery_type", "")).strip()
                if discovery_type not in DISCOVERY_TYPES:
                    discovery_type = "structural"
                title = str(item.get("title", ""))
                proposals.append({
                    "title": title,
                    "description": str(item.get("description", "")),
                    # 問いかけを出し忘れた場合は見出しから作る（カードが空にならないように）
                    "question": _ensure_trailing_question(str(item.get("question", "")) or title),
                    "discovery_type": discovery_type,
                    "related_isbns": related_isbns,
                })
            return proposals
    except (json.JSONDecodeError, AttributeError):
        pass
    # パースに失敗した場合は生テキストをそのまま1件の提案として返す
    return [{
        "title": "分析結果",
        "description": text,
        "question": _ensure_trailing_question(text[:60]),
        "discovery_type": "structural",
        "related_isbns": [],
    }]


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


@router.get("/forced-whisper")
def get_forced_whisper(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """ユーザーが自由に付けた意味づけ（Concept）が閾値分だけ増えていたら、
    タップを待たずに本棚側から強制的に話しかける開始メッセージを生成する。
    一度話しかけたら、次に閾値分また増えるまでは再度話しかけない。"""
    design = (
        db.query(ShelfDesign)
        .filter(ShelfDesign.participant_id == participant_id)
        .first()
    )
    if not design:
        return {"forced": False}

    current_count = count_concept_nodes(participant_id)
    last_count = design.last_forced_concept_count or 0
    if current_count - last_count < CONCEPT_WHISPER_THRESHOLD:
        return {"forced": False}

    topic = get_latest_concept_topic(participant_id)
    if not topic or not topic.get("isbns"):
        # 意味づけの実体（本との紐付け）が見つからない場合もカウントは進め、無限に問い合わせが続くのを防ぐ
        design.last_forced_concept_count = current_count
        db.commit()
        return {"forced": False}

    anchor_isbn = topic["isbns"][0]
    titles = "、".join(topic["titles"][:4])
    fact = (
        f"ユーザーはこれまでに数多くの意味づけを本棚に重ねてきました。"
        f"直近では「{titles}」などに「{topic['concept']}」という意味づけがされています。"
    )
    intent = "積み重ねてきた意味づけ全体を振り返って本棚側から気づいたことを伝え、それらの意味づけがどうつながっているかを尋ねる。"

    prompt = _build_opening_prompt(fact, intent)
    try:
        reply = _ensure_trailing_question(_llm.generate_text(prompt, max_tokens=200).strip())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"対話に失敗しました: {e}")

    design.last_forced_concept_count = current_count
    db.commit()

    return {
        "forced": True,
        "isbn": anchor_isbn,
        "title": topic["titles"][0] if topic["titles"] else None,
        "topic_id": "forced_reflection",
        "reply": reply,
        "related_isbns": topic["isbns"][:5],
    }


class BookChatRequest(BaseModel):
    # 応答は棚全体の分析を根拠にするため、特定の本に紐づかない対話でも呼べる。
    # 2ペイン構成では右ペインに常設の対話パネルがあり、本を選ばずに話し始められる。
    isbn: str | None = None
    topic_id: str | None = None
    history: list[AnalysisChatMessage] = []
    message: str | None = None


@router.post("/book-chat")
def book_chat(
    body: BookChatRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """本棚からの強制対話（forced-whisper）の続きに応答する。
    開始の一言はforced-whisper側で生成済みのため、ここでは棚全体の分析結果を根拠に応答するのみ。"""
    shelf_isbns = [
        r[0] for r in db.query(ShelfLayout.isbn)
                        .filter(ShelfLayout.participant_id == participant_id).all()
    ]
    if not shelf_isbns:
        raise HTTPException(status_code=400, detail="本棚に本が並んでいません")

    overview = get_graph_overview(participant_id, shelf_isbns=shelf_isbns)
    if overview["total_books"] == 0:
        raise HTTPException(status_code=400, detail="本棚に本がありません")

    edges = get_book_edges(participant_id, shelf_isbns=shelf_isbns)
    network = analyze_book_network(nodes=overview["book_catalog"], edges=edges)

    # 会話履歴が伸び続けてもトークン予算を圧迫しないよう、直近だけを渡す
    recent_history = body.history[-8:]

    stats_lines = _build_stats_context(overview, network)
    valid_isbns = _collect_context_isbns(overview, network)
    prompt = _build_chat_prompt(stats_lines, recent_history, body.message)
    try:
        raw = _llm.generate_json(prompt, max_tokens=450)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"対話に失敗しました: {e}")

    reply, related_isbns = _parse_chat_reply(raw, valid_isbns)
    return {"reply": _ensure_trailing_question(reply), "related_isbns": related_isbns}


@router.post("/analyze")
def analyze_graph(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    shelf_isbns = [
        r[0] for r in db.query(ShelfLayout.isbn)
                        .filter(ShelfLayout.participant_id == participant_id).all()
    ]
    if not shelf_isbns:
        raise HTTPException(status_code=400, detail="本棚に本が並んでいません")

    overview = get_graph_overview(participant_id, shelf_isbns=shelf_isbns)
    if overview["total_books"] == 0:
        raise HTTPException(status_code=400, detail="本棚に本がありません")

    edges = get_book_edges(participant_id, shelf_isbns=shelf_isbns)
    network = analyze_book_network(nodes=overview["book_catalog"], edges=edges)

    shelf_rows = _fetch_shelf_rows(db, participant_id)
    memo_isbns = {row["isbn"] for row in overview["book_meanings"] if row.get("isbn")}
    shelf_patterns = analyze_shelf_patterns(shelf_rows, memo_isbns=memo_isbns)

    # 繰り返し隣り合わせに置き直されている本のペア（未言語化パターンの材料）
    co_occurrence = query_co_occurrence_pairs(participant_id)

    prompt = _build_analysis_prompt(
        overview, network, shelf_patterns,
        co_occurrence=co_occurrence,
        asked_questions=get_answered_discovery_questions(participant_id),
    )
    try:
        raw = _llm.generate_json(prompt, max_tokens=800)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"分析に失敗しました: {e}")

    valid_isbns = {row["isbn"] for row in overview["book_catalog"] if row.get("isbn")}
    proposals = _parse_proposals(raw, valid_isbns)

    # 発見を永続化する（設計書3.3）。以前はここで捨てていたため、
    # status も納得度・驚き度のフィードバックも残らなかった。
    saved = save_discoveries(
        [
            {
                "type": p.get("discovery_type") or "structural",
                "title": p["title"],
                "generated_question": p["question"],
                "body": p["description"],
                "related_book_ids": p["related_isbns"],
            }
            for p in proposals
        ],
        participant_id=participant_id,
    )
    for proposal, record in zip(proposals, saved):
        proposal["discovery_id"] = record["discovery_id"]

    return {
        "proposals": proposals,
        "stats": overview,
        "network": network,
        "shelf_patterns": shelf_patterns,
        "co_occurrence": co_occurrence,
    }


# ============================================================
# Discovery のフィードバック収集（設計書7.3）
# ============================================================

class DiscoveryFeedbackRequest(BaseModel):
    status: str  # "confirmed" | "rejected" | "modified"
    surprise_score: float | None = None   # 驚き度
    agreement_score: float | None = None  # 納得度
    comment: str | None = None


@router.get("/growth")
def get_growth_endpoint(participant_id: str = Depends(resolve_participant_id)):
    """育成インジケータ（設計書6.4）の元になる量。
    画面側では数値を出さず、照明の強さに変換して見せる。"""
    return get_growth_stats(participant_id)


@router.get("/discoveries")
def list_discoveries_endpoint(
    status: str | None = None,
    participant_id: str = Depends(resolve_participant_id),
):
    return {"discoveries": list_discoveries(participant_id, status=status)}


@router.post("/discovery/{discovery_id}/feedback")
def discovery_feedback_endpoint(
    discovery_id: str,
    body: DiscoveryFeedbackRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    if body.status not in ("confirmed", "rejected", "modified", "pending"):
        raise HTTPException(status_code=400, detail="status が不正です")

    ok = record_discovery_feedback(
        discovery_id,
        participant_id=participant_id,
        status=body.status,
        surprise_score=body.surprise_score,
        agreement_score=body.agreement_score,
        comment=body.comment,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="発見が見つかりません")
    return {"ok": True}


class ConceptEdgeConfirmRequest(BaseModel):
    confirmed: bool


@router.post("/concept-edge/{edge_id}/confirm")
def confirm_concept_edge_endpoint(
    edge_id: str,
    body: ConceptEdgeConfirmRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """推測でついた意味づけエッジ(confidence: inferred)を、
    ユーザーのYes/Noで確定または否定する（設計書6.2の一次応答）。"""
    ok = confirm_concept_edge(edge_id, participant_id=participant_id, confirmed=body.confirmed)
    if not ok:
        raise HTTPException(status_code=404, detail="エッジが見つかりません")
    return {"ok": True}
