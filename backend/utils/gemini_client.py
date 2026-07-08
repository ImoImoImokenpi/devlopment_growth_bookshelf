# gemini_client.py
import os
from pathlib import Path

from google import genai
from google.genai import types
from google.genai.errors import ClientError as GeminiClientError, ServerError as GeminiServerError
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


class GeminiClient:
    """本番用（安定運用向け）。呼び出し元は generate_text / generate_from_image のみ使う。"""

    MODELS = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.0-flash"]

    _instance: "GeminiClient | None" = None

    def __init__(self):
        self._client = None  # 遅延生成。APIキー未設定でもアプリ起動を妨げないようにする

    @classmethod
    def get_instance(cls) -> "GeminiClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_client(self):
        if self._client is None:
            self._client = genai.Client(
                api_key=os.environ.get("GEMINI_API_KEY"),
                http_options=types.HttpOptions(api_version="v1"),
            )
        return self._client

    def _generate_with_fallback(self, contents, max_tokens: int, json_mode: bool = False) -> str:
        """MODELS を順に試し、429（レート制限）・503（過負荷）の時は次のモデルにフォールバックする。"""
        last_error = None
        config_kwargs = {"max_output_tokens": max_tokens}
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        for model in self.MODELS:
            try:
                response = self._get_client().models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                return (response.text or "").strip()
            except (GeminiClientError, GeminiServerError) as e:
                code = getattr(e, "code", None)
                if code in (429, 503):
                    last_error = e
                    continue
                raise
        raise last_error

    def generate_text(self, prompt: str, max_tokens: int = 1024) -> str:
        return self._generate_with_fallback(prompt, max_tokens)

    def generate_json(self, prompt: str, max_tokens: int = 2048) -> str:
        """モデルにJSON出力を強制させる（構造化データの抽出用）。"""
        return self._generate_with_fallback(prompt, max_tokens, json_mode=True)

    def generate_from_image(self, image_data: bytes, media_type: str, prompt: str, max_tokens: int = 256) -> str:
        contents = [
            types.Part.from_bytes(data=image_data, mime_type=media_type),
            types.Part.from_text(text=prompt),
        ]
        return self._generate_with_fallback(contents, max_tokens)
