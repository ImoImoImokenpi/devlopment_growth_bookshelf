# groq_client.py
import base64
import os
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


class GroqClient:
    """プロトタイプ用（無料枠のレート制限が緩い）。呼び出し元は generate_text / generate_from_image のみ使う。"""

    MODEL        = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

    _instance: "GroqClient | None" = None

    def __init__(self):
        self._client = None  # 遅延生成。APIキー未設定でもアプリ起動を妨げないようにする

    @classmethod
    def get_instance(cls) -> "GroqClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_client(self) -> Groq:
        if self._client is None:
            self._client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        return self._client

    def generate_text(self, prompt: str, max_tokens: int = 1024) -> str:
        response = self._get_client().chat.completions.create(
            model=self.MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return (response.choices[0].message.content or "").strip()

    def generate_json(self, prompt: str, max_tokens: int = 2048) -> str:
        """モデルにJSON出力を強制させる（構造化データの抽出用）。プロンプト中に "JSON" という単語が必要。"""
        response = self._get_client().chat.completions.create(
            model=self.MODEL,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return (response.choices[0].message.content or "").strip()

    def generate_from_image(self, image_data: bytes, media_type: str, prompt: str, max_tokens: int = 256) -> str:
        image_b64 = base64.standard_b64encode(image_data).decode("utf-8")
        response = self._get_client().chat.completions.create(
            model=self.VISION_MODEL,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
                ],
            }],
        )
        return (response.choices[0].message.content or "").strip()
