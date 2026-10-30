"""本棚対話 API。

ユーザーが並べ替えを終えて「対話」ボタンを押すと /dialogue/start が呼ばれる。
知識グラフ（今の本棚・前回の対話以降に動かした本・これまでの意味づけ）を
LLMに読ませ、並べ替えについての問いかけから会話を始める。

会話の中で持ち主が本どうしのつながりや置いた理由を語ると、LLMがそれを
「意味づけの候補」(MeaningProposal) として取り出す。持ち主が採用した候補だけが
Concept として知識グラフに書き込まれ、本棚が育っていく。
"""
import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from neo4j.exceptions import ServiceUnavailable
from pydantic import BaseModel

from graph.dialogue import store
from graph.main_kg.neo4j_crud import save_concept
from participant import resolve_participant_id
from utils.llm_modes import LLMDisabledError
from utils.llm_provider import get_llm_client, get_llm_mode

router = APIRouter(prefix="/dialogue")
logger = logging.getLogger(__name__)

_llm = get_llm_client()
_LLM_MODE = get_llm_mode()  # off / mock / live（起動時に決まる）
OFF_MESSAGE = "対話は停止中です（LLM_MODE=off）"

MAX_TRANSCRIPT_TURNS = 20
MAX_PROPOSALS = 4
MAX_MEANING_LEN = 30


# ============================================================
# 知識グラフ → LLM向けの文
# ============================================================

def _book_ids(books: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """本棚の本に B1, B2… の短いIDを振る（ISBNを直接扱わせると取り違えやすいため）。"""
    isbn_to_id = {b["isbn"]: f"B{i + 1}" for i, b in enumerate(books)}
    id_to_isbn = {v: k for k, v in isbn_to_id.items()}
    return isbn_to_id, id_to_isbn


def _label(book: dict, isbn_to_id: dict[str, str]) -> str:
    return f"{isbn_to_id[book['isbn']]}「{book.get('title') or '（書名不明）'}」"


def _color_name(spine_color: str | None) -> str | None:
    """背の代表色 "R,G,B" を、会話で使えるおおまかな色名にする。"""
    try:
        r, g, b = (int(float(x)) / 255 for x in str(spine_color).split(",")[:3])
    except (TypeError, ValueError):
        return None
    hi, lo = max(r, g, b), min(r, g, b)
    sat = 0 if hi == 0 else (hi - lo) / hi
    if hi < 0.3:
        return "黒"
    if sat < 0.15:
        return "白" if hi > 0.85 else "灰"
    d = hi - lo
    if hi == r:
        hue = 60 * (((g - b) / d) % 6)
    elif hi == g:
        hue = 60 * ((b - r) / d + 2)
    else:
        hue = 60 * ((r - g) / d + 4)
    if hue < 15 or hue >= 340:
        return "赤"
    if hue < 40:
        return "茶" if hi < 0.6 else "橙"
    if hue < 70:
        return "黄"
    if hue < 165:
        return "緑"
    if hue < 255:
        return "青"
    return "紫" if hue < 300 else "ピンク"


def _shelf_text(books: list[dict], isbn_to_id: dict[str, str]) -> str:
    lines = []
    current_shelf = None
    for b in books:
        if b["shelf_index"] != current_shelf:
            current_shelf = b["shelf_index"]
            lines.append(f"【上から{current_shelf + 1}段目（左から順に）】")
        details = []
        # 高さと背の色は本ごとの素のデータだけを渡す（配置分析のスコアなどは渡さない）
        if b.get("height_mm"):
            details.append(f"高さ{b['height_mm']}mm")
        color = _color_name(b.get("spine_color"))
        if color:
            details.append(f"背の色: {color}")
        if b.get("authors"):
            details.append("著者: " + "、".join(b["authors"]))
        if b.get("themes"):
            details.append("内容テーマ: " + "、".join(b["themes"]))
        if b.get("concepts"):
            details.append("持ち主の意味づけ: " + "、".join(b["concepts"]))
        suffix = f"（{' / '.join(details)}）" if details else ""
        lines.append(f"- {_label(b, isbn_to_id)}{suffix}")
    return "\n".join(lines)


def _neighbors(book: dict, books: list[dict]) -> tuple[dict | None, dict | None]:
    row = [b for b in books if b["shelf_index"] == book["shelf_index"]]
    i = row.index(book)
    left = row[i - 1] if i > 0 else None
    right = row[i + 1] if i < len(row) - 1 else None
    return left, right


def _move_line(m: dict, b: dict, books: list[dict], isbn_to_id: dict[str, str]) -> str:
    """1冊の移動を「どこからどこへ・今の両隣」の文にする。"""
    left, right = _neighbors(b, books)
    around = "、".join(_label(n, isbn_to_id) for n in (left, right) if n) or "両隣なし"
    src = m.get("from_pos") or {}
    if src.get("shelf_index") is not None and src.get("column_index") is not None:
        origin = f"上から{src['shelf_index'] + 1}段目の左から{src['column_index'] + 1}番目あたりから"
    else:
        origin = ""
    times = f"（{m['move_count']}回動かした）" if m.get("move_count", 1) > 1 else ""
    return (
        f"- {_label(b, isbn_to_id)} を{origin}上から{b['shelf_index'] + 1}段目へ動かした{times}"
        f"（今の両隣: {around}）"
    )


def _session_moves_text(moves: list[dict], books: list[dict], isbn_to_id: dict[str, str]) -> str:
    by_isbn = {b["isbn"]: b for b in books}
    lines = [_move_line(m, by_isbn[m["isbn"]], books, isbn_to_id) for m in moves if m["isbn"] in by_isbn]
    return "\n".join(lines) if lines else "（まだない）"


def _changes_text(changes: dict, books: list[dict], isbn_to_id: dict[str, str]) -> tuple[str, list[str]]:
    """前回の対話以降の変化を文にする。戻り値は (文, きっかけになった本のISBN)。"""
    by_isbn = {b["isbn"]: b for b in books}
    lines = []
    discussed = []

    added = [i for i in changes["added_isbns"] if i in by_isbn]
    for isbn in added:
        b = by_isbn[isbn]
        left, right = _neighbors(b, books)
        around = "、".join(_label(n, isbn_to_id) for n in (left, right) if n) or "両隣なし"
        lines.append(
            f"- {_label(b, isbn_to_id)} を新しく本棚に加え、上から{b['shelf_index'] + 1}段目に置いた"
            f"（今の両隣: {around}）"
        )
        discussed.append(isbn)

    for m in changes["moved"]:
        if m["isbn"] not in by_isbn or m["isbn"] in discussed:
            continue
        lines.append(_move_line(m, by_isbn[m["isbn"]], books, isbn_to_id))
        discussed.append(m["isbn"])

    if not lines:
        if changes["is_first_dialogue"]:
            return "（はじめての対話。まだ特定の並べ替えはないので、本棚全体を見て話しかける）", []
        return "（前回の対話から、本の並べ替えはない）", []
    return "\n".join(lines), discussed


# ============================================================
# システムプロンプト（対話のあいだ変わらない部分）
#   1つ目のブロック: 人物像・聞き方・締めくくり・意味づけ・出力のきまり（全対話で共通）
#   2つ目のブロック: 持ち主の本棚（知識グラフ）と対話のきっかけ（対話ごとに固定）
# 毎回変わる情報（会話の進み具合・対話中に動かした本・採用された意味づけ）は、
# 会話の最後に「運営からの補足」（会話途中のシステムメッセージ）として添える。
# ============================================================

SYSTEM_RULES = """あなたは、本棚の持ち主と一緒にその本棚を眺める、穏やかで好奇心のある聞き手です。
この対話の目的は、持ち主自身の言葉で次の2つを語ってもらうことです。
- 並べた理由・意図: なぜその本をそこに置いたのか、どんな基準や気持ちで並べているのか
- 本どうしのつながり: 隣り合う本や近くの本が、持ち主にとってどうつながっているのか

聞き方のきまり:
- 1回の発言は短く、1〜2文・60字程度まで。質問は1つだけ。
- 持ち主の言葉を受け止めるのはひと言だけにし、長く言い換えたり繰り返したりしない。
- 質問は上の2つのどちらかに向ける。「なぜここに？」「隣の〇〇とはどうつながりますか？」
  「この段にはどんな本を集めていますか？」のように、具体的な本や場所を指して聞く。
- 本は必ず書名で呼ぶ（B1 のようなIDは発言に出さない）。副題は省き、短く呼ぶ。
- あなたの解釈や本の内容の知識を先に言わない。持ち主が語る前に理由を当てにいかない。
- 持ち主の答えを否定せず、出てきた言葉をそのまま拾って、もう一歩だけ掘り下げる。
- 思い出や本の感想に話が広がったら、受け止めたうえで、並べ方やつながりの話に戻す。
- 「特に理由はない」「なんとなく」という答えも大事な答えとして受け止め、別の本や場所に話題を移す。
- 持ち主が高さ・色・見た目に触れたら、本の一覧の高さや背の色を見て、実際の並び
  （例: 右へ少しずつ低くなっている、同じ高さの本が続いている、白い背が集まっている）を
  ひと言で具体的に確かめてから、もう一歩掘り下げる。
- 持ち主が触れる前に、あなたから高さや色の並びを指摘しない。
- 数値や分析用語（スコア、クラスタ、カテゴリなど）は使わない。

最初のひと言のきまり:
- 挨拶はせず、すぐ問いかけに入る。
- 対話のきっかけ（並べ替えや新しく加えた本）があれば、その中から1冊（または隣り合わせの2冊）を選び、
  なぜそこに置いたのかを尋ねる。
- きっかけがないときは、持ち主の意図が表れていそうな段や隣り合わせを1つ選び、どんな考えで並べたのかを尋ねる。

締めくくりのきまり:
- 会話の最後に届く「運営からの補足」の「会話の進み具合」に従って、締めくくるかどうかを決める。
- 締めくくるときは質問をしない。この対話で持ち主が語った「並べた理由・意図」と「本どうしのつながり」を、
  持ち主の言葉を使って1〜2文で短く振り返り、お礼を伝える。
  意味づけの候補を出すときは、最後に「残したいものを下で選んでください。」と添える（候補がないときは添えない）。
  このとき done を true にする。それ以外は done を false にする。

意味づけの候補のきまり:
- 候補は締めくくるとき（done が true）だけ proposals に入れる。それ以外のときは空の配列にする。
- この対話全体で持ち主が語った「並べた理由・意図」と「本どうしのつながり」を、意味づけとしてまとめる。
  同じことを言っている候補や、同じ本の組み合わせになる候補は1つにまとめる。最大4件。
  - meaning: 持ち主の言葉をできるだけそのまま使った、15文字程度の短い名前
  - books: その意味づけが当てはまる本のID（本棚のリストにあるものだけ。1冊以上）
  - reason: 持ち主のどの言葉から取り出したかを1文で
- 本棚にすでにある同じ意味づけ（同じ名前・同じ本）や、この対話ですでに本棚に加わった意味づけは出さない。
- 持ち主がつながりや理由を語らなかった場合は、空の配列にする。

出力のきまり:
- 次の形のJSONだけを出力する。message には持ち主に見せる言葉だけを書く。
  {"message": "持ち主への発言", "focus": ["話題にした本のID"], "done": false,
   "proposals": [{"meaning": "名前", "books": ["B1", "B2"], "reason": "理由"}]}"""

# 構造化出力のスキーマ（Claude では API 側でこの形を保証させる）
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "focus": {"type": "array", "items": {"type": "string"}},
        "done": {"type": "boolean"},
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "meaning": {"type": "string"},
                    "books": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["meaning", "books", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["message", "focus", "done", "proposals"],
    "additionalProperties": False,
}

# 会話は持ち主の発言から始める決まりなので、対話開始の合図を最初の持ち主の発言として置く
OPENING_USER_MESSAGE = "（持ち主が本棚の並べ替えを終えて、「本棚と話す」を押しました）"


def _system_blocks(books: list[dict], isbn_to_id: dict[str, str], changes_text: str) -> list[str]:
    context = (
        f"# 持ち主の本棚（知識グラフより）\n{_shelf_text(books, isbn_to_id)}\n\n"
        f"# 対話のきっかけ（前回の対話以降に持ち主がしたこと）\n{changes_text}"
    )
    return [SYSTEM_RULES, context]


def _conversation(turns: list[dict]) -> list[dict]:
    """知識グラフに残した発言を、そのまま交互のメッセージにする。"""
    messages = [{"role": "user", "content": OPENING_USER_MESSAGE}]
    for turn in turns[-MAX_TRANSCRIPT_TURNS:]:
        messages.append({"role": turn["role"], "content": turn["text"]})
    return messages


# 締めくくりの目安（持ち主の発言回数）。締めくくった後に持ち主が続けた場合は短めに数え直す。
WRAP_UP_RANGE = (3, 5)
WRAP_UP_RANGE_AFTER_CONTINUE = (1, 3)


def _wrap_up_rule(turns: list[dict]) -> str:
    """持ち主の発言回数から、今回締めくくるべきかの指示を作る。"""
    last_wrap = max((i for i, t in enumerate(turns) if t.get("is_wrap_up")), default=-1)
    n = sum(1 for t in turns[last_wrap + 1:] if t["role"] == "user")
    low, high = WRAP_UP_RANGE_AFTER_CONTINUE if last_wrap >= 0 else WRAP_UP_RANGE
    head = (
        f"一度締めくくった後、持ち主が話を続けました。続けてからの発言はこれで{n}回目です。"
        if last_wrap >= 0 else
        f"持ち主の発言はこれで{n}回目です。{low}〜{high}往復を目安に締めくくります。"
    )
    if n < low:
        rule = "まだ締めくくらず、問いかけを続ける（done は false）。"
    elif n < high:
        rule = ("並べた理由やつながりが語られ、話が一巡したと思えば締めくくってよい（done は true）。"
                "まだ聞きたいことがあれば問いかけを続ける（done は false）。")
    else:
        rule = "今回で必ず締めくくる（done は true）。"
    return f"{head}\n{rule}"


def _accepted_text(accepted: list[dict], isbn_to_id: dict[str, str]) -> str:
    if not accepted:
        return "（まだない）"
    lines = []
    for a in accepted:
        ids = " ".join(isbn_to_id[i] for i in (a.get("isbns") or []) if i in isbn_to_id)
        lines.append(f"- {a['text']}（{ids}）")
    return "\n".join(lines)


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _ids_to_isbns(ids, id_to_isbn: dict[str, str]) -> list[str]:
    if not isinstance(ids, list):
        return []
    out = []
    for i in ids:
        isbn = id_to_isbn.get(str(i).strip())
        if isbn and isbn not in out:
            out.append(isbn)
    return out


def _call_llm(system_blocks: list[str], messages: list[dict], max_tokens: int) -> dict:
    """Claude ではシステムプロンプト＋会話＋構造化出力で呼ぶ。
    それ以外のプロバイダーでは1つの文章にまとめ、出力からJSONを取り出す。"""
    try:
        raw = _llm.chat(system_blocks, messages, max_tokens=max_tokens, json_schema=RESPONSE_SCHEMA)
    except LLMDisabledError:
        raise HTTPException(status_code=503, detail=OFF_MESSAGE)
    except Exception as e:
        logger.exception("対話のLLM呼び出しに失敗しました")
        raise HTTPException(status_code=502, detail=f"LLMの応答を取得できませんでした: {e}")
    data = _parse_json(raw)
    if not isinstance(data.get("message"), str) or not data["message"].strip():
        logger.warning("対話のLLM応答を解釈できませんでした: %s", raw)
        raise HTTPException(status_code=502, detail="LLMの応答を解釈できませんでした。もう一度お試しください。")
    return data


def _neo4j_guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ServiceUnavailable:
        raise HTTPException(status_code=503, detail="知識グラフ(Neo4j)に接続できません。Neo4jを起動してください。")


# ============================================================
# エンドポイント
# ============================================================

@router.get("/mode")
def llm_mode():
    """画面に今のLLMのモードを出すため（off / mock / live）。"""
    return {"mode": _LLM_MODE}


@router.post("/start")
def start_dialogue(participant_id: str = Depends(resolve_participant_id)):
    if _LLM_MODE == "off":
        raise HTTPException(status_code=503, detail=OFF_MESSAGE)
    books = _neo4j_guard(store.get_shelf_books, participant_id)
    if not books:
        raise HTTPException(status_code=400, detail="本棚に本がありません。ギャラリーから本を加えてください。")
    changes = _neo4j_guard(store.get_changes_since_last_dialogue, participant_id)

    isbn_to_id, id_to_isbn = _book_ids(books)
    changes_text, discussed = _changes_text(changes, books, isbn_to_id)

    system_blocks = _system_blocks(books, isbn_to_id, changes_text)
    messages = [
        {"role": "user", "content": OPENING_USER_MESSAGE},
        {"role": "system", "content": "最初のひと言を書いてください（最初のひと言のきまりに従う）。"},
    ]
    data = _call_llm(system_blocks, messages, max_tokens=500)
    session_id = str(uuid.uuid4())
    message = data["message"].strip()
    _neo4j_guard(store.create_session, participant_id, session_id, discussed, changes_text)
    _neo4j_guard(store.add_turn, participant_id, session_id, str(uuid.uuid4()), "assistant", message)

    return {
        "session_id": session_id,
        "message": message,
        "focus_isbns": _ids_to_isbns(data.get("focus"), id_to_isbn),
        "discussed_isbns": discussed,
    }


class MessageRequest(BaseModel):
    text: str


def _respond(session_id: str, participant_id: str, info: dict, force_wrap_up: bool = False) -> dict:
    """会話の続きを LLM に書かせる。締めくくり（done）のときだけ、対話全体から
    まとめた意味づけの候補を保存して返す（会話の途中では候補を出さない）。"""
    # 会話の途中で並べ替えや意味づけが増えていることがあるので、本棚は毎回読み直す
    books = _neo4j_guard(store.get_shelf_books, participant_id)
    turns = _neo4j_guard(store.get_turns, participant_id, session_id)
    session_moves = _neo4j_guard(store.get_session_moves, participant_id, session_id)
    accepted = _neo4j_guard(store.get_accepted_meanings, participant_id, session_id)
    isbn_to_id, id_to_isbn = _book_ids(books)

    if force_wrap_up:
        progress = "持ち主が対話を終えようとしています。今回で必ず締めくくる（done は true）。"
        ask = "締めくくりのきまりに従って、この対話を振り返ってください。"
    else:
        progress = _wrap_up_rule(turns)
        ask = "持ち主の最後の発言に返事をしてください。対話の中で本を動かしていれば、その移動にも自然に触れてかまいません。"

    system_blocks = _system_blocks(books, isbn_to_id, info.get("changes_text") or "（なし）")
    note = (
        f"# 会話の進み具合\n{progress}\n\n"
        "# この対話の中で持ち主が動かした本（会話を受けて並べ替えた可能性がある）\n"
        f"{_session_moves_text(session_moves, books, isbn_to_id)}\n\n"
        f"# この対話で本棚に加わった意味づけ\n{_accepted_text(accepted, isbn_to_id)}\n\n"
        f"{ask}"
    )
    messages = _conversation(turns)
    if messages[-1]["role"] != "user":
        # 補足(system)は持ち主の発言の後ろにしか置けない。途中で終えるときは
        # 「対話を終える」を押したことを持ち主側の合図として置く
        messages.append({"role": "user", "content": "（持ち主が「対話を終える」を押しました）"})
    messages.append({"role": "system", "content": note})
    data = _call_llm(system_blocks, messages, max_tokens=1000)
    message = data["message"].strip()
    done = force_wrap_up or data.get("done") is True

    assistant_turn_id = str(uuid.uuid4())
    _neo4j_guard(
        store.add_turn, participant_id, session_id, assistant_turn_id, "assistant", message,
        is_wrap_up=done,
    )

    proposals = []
    raw_proposals = data.get("proposals") if done and isinstance(data.get("proposals"), list) else []
    for p in raw_proposals[:MAX_PROPOSALS]:
        if not isinstance(p, dict):
            continue
        meaning = str(p.get("meaning") or "").strip()[:MAX_MEANING_LEN]
        isbns = _ids_to_isbns(p.get("books"), id_to_isbn)
        if not meaning or not isbns:
            continue
        reason = str(p.get("reason") or "").strip()
        proposal_id = str(uuid.uuid4())
        # 対話全体をまとめた候補なので、締めくくりの発言から取り出したものとして記録する
        _neo4j_guard(
            store.add_proposal, participant_id, session_id, assistant_turn_id,
            proposal_id, meaning, isbns, reason,
        )
        proposals.append({"proposal_id": proposal_id, "meaning": meaning, "isbns": isbns, "reason": reason})

    return {
        "message": message,
        "focus_isbns": _ids_to_isbns(data.get("focus"), id_to_isbn),
        "proposals": proposals,
        "done": done,
    }


def _active_session(participant_id: str, session_id: str) -> dict:
    info = _neo4j_guard(store.get_session_info, participant_id, session_id)
    if not info:
        raise HTTPException(status_code=404, detail="対話が見つかりません")
    if info["status"] != "active":
        raise HTTPException(status_code=400, detail="この対話はもう終わっています")
    return info


@router.post("/{session_id}/message")
def send_message(session_id: str, body: MessageRequest, participant_id: str = Depends(resolve_participant_id)):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="メッセージが空です")
    info = _active_session(participant_id, session_id)
    _neo4j_guard(store.add_turn, participant_id, session_id, str(uuid.uuid4()), "user", text)
    return _respond(session_id, participant_id, info)


@router.post("/{session_id}/wrap-up")
def wrap_up(session_id: str, participant_id: str = Depends(resolve_participant_id)):
    """持ち主が途中で「対話を終える」を押したとき。LLM に締めくくらせ、
    対話全体からまとめた意味づけの候補を返す（反映するかは画面で持ち主が決める）。"""
    info = _active_session(participant_id, session_id)
    return _respond(session_id, participant_id, info, force_wrap_up=True)


class AcceptRequest(BaseModel):
    # 持ち主が名前や対象の本を直してから採用できるようにする（未指定なら提案のまま）
    meaning: str | None = None
    isbns: list[str] | None = None


@router.post("/{session_id}/proposals/{proposal_id}/accept")
def accept_proposal(
    session_id: str, proposal_id: str, body: AcceptRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    proposal = _neo4j_guard(store.get_proposal, participant_id, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="提案が見つかりません")
    if proposal["status"] != "pending":
        raise HTTPException(status_code=400, detail="この提案はもう処理済みです")

    meaning = (body.meaning or proposal["text"]).strip()[:MAX_MEANING_LEN]
    isbns = body.isbns if body.isbns else proposal["isbns"]
    if not meaning or not isbns:
        raise HTTPException(status_code=400, detail="意味づけの名前と本が必要です")

    concept_id = _neo4j_guard(
        save_concept, isbns, meaning, participant_id=participant_id,
        origin="dialogue", confidence="confirmed",
    )
    _neo4j_guard(
        store.resolve_proposal, participant_id, proposal_id, "accepted",
        final_text=meaning, final_isbns=isbns, concept_id=concept_id,
    )
    return {"concept_id": concept_id, "meaning": meaning, "isbns": isbns}


@router.post("/{session_id}/proposals/{proposal_id}/reject")
def reject_proposal(session_id: str, proposal_id: str, participant_id: str = Depends(resolve_participant_id)):
    proposal = _neo4j_guard(store.get_proposal, participant_id, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="提案が見つかりません")
    if proposal["status"] == "pending":
        _neo4j_guard(store.resolve_proposal, participant_id, proposal_id, "rejected")
    return {"status": "rejected"}


@router.post("/{session_id}/end")
def end_dialogue(session_id: str, participant_id: str = Depends(resolve_participant_id)):
    _neo4j_guard(store.end_session, participant_id, session_id)
    return {"status": "ended"}
