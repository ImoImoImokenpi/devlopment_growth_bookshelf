# llm_modes.py
"""LLM_MODE=off / mock 用のクライアント（APIを呼ばないのでクレジットを使わない）。

本物のクライアント（ClaudeClient など）と同じ呼び出し口
（chat / generate_text / generate_json / generate_from_image）を持たせ、
呼び出し側のコードを変えずに差し替えられるようにする。
"""
import json
import re
import time


class LLMDisabledError(RuntimeError):
    """LLM_MODE=off のときに LLM を呼ぼうとした。"""


class DisabledClient:
    """停止モード。呼ばれたら必ず LLMDisabledError にする。"""

    MESSAGE = "LLMは停止中です（LLM_MODE=off）。"

    def chat(self, *args, **kwargs) -> str:
        raise LLMDisabledError(self.MESSAGE)

    def generate_text(self, *args, **kwargs) -> str:
        raise LLMDisabledError(self.MESSAGE)

    def generate_json(self, *args, **kwargs) -> str:
        raise LLMDisabledError(self.MESSAGE)

    def generate_from_image(self, *args, **kwargs) -> str:
        raise LLMDisabledError(self.MESSAGE)


class MockClient:
    """モックモード。決まった形の返事を返す（画面・知識グラフの開発用）。

    本棚対話（chat）は、システムプロンプトの本の一覧（B1「書名」…）と会話の進み具合を読み、
    問いかけ → 返事 → 締めくくり＋意味づけの候補、を本物と同じJSONの形で返す。
    返事の頭には（モック）を付け、本番の発言と見分けられるようにする。
    """

    DELAY_SECONDS = 0.5  # 「考え中…」の表示などを確認できるよう、少しだけ待つ

    def __init__(self):
        self._book_cursor = 0

    # ---- 本棚対話 ----
    def chat(self, system_blocks: list[str], messages: list[dict], max_tokens: int = 1024,
             json_schema: dict | None = None) -> str:
        time.sleep(self.DELAY_SECONDS)
        props = (json_schema or {}).get("properties", {})
        if "pick" in props:
            return self._recommend(messages)
        if "plans" in props:
            return self._plan(messages)
        books = re.findall(r"- (B\d+)「(.+?)」", "\n".join(system_blocks))
        note = messages[-1]["content"] if messages and messages[-1]["role"] == "system" else ""
        user_texts = [
            m["content"] for m in messages
            if m["role"] == "user" and not m["content"].startswith("（")
        ]

        def short(title: str) -> str:
            return title.split(" : ")[0].split(" = ")[0][:20]

        def next_books(n: int) -> list[tuple[str, str]]:
            if not books:
                return []
            picked = [books[(self._book_cursor + i) % len(books)] for i in range(n)]
            self._book_cursor = (self._book_cursor + n) % len(books)
            return picked

        if "最初のひと言" in note:
            # 本物のきまりに合わせて、これまでの対話で話題にした本を避け、意味づけのない本を優先する
            context = "\n".join(system_blocks)
            history = context.split("# これまでの対話", 1)[1].split("# 対話のきっかけ", 1)[0] if "# これまでの対話" in context else ""
            asked = set(re.findall(r"『(.+?)』", history))
            lines = re.findall(r"^- (B\d+)「(.+?)」(.*)$", context, flags=re.M)
            fresh = [i for i, (bid, title, rest) in enumerate(lines)
                     if title not in asked and "持ち主の意味づけ" not in rest]
            start = fresh[0] if fresh else 0
            self._book_cursor = start
            pair = next_books(2)
            names = "』と『".join(short(t) for _, t in pair) or "この本棚"
            return self._json(
                f"（モック）『{names}』は、どんな考えで並べましたか？",
                focus=[i for i, _ in pair],
            )

        # 「本を入れて」と頼まれたら、締めくくらずに受ける（持ち主が終えようとしているときは除く）
        latest = user_texts[-1] if user_texts else ""
        if "必ず締めくくる" not in note and len(messages) >= 2 and messages[-2]["content"] == latest:
            request = self._book_request(latest)
            if request:
                return self._json("（モック）本棚の知識グラフから探して置いてみます。", book_request=request)

        wrap_up = "必ず締めくくる" in note or "締めくくってよい" in note
        if wrap_up:
            proposals = []
            for k, text in enumerate(user_texts[-4:]):
                pair = [books[(k * 2 + j) % len(books)][0] for j in range(2)] if books else []
                proposals.append({
                    "meaning": re.sub(r"[。、！？!?\s]+$", "", text)[:15] or "モックの意味づけ",
                    "books": pair,
                    "reason": f"「{text[:30]}」という言葉から（モック）",
                })
            return self._json("（モック）お話ありがとうございました。", done=True, proposals=proposals)

        last = user_texts[-1] if user_texts else ""
        nxt = next_books(1)
        target = f"隣の『{short(nxt[0][1])}』" if nxt else "隣の本"
        return self._json(
            f"（モック）「{last[:20]}」なんですね。{target}とはどうつながっていますか？",
            focus=[i for i, _ in nxt],
        )

    @staticmethod
    def _recommend(messages: list[dict]) -> str:
        """おすすめ（routers/recommend.py）。最初の候補を、根拠につながる本の最初の1冊の右に置く。"""
        text = messages[-1]["content"] if messages else ""
        basis = re.search(r"# 根拠（知識グラフ）\n(.+)", text)
        anchor = re.search(r"# 根拠につながる本\n- (B\d+)", text)
        title = re.search(r"- C1「(.+?)」", text)
        has_candidate = title is not None
        return json.dumps({
            "pick": "C1" if has_candidate else "",
            "reason": f"（モック）『{title.group(1)[:20] if title else ''}』は{basis.group(1) if basis else ''}とつながりそうです。",
            "anchor": anchor.group(1) if anchor else "",
            "side": "right",
            "placement_reason": "（モック）根拠の本の隣に置きました。",
        }, ensure_ascii=False)

    @staticmethod
    def _plan(messages: list[dict]) -> str:
        """頼まれた冊数の計画（routers/recommend.py）。意味づけ → テーマ → 本の順に根拠を1つずつ使う。"""
        text = messages[-1]["content"] if messages else ""
        m = re.search(r"# 加える冊数\n(\d+)冊", text)
        count = int(m.group(1)) if m else 3
        ids = re.findall(r"^- ([KTB]\d+)[「]", text, flags=re.M)
        plans = [{"basis": i, "keywords": [], "aim": f"（モック）{i}を根拠に1冊"} for i in ids[:count]]
        return json.dumps({"plans": plans}, ensure_ascii=False)

    @staticmethod
    def _book_request(text: str) -> dict | None:
        """「本を5冊入れて」のようなお願いを読み取る（モック用のおおまかな判定）。"""
        if not re.search(r"(入れ|いれ|加え|くわえ|足し|たし|追加|置い|おい|おすすめ)", text) or not re.search(r"(本|冊)", text):
            return None
        digits = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        m = re.search(r"(\d+)\s*冊", digits)
        wish = "バランスよく" if "バランス" in text else ""
        return {"count": min(int(m.group(1)), 5) if m else 3, "wish": wish}

    @staticmethod
    def _json(message: str, focus=None, done: bool = False, proposals=None, book_request=None) -> str:
        return json.dumps(
            {"message": message, "focus": focus or [], "done": done, "proposals": proposals or [],
             "book_request": book_request or {"count": 0, "wish": ""}},
            ensure_ascii=False,
        )

    # ---- そのほかの機能（テーマ生成・比較カードなど） ----
    def generate_text(self, prompt: str, max_tokens: int = 1024) -> str:
        time.sleep(self.DELAY_SECONDS)
        return "（モック）LLMの応答の代わりの文章です。"

    def generate_json(self, prompt: str, max_tokens: int = 2048) -> str:
        time.sleep(self.DELAY_SECONDS)
        return "{}"

    def generate_from_image(self, image_data: bytes, media_type: str, prompt: str, max_tokens: int = 256) -> str:
        # 背表紙写真からのISBN読み取り。モックでは読み取れなかった扱いにする
        time.sleep(self.DELAY_SECONDS)
        return ""
