"""My本棚の「過去/現在」2本棚スコープ。

投影のズレ研究のメイン本棚（ShelfLayout/ShelfDesign）に、実験（時期による
本の並びの動作確認）用として period を追加する。Neo4j側のOWNS・概念グラフ・
配置分析・投影スタイル分析は「今の実際の蔵書」を前提にした研究データなので、
period="present" のときだけ従来通り連携し、period="past"（振り返り用の
仮の並び）ではSQLのみで完結させ、研究データには一切書き込まない。
"""

PAST = "past"
PRESENT = "present"
VALID_PERIODS = (PAST, PRESENT)
DEFAULT_PERIOD = PRESENT


def normalize_period(period: str | None) -> str:
    if not period:
        return DEFAULT_PERIOD
    if period not in VALID_PERIODS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"period は {list(VALID_PERIODS)} のいずれかです")
    return period
