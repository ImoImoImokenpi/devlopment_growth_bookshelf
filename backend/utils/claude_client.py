# claude_client.py
"""Claude（Anthropic API）用のLLMクライアント。

LLM_MODE=live のときに使う。停止・モック用のクライアント（utils/llm_modes.py）と
同じ呼び出し口（chat / generate_text / generate_json / generate_from_image）を持つ。

- モデル: Claude Opus 5.5（LLM_CLAUDE_MODEL で変更可）
- Claude Opus 5.5 は思考（thinking）が常に有効で、思考に使うトークンも max_tokens に
  含まれる。呼び出し側は「返答の長さ」のつもりで max_tokens を渡してくるので、
  ここで思考のぶんの余裕を足してから送る（足さないと返答が途中で切れる）。
- 思考の深さは effort で決める（LLM_CLAUDE_EFFORT、既定は low）。対話の応答は速さが大事で、
  短い会話文やJSONの抽出には low で足りるため。
- 安全分類器が回答を断った場合は、サーバー側で推奨のモデルに自動で切り替える
  （fallbacks="default"）。それでも断られたときは例外にする。
"""
import base64
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

THINKING_HEADROOM_TOKENS = 8000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeRefusalError(RuntimeError):
    """Claude が回答を断った（stop_reason="refusal"）。"""


class ClaudeClient:
    # 環境変数名は LLM_ を付けてこのアプリ専用にする（CLAUDE_* は他のツールが使うことがある）
    MODEL = os.environ.get("LLM_CLAUDE_MODEL", "claude-opus-5-5")
    EFFORT = os.environ.get("LLM_CLAUDE_EFFORT", "low")

    _instance: "ClaudeClient | None" = None

    def __init__(self):
        self._client = None  # 遅延生成。APIキー未設定でもアプリ起動を妨げないようにする

    @classmethod
    def get_instance(cls) -> "ClaudeClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            # ANTHROPIC_API_KEY（backend/.env か環境変数）を自動で読む
            self._client = anthropic.Anthropic()
        return self._client

    def _create(self, content, max_tokens: int) -> str:
        response = self._get_client().beta.messages.create(
            model=self.MODEL,
            max_tokens=max_tokens + THINKING_HEADROOM_TOKENS,
            output_config={"effort": self.EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks="default",
            messages=[{"role": "user", "content": content}],
        )
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise ClaudeRefusalError(f"Claudeが回答を断りました（{category or '理由不明'}）")
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def chat(
        self, system_blocks: list[str], messages: list[dict], max_tokens: int = 1024,
        json_schema: dict | None = None,
    ) -> str:
        """システムプロンプト＋会話で呼ぶ（本棚対話用）。

        - system_blocks: システムプロンプトを変わりにくい順に並べたもの。最後のブロックに
          キャッシュの区切りを付け、同じ対話の2回目以降はキャッシュから読ませる。
        - messages: user / assistant の交互の会話。最後に {"role": "system"} を置くと、
          会話途中の運営からの補足として扱われる（キャッシュを崩さずに毎回の情報を足せる）。
        - json_schema: 指定すると構造化出力でこの形のJSONを保証させる。
        """
        system = [{"type": "text", "text": text} for text in system_blocks]
        if system:
            system[-1]["cache_control"] = {"type": "ephemeral"}
        output_config: dict = {"effort": self.EFFORT}
        if json_schema:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}

        response = self._get_client().beta.messages.create(
            model=self.MODEL,
            max_tokens=max_tokens + THINKING_HEADROOM_TOKENS,
            system=system,
            messages=messages,
            output_config=output_config,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise ClaudeRefusalError(f"Claudeが回答を断りました（{category or '理由不明'}）")
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def generate_text(self, prompt: str, max_tokens: int = 1024) -> str:
        return self._create(prompt, max_tokens)

    def generate_json(self, prompt: str, max_tokens: int = 2048) -> str:
        """JSONだけを返させる。呼び出し側が json.loads できるよう、
        コードフェンス（```json ... ```）が付いていたら外して返す。"""
        text = self._create(
            prompt + "\n\n出力はJSONのみとし、前後に説明文やコードフェンスを付けないでください。",
            max_tokens,
        )
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        return text

    def generate_from_image(self, image_data: bytes, media_type: str, prompt: str, max_tokens: int = 256) -> str:
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(image_data).decode("ascii"),
                },
            },
            {"type": "text", "text": prompt},
        ]
        return self._create(content, max_tokens)
