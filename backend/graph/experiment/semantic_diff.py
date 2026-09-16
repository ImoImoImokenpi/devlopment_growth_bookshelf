"""2.6 意味差分生成API（LLM連携）。

閲覧者の部分推測テキストと、対象グループの実際の意味データ（Group.name・
所属本のComment本文）だけをLLMに渡し、
  - 閲覧者の推測がジャンル的・表層的な説明("genre_based")か、
    文脈的・個人的な説明("contextual")に近いかの簡易判定
  - 両者の意味的なギャップを、断定を避けた自然文（1〜2文）
を生成する。対象グループ以外のデータ（他の参加者・他のグループのコメント等）は
一切渡さない（プロンプトインジェクション対策・分析範囲の限定、spec 2.6/6章）。
"""
from __future__ import annotations

import json
import re

from graph.style_projection.groups import get_group_semantic_content

_ATTRIBUTION_TYPES = ("genre_based", "contextual")


def _ensure_tentative_tone(text: str) -> str:
    text = text.strip()
    if "かもしれ" in text:
        return text
    return f"{text.rstrip('。')}かもしれません。"


def _build_semantic_diff_prompt(viewer_text: str, group_name: str | None, comments: list[str]) -> str:
    lines = [
        "あなたは、読書家の本棚を見た閲覧者の推測と、本棚の持ち主が実際に残した理由との",
        "意味的なギャップを、断定を避けた柔らかい言い方で伝えるアシスタントです。",
        "",
        f"【閲覧者の推測】{viewer_text}",
        "",
        "【持ち主が実際にこのグループに付けた名前】",
        group_name or "（無題）",
        "",
        "【持ち主がこのグループの本に残したコメント】",
    ]
    if comments:
        for c in comments[:10]:
            lines.append(f"- {c}")
    else:
        lines.append("- （コメントなし）")

    lines.append("")
    lines.append(
        "まず、閲覧者の推測が次のどちらに近いかを判定してください:"
        " genre_based（ジャンルや表層的な特徴による説明）,"
        " contextual（個人的な経験や文脈による説明）。"
    )
    lines.append(
        "同様に、持ち主の実際の名前・コメントから読み取れる理由が genre_based と contextual の"
        "どちらに近いかも判定してください（owner_actual_type）。"
    )
    lines.append(
        "最後に、閲覧者の推測と持ち主の実際の理由との意味的なギャップを、断定を避けた"
        "「〜かもしれません」調の自然文で1〜2文にまとめてください（gap_summary）。"
        "持ち主の実際の名前・コメントの引用は最小限にし、閲覧者を否定するような言い方は避けてください。"
    )
    lines.append("出力は次のJSON形式のみとし、前置きや説明文、コードブロック記法は付けないでください。")
    lines.append(
        '{"viewer_attribution_type": "genre_based", "owner_actual_type": "contextual", '
        '"gap_summary": "1〜2文"}'
    )
    return "\n".join(lines)


def _parse_semantic_diff(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    obj_start, obj_end = text.find("{"), text.rfind("}")
    candidate = text[obj_start:obj_end + 1] if obj_start != -1 and obj_end > obj_start else text
    try:
        data = json.loads(candidate)
        viewer_type = str(data.get("viewer_attribution_type", "")).strip()
        owner_type = str(data.get("owner_actual_type", "")).strip()
        gap_summary = str(data.get("gap_summary", "")).strip()
        if viewer_type not in _ATTRIBUTION_TYPES:
            viewer_type = "genre_based"
        if owner_type not in _ATTRIBUTION_TYPES:
            owner_type = "contextual"
        if gap_summary:
            return {
                "viewer_attribution_type": viewer_type,
                "owner_actual_type": owner_type,
                "gap_summary": _ensure_tentative_tone(gap_summary),
            }
    except (json.JSONDecodeError, AttributeError):
        pass
    return {
        "viewer_attribution_type": "genre_based",
        "owner_actual_type": "contextual",
        "gap_summary": _ensure_tentative_tone(text[:80]) if text else None,
    }


def build_semantic_diff(llm, viewer_text: str, group_id: str) -> dict:
    """viewer_text（部分推測の自由記述）と対象グループ(group_id)の実際の意味データから
    意味差分カードを生成する。llmは utils.llm_provider.get_llm_client() の戻り値
    （呼び出し側で使い回しているクライアントをそのまま渡す）。"""
    content = get_group_semantic_content(group_id)
    prompt = _build_semantic_diff_prompt(viewer_text, content["name"], content["comments"])
    raw = llm.generate_json(prompt, max_tokens=300)
    return _parse_semantic_diff(raw)
