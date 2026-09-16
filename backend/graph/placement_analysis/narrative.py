"""グラフに保存された構造指標から、参加者の本棚の配置を自然文で
「逆に言語化」できるかを試す機能。

配置分析（PlacementProfile・孤立本・DesignEvidence）と内容分析
（content_alignment: テーマ・意味づけごとの物理的なまとまり具合）の
両方をLLMに渡し、「何をまとめて何を分散させているか」まで踏み込んだ
説明を作らせる。Group.nameやComment本文のような込み入った意味データ
（experiment側が扱うもの）は一切含めない。書名は、デザイン根拠として挙げる
段の本だけ、引用のために別途引く（Bookは全参加者共有の客観データなので、
構造指標そのものには含まれないが、参照して問題ない）。
"""
from __future__ import annotations

from graph.placement_analysis.profile import get_latest_placement_profile
from graph.placement_analysis.isolation import compute_isolation, summarize_isolation
from graph.placement_analysis.evidence import get_design_evidence_history
from graph.placement_analysis.content_alignment import compute_content_alignment
from graph.placement_analysis.books import fetch_titles

_METRIC_LABELS = {
    "height_order_score": "高さの並び順（段全体で高さが順に変化する度合い、0〜1）",
    "height_staircase_score": "高さの段々（隣り合う本の高さの増減が同方向へ連続する割合、0〜1）",
    "row_height_trend_score": "段をまたいだ高さの傾向（+1に近いほど下段が大きい本・-1に近いほど上段が大きい本、-1〜1）",
    "height_group_order_score": "グループ単位の高さの並び順（間隔で区切られた小グループごとに高さ順序を見た度合い。山型・谷型など、段全体では打ち消し合って見えない部分的な高さ順を拾う、0〜1）",
    "height_grouping_score": "高さのまとまり（隣同士が近い高さになりやすいか、-1〜1）",
    "color_grouping_score": "背表紙の色のまとまり（隣同士が近い色味になりやすいか、-1〜1）",
    "color_gradient_score": "色のグラデーション（色相が一定方向へなだらかに変化するか、0〜1）",
    "color_uniformity_score": "色の統一感（段全体で使われている色数の絞り込み具合、0〜1）",
    "author_grouping_score": "著者のまとまり（同じ著者を隣に置きやすいか、-1〜1）",
    "genre_placement_modularity": "ジャンル(NDC)と配置の一致度",
    "genre_placement_nmi": "ジャンル(NDC)と配置の一致度（NMI、0〜1）",
    "theme_placement_modularity": "あらすじから抽出した内容テーマと配置の一致度",
    "theme_placement_nmi": "内容テーマと配置の一致度（NMI、0〜1）",
    "concept_placement_modularity": "参加者自身が付けた意味づけと配置の一致度",
    "concept_placement_nmi": "意味づけと配置の一致度（NMI、0〜1）",
    "symmetry_score": "高さの左右対称性（0〜1）",
    "rhythm_score": "色の周期性（0〜1）",
    "spacing_regularity": "間隔の均一さ（0〜1）",
}


def _format_alignment_section(title: str, breakdown: list[dict]) -> list[str]:
    if not breakdown:
        return []
    lines = ["", f"【{title}：物理的なまとまり具合（1.0に近いほど固めて置いている）】"]
    for g in breakdown[:3]:
        lines.append(
            f"- 「{g['name']}」({g['book_count']}冊): clustering_rate={g['clustering_rate']}, "
            f"{g['shelves_used']}段に分散"
        )
    if len(breakdown) > 4:
        lines.append("  …")
        for g in breakdown[-2:]:
            lines.append(
                f"- 「{g['name']}」({g['book_count']}冊): clustering_rate={g['clustering_rate']}, "
                f"{g['shelves_used']}段に分散"
            )
    return lines


def build_narrative_prompt(
    profile: dict,
    isolation_summary: dict,
    evidence: list[dict],
    titles: dict[str, str],
    content_alignment: dict,
) -> str:
    lines = [
        "あなたは、本棚の構造データ（配置の統計指標）と内容データ（テーマ・意味づけの",
        "分布）の両方から、持ち主の本の並べ方の癖を言葉で説明する分析家です。以下は、",
        "ある参加者の本棚をグラフ構造から機械的に計測した数値指標です。本の中身の詳細",
        "（あらすじの引用など）ではなく、並べ方の統計と、テーマ・意味づけごとの物理的な",
        "まとまり具合の対比を根拠に、この人がどんな基準で本を並べているか、400字程度の",
        "日本語の文章で説明してください。特に、どのテーマ/意味づけは物理的にもまとめていて、",
        "どれを別の基準（高さ・色など）を優先して分散させているか、という対比があれば",
        "積極的に触れてください。断定を避け、「〜傾向があります」「〜のようです」という",
        "言い回しにしてください。",
        "",
        f"対象冊数: {profile.get('book_count')}冊",
        "",
        "【配置の構造指標】",
    ]
    for key, label in _METRIC_LABELS.items():
        value = profile.get(key)
        if value is None:
            continue
        lines.append(f"- {label}: {value}")

    lines.append("")
    lines.append(f"【デザイン重視の配置と判定されたか】{'はい' if profile.get('design_intent') else 'いいえ'}")

    lines.append("")
    lines.append("【孤立している本の集計】")
    lines.append(f"- 知識グラフ全体で孤立: {isolation_summary.get('topological_isolated_count')}冊")
    lines.append(f"- 意味づけを誰とも共有していない: {isolation_summary.get('semantic_isolated_count')}冊")
    lines.append(f"- 棚の同じ段に他の本がない: {isolation_summary.get('physical_isolated_count')}冊")
    lines.append(f"- 隣にはあるが共通点がない: {isolation_summary.get('floating_count')}冊")

    lines.extend(_format_alignment_section("内容テーマ", content_alignment.get("themes", [])))
    lines.extend(_format_alignment_section("意味づけ", content_alignment.get("concepts", [])))

    if evidence:
        lines.append("")
        lines.append("【デザイン重視と判定された根拠】")
        for e in evidence[:3]:
            book_titles = "、".join(titles.get(isbn, isbn) for isbn in e.get("isbns", [])[:4])
            lines.append(
                f"- {e['label']}（{e['shelf_index'] + 1}段目、score={e['score']}、"
                f"p={e.get('p_value')}）: {book_titles}"
            )

    return "\n".join(lines)


def build_placement_narrative(llm, participant_id: str) -> dict:
    """配置分析と内容分析の両方から自然文の説明を生成する。戻り値には、
    実際にLLMへ渡した材料も含める（検証用）。"""
    profile = get_latest_placement_profile(participant_id)
    if not profile:
        raise ValueError(f"PlacementProfileがまだありません: participant_id={participant_id}")

    isolation_summary = summarize_isolation(compute_isolation(participant_id))
    evidence = get_design_evidence_history(participant_id)
    content_alignment = compute_content_alignment(participant_id)

    all_isbns = [isbn for e in evidence for isbn in e.get("isbns", [])]
    titles = fetch_titles(all_isbns)

    prompt = build_narrative_prompt(profile, isolation_summary, evidence, titles, content_alignment)
    narrative = llm.generate_text(prompt, max_tokens=500)

    return {
        "participant_id": participant_id,
        "prompt": prompt,
        "narrative": narrative.strip(),
        "profile": profile,
        "isolation_summary": isolation_summary,
        "evidence": evidence,
        "content_alignment": content_alignment,
    }
