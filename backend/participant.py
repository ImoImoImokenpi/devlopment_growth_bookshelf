"""被験者(participant)スコープ。

研究では20人ほどの被験者がそれぞれ自分の蔵書を持ち込み、それぞれの本棚を持つ。
そのため「その人の主観」にあたるデータ（配置・意味づけ・感想・発見）は
すべて participant_id で分離する必要がある。

一方で書誌情報（Book / Author / Publisher / NDC）は客観データなので、
全被験者で共有する。同じ本を複数人が持っていても1つのノードでよい。
"""
import os
import re

from fastapi import Header, HTTPException

# ヘッダが無いときのフォールバック。既存の単一ユーザ時代のデータはここに属する。
DEFAULT_PARTICIPANT_ID = "P00"

# 「他の参加者の本棚を観察する」画面の一覧に使う参加者ID全体。
# P00はプロトタイプ（開発用データ）として一覧にも含める。
PROTOTYPE_PARTICIPANT_ID = "P00"
ALL_PARTICIPANT_IDS = [PROTOTYPE_PARTICIPANT_ID] + [f"P{i:02d}" for i in range(1, 21)]

PARTICIPANT_HEADER = "X-Participant-Id"

# 被験者IDはNeo4jのノードIDやSQLiteのキーに直接埋め込むため、扱いやすい文字に限定する
_VALID_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def is_valid_participant_id(value: str) -> bool:
    return bool(_VALID_ID.match(value or ""))


def _header_required() -> bool:
    """本番の実験環境では、ヘッダの付け忘れで全員分のデータが P00 に
    混ざるほうが事故として重い。REQUIRE_PARTICIPANT_HEADER=1 で必須化する。"""
    return os.getenv("REQUIRE_PARTICIPANT_HEADER", "").strip() in ("1", "true", "True")


def resolve_participant_id(
    x_participant_id: str | None = Header(default=None),
) -> str:
    """X-Participant-Id ヘッダから被験者IDを取り出す FastAPI の依存関数。"""
    if not x_participant_id:
        if _header_required():
            raise HTTPException(
                status_code=400,
                detail=f"{PARTICIPANT_HEADER} ヘッダが必要です",
            )
        return DEFAULT_PARTICIPANT_ID

    pid = x_participant_id.strip()
    if not is_valid_participant_id(pid):
        # 不正なIDを黙って既定値に落とすと、複数被験者のデータが静かに
        # 1人分へ混ざる。それは復旧不能なので、ここは必ず失敗させる。
        raise HTTPException(
            status_code=400,
            detail=f"{PARTICIPANT_HEADER} が不正です（英数字・ハイフン・アンダースコア32文字以内）: {pid}",
        )
    return pid
