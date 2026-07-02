# gemini_client.py
import os
from pathlib import Path

from google import genai
from google.genai import types
from google.genai.errors import ClientError as GeminiClientError, ServerError as GeminiServerError
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


class GeminiClient:

    MODELS  = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash-lite"]

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

    def generate_content(self, model: str, contents):
        return self._get_client().models.generate_content(model=model, contents=contents)

    def generate_with_fallback(self, contents) -> str:
        """MODELS を順に試し、429（レート制限）・503（過負荷）の時は次のモデルにフォールバックする。"""
        last_error = None
        for model in self.MODELS:
            try:
                response = self.generate_content(model=model, contents=contents)
                return response.text.strip()
            except (GeminiClientError, GeminiServerError) as e:
                code = getattr(e, "code", None)
                if code in (429, 503):
                    last_error = e
                    continue
                raise
        raise last_error
