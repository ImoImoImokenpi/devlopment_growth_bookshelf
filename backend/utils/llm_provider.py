# llm_provider.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def get_llm_client():
    """
    LLM_PROVIDER 環境変数でプロバイダーを切り替える。
    - "groq"（既定はfalse）: プロトタイプ用。無料枠のレート制限が緩い
    - 未設定 / "gemini": 本番用
    """
    provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()

    if provider == "groq":
        from utils.groq_client import GroqClient
        return GroqClient.get_instance()

    from utils.gemini_client import GeminiClient
    return GeminiClient.get_instance()
