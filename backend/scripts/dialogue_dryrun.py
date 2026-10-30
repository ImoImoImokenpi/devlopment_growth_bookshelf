"""本棚対話を、知識グラフに書き込まずに試す（プロンプト調整用）。

本棚・意味づけは実際の知識グラフから読み、LLMも実際に呼ぶ。対話の記録・意味づけの候補・
「前回の対話以降に動かした本」の消去といった書き込みはすべて止めて、画面に出すだけにする。

使い方（backend/ で）:
    venv/Scripts/python scripts/dialogue_dryrun.py                 # 対話形式（空行で終了）
    venv/Scripts/python scripts/dialogue_dryrun.py --pid P00 \
        --say "上の段は仕事でよく開く本" --say "手が届くところに置きたくて" --say "そうです"
    --show-prompt を付けると、LLMに送るシステムプロンプトと会話も表示する。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.disable(logging.WARNING)

import routers.dialogue as d  # noqa: E402
from graph.dialogue import store  # noqa: E402
from participant import DEFAULT_PARTICIPANT_ID  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", default=DEFAULT_PARTICIPANT_ID)
    ap.add_argument("--say", action="append", help="持ち主の発言（順に送る）。省略すると対話形式")
    ap.add_argument("--show-prompt", action="store_true")
    args = ap.parse_args()

    turns: list[dict] = []
    state = {"changes_text": None}

    # 書き込みを止め、会話はメモリ上に持つ
    store.create_session = lambda pid, sid, isbns, changes_text: state.update(changes_text=changes_text)
    store.add_turn = lambda pid, sid, tid, role, text, is_wrap_up=False: turns.append(
        {"role": role, "text": text, "is_wrap_up": is_wrap_up})
    store.get_turns = lambda pid, sid: list(turns)
    store.add_proposal = lambda *a, **k: None
    store.get_accepted_meanings = lambda pid, sid: []
    store.get_session_moves = lambda pid, sid: []
    store.get_session_info = lambda pid, sid: {
        "status": "active", "changes_text": state["changes_text"], "discussed_isbns": []}

    if args.show_prompt:
        original = d._call_llm

        def show(system_blocks, messages, max_tokens):
            print("\n===== システムプロンプト =====")
            for i, block in enumerate(system_blocks, 1):
                print(f"--- ブロック{i} ---\n{block}")
            print("===== 会話 =====")
            for m in messages:
                print(f"[{m['role']}] {m['content']}")
            print("================")
            return original(system_blocks, messages, max_tokens)
        d._call_llm = show

    r = d.start_dialogue(participant_id=args.pid)
    print(f"\n[LLM] {r['message']}")
    sid = r["session_id"]

    says = list(args.say or [])
    while True:
        if says:
            text = says.pop(0)
            print(f"\n[持ち主] {text}")
        elif args.say is not None:
            break
        else:
            text = input("\n[持ち主] ").strip()
            if not text:
                break
        r = d.send_message(sid, d.MessageRequest(text=text), participant_id=args.pid)
        print(f"\n[LLM] {r['message']}")
        for p in r["proposals"]:
            print(f"  ・意味づけの候補「{p['meaning']}」({len(p['isbns'])}冊) … {p['reason']}")
        if r["done"]:
            print("\n（LLMが会話を締めくくりました）")
            if args.say is not None and not says:
                break


if __name__ == "__main__":
    main()
