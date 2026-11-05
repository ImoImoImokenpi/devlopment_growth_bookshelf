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
# 今開いている本棚（models.Bookshelf.scope_id）。持ち主は本棚を複数持てて、
# 本棚ごとに配置・知識グラフ・対話を分ける。無ければ最初の本棚（＝持ち主のID）。
SHELF_HEADER = "X-Shelf-Id"

# 被験者IDはNeo4jのノードIDやSQLiteのキーに直接埋め込むため、扱いやすい文字に限定する
_VALID_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def is_valid_participant_id(value: str) -> bool:
    return bool(_VALID_ID.match(value or ""))


def _header_required() -> bool:
    """本番の実験環境では、ヘッダの付け忘れで全員分のデータが P00 に
    混ざるほうが事故として重い。REQUIRE_PARTICIPANT_HEADER=1 で必須化する。"""
    return os.getenv("REQUIRE_PARTICIPANT_HEADER", "").strip() in ("1", "true", "True")


def shelf_scope_id(participant_id: str, number: int) -> str:
    """2つ目以降の本棚のスコープID（例: P00-S2）。"""
    return f"{participant_id}-S{number}"


def resolve_participant_id(
    x_participant_id: str | None = Header(default=None),
    x_shelf_id: str | None = Header(default=None),
) -> str:
    """データを読み書きする範囲のIDを返す FastAPI の依存関数。

    ふだんは持ち主のID（X-Participant-Id）。X-Shelf-Id で2つ目以降の本棚を
    開いているときは、その本棚のスコープID（例: P00-S2）を返す。ほかのテーブルや
    知識グラフは、このIDを participant_id として扱うので、本棚ごとにデータが分かれる。
    """
    base = resolve_base_participant_id(x_participant_id)
    shelf = (x_shelf_id or "").strip()
    if not shelf or shelf == base:
        return base
    if not (is_valid_participant_id(shelf) and shelf.startswith(f"{base}-S")):
        raise HTTPException(status_code=400, detail=f"{SHELF_HEADER} が不正です: {shelf}")
    # 消した本棚・存在しない本棚に書き込むと、どこにも表示されないデータが残るので弾く
    from database import SessionLocal
    from models import Bookshelf
    with SessionLocal() as db:
        exists = db.query(Bookshelf.id).filter(
            Bookshelf.scope_id == shelf, Bookshelf.participant_id == base,
        ).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"本棚が見つかりません: {shelf}")
    return shelf


def resolve_base_participant_id(
    x_participant_id: str | None = Header(default=None),
) -> str:
    """X-Participant-Id ヘッダから被験者IDを取り出す FastAPI の依存関数（本棚は問わない）。"""
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
