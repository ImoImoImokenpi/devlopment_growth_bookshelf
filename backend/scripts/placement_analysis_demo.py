"""本棚配置分析システムの動作確認用スクリプト。

既存の実データ（P00など、/bookshelf/sync-layout 経由でNeo4jに反映済みの参加者）
に対して、エンリッチメント→指標計算→PlacementProfile保存→孤立本検出→
デザイン根拠履歴、まで一通り実行する。新規ダミーデータは作らない
（高さ・色・著者・NDCの実データが無いと意味のある指標が出ないため）。

実行:
    cd backend
    python -m scripts.placement_analysis_demo [participant_id]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.placement_analysis.schema import ensure_placement_analysis_schema
from graph.placement_analysis.profile import compute_and_save_placement_profile, get_placement_profile_history
from graph.placement_analysis.isolation import compute_isolation, summarize_isolation
from graph.placement_analysis.evidence import get_design_evidence_history
from graph.placement_analysis.authors import sync_author_canonical_names, find_author_duplicate_groups


def run_demo(participant_id: str = "P00") -> None:
    ensure_placement_analysis_schema()

    updated = sync_author_canonical_names()
    print(f"[authors] canonicalName付与: {updated}件")
    dup_groups = find_author_duplicate_groups()
    print(f"[authors] 表記ゆれ候補: {json.dumps(dup_groups, ensure_ascii=False)}")

    profile = compute_and_save_placement_profile(participant_id)
    print(f"[profile] {json.dumps(profile, ensure_ascii=False, default=str)}")

    history = get_placement_profile_history(participant_id)
    print(f"[history] {len(history)}件のスナップショット")

    isolation_records = compute_isolation(participant_id)
    print(f"[isolation summary] {json.dumps(summarize_isolation(isolation_records), ensure_ascii=False)}")
    for r in isolation_records[:5]:
        print(f"  {r}")

    evidence = get_design_evidence_history(participant_id)
    print(f"[design evidence] {len(evidence)}件")
    for e in evidence[:3]:
        print(f"  {e}")


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "P00"
    run_demo(pid)
