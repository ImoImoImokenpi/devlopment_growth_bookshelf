# llm_provider.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

LLM_MODES = ("off", "mock", "live")


def get_llm_mode() -> str:
    """LLM_MODE: off（停止）/ mock（モック）/ live（本番）。
    未設定や不正な値は off にする（うっかりAPIのクレジットを使わないように）。"""
    mode = os.environ.get("LLM_MODE", "off").strip().lower()
    return mode if mode in LLM_MODES else "off"


def get_llm_client():
    """
    LLM_MODE で、APIを呼ぶかどうかを切り替える（変更はバックエンドの再起動で反映）。
    - "off" : 停止。呼ばれたら LLMDisabledError（APIは呼ばない）
    - "mock": モック。決まった形の返事を返す（APIは呼ばない）
    - "live": 本番。Claude（Anthropic API）を呼ぶ。ANTHROPIC_API_KEY が必要で、クレジットを使う
    """
    mode = get_llm_mode()
    if mode == "off":
        from utils.llm_modes import DisabledClient
        return DisabledClient()
    if mode == "mock":
        from utils.llm_modes import MockClient
        return MockClient()

    from utils.claude_client import ClaudeClient
    return ClaudeClient.get_instance()
