"""新UI vs 旧UI比較実験のID解決。

既存の participant.py（「投影のズレ」研究、P00〜P20の固定リスト）とは
別の参加者プール・別の研究なので、あえて再利用せず独立させている。
ヘッダ名も別にすることで、同じブラウザで両方の研究を触っても混線しない。

参加者60名・観察者20〜25名という人数を固定リストで管理するのは無理があるため、
形式（英数字・ハイフン・アンダースコア32文字以内）だけを検証し、IDの発行・
名簿管理は研究者側の運用に委ねる。参加者と観察者を取り違えないよう、
研究者が発行するIDにはそれぞれ分かる接頭辞（例: U01.., O01..）を
付けることを推奨する（このモジュールでは強制はしない）。
"""
import re

from fastapi import Header, HTTPException

UIAB_PARTICIPANT_HEADER = "X-Uiab-Participant-Id"
UIAB_OBSERVER_HEADER = "X-Uiab-Observer-Id"

_VALID_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

VALID_PERIODS = ("period1", "period2")


def is_valid_uiab_id(value: str) -> bool:
    return bool(_VALID_ID.match(value or ""))


def resolve_uiab_participant_id(
    x_uiab_participant_id: str | None = Header(default=None),
) -> str:
    if not x_uiab_participant_id or not is_valid_uiab_id(x_uiab_participant_id):
        raise HTTPException(
            status_code=400,
            detail=f"{UIAB_PARTICIPANT_HEADER} ヘッダが必要です（英数字・ハイフン・アンダースコア32文字以内）",
        )
    return x_uiab_participant_id.strip()


def resolve_uiab_observer_id(
    x_uiab_observer_id: str | None = Header(default=None),
) -> str:
    if not x_uiab_observer_id or not is_valid_uiab_id(x_uiab_observer_id):
        raise HTTPException(
            status_code=400,
            detail=f"{UIAB_OBSERVER_HEADER} ヘッダが必要です（英数字・ハイフン・アンダースコア32文字以内）",
        )
    return x_uiab_observer_id.strip()


def validate_period(period: str) -> None:
    if period not in VALID_PERIODS:
        raise HTTPException(status_code=400, detail=f"period は {list(VALID_PERIODS)} のいずれかです")
