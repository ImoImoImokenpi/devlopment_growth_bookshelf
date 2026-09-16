"""グラフに保存された構造指標だけから、参加者の本棚の配置を自然文で
「逆に言語化」できるかを試すデモスクリプト。

実行:
    cd backend
    python -m scripts.placement_narrative_demo [participant_id]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.llm_provider import get_llm_client
from graph.placement_analysis.narrative import build_placement_narrative


def run_demo(participant_id: str = "P00") -> None:
    llm = get_llm_client()
    result = build_placement_narrative(llm, participant_id)

    print("=== LLMに渡したプロンプト ===")
    print(result["prompt"])

    print("\n=== グラフから逆に言語化した結果 ===")
    print(result["narrative"])


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "P00"
    run_demo(pid)
