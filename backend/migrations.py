"""起動時に走らせる、既存 bookshelf.db 向けの軽量マイグレーション。

Alembic を入れていないので、必要な変更だけを冪等に適用する。
すべて「既に適用済みなら何もしない」形で書くこと。
"""
import logging

from sqlalchemy import text

from models import MyHand, ShelfDesign, ShelfLayout
from participant import DEFAULT_PARTICIPANT_ID
from shelf_period import DEFAULT_PERIOD

logger = logging.getLogger(__name__)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).first()
    return row is not None


def _columns(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]


def _add_column_if_missing(conn, table: str, column: str, ddl_type: str) -> None:
    if not _table_exists(conn, table):
        return
    if column in _columns(conn, table):
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
    logger.info("migration: %s.%s を追加しました", table, column)


def _rebuild_with_participant(conn, model) -> bool:
    """participant_id を持たない旧テーブルを、新スキーマで作り直して中身を移す。

    SQLite は UNIQUE 制約を後から外せないため、
      ShelfLayout.isbn           (UNIQUE)  → (participant_id, isbn)      の複合UNIQUE
      MyHand.registered_book_id  (UNIQUE)  → (participant_id, book_id)   の複合UNIQUE
    に変えるにはテーブルごと作り直すしかない。
    """
    table = model.__tablename__
    if not _table_exists(conn, table):
        return False  # 未作成なら create_all が新スキーマで作るので何もしなくてよい

    old_cols = _columns(conn, table)
    if "participant_id" in old_cols:
        return False  # 適用済み

    tmp = f"{table}__pre_participant"

    # RENAME するとインデックスは旧テーブルに付いたまま名前だけ残り、
    # 新テーブル作成時に同名で衝突する。先に落としておく。
    # PRAGMA の結果は必ずリストに落としてから DDL を流すこと。
    # カーソルを開いたままスキーマを変更すると SQLite が table is locked を返す。
    index_names = [
        row[1]
        for row in conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
        # 暗黙のインデックスは DROP できないが、旧テーブルと一緒に消える
        if not row[1].startswith("sqlite_autoindex_")
    ]
    for index_name in index_names:
        conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

    conn.execute(text(f"ALTER TABLE {table} RENAME TO {tmp}"))
    model.__table__.create(bind=conn)

    new_cols = _columns(conn, table)
    carried = [c for c in old_cols if c in new_cols and c != "participant_id"]
    col_list = ", ".join(carried)
    conn.execute(
        text(
            f"INSERT INTO {table} ({col_list}, participant_id) "
            f"SELECT {col_list}, :pid FROM {tmp}"
        ),
        {"pid": DEFAULT_PARTICIPANT_ID},
    )
    conn.execute(text(f"DROP TABLE {tmp}"))
    logger.info("migration: %s を被験者スコープに作り直しました", table)
    return True


def _rebuild_with_period(conn, model) -> bool:
    """period を持たない旧テーブルを、新スキーマ（period列＋それを含むUNIQUE）で
    作り直して中身を移す。既存行はすべて period="present"（今の本棚）として扱う
    ——旧仕様は単一の本棚だったので、それがそのまま「現在」に対応する。
    """
    table = model.__tablename__
    if not _table_exists(conn, table):
        return False

    old_cols = _columns(conn, table)
    if "period" in old_cols:
        return False  # 適用済み

    tmp = f"{table}__pre_period"

    index_names = [
        row[1]
        for row in conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
        if not row[1].startswith("sqlite_autoindex_")
    ]
    for index_name in index_names:
        conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

    conn.execute(text(f"ALTER TABLE {table} RENAME TO {tmp}"))
    model.__table__.create(bind=conn)

    new_cols = _columns(conn, table)
    carried = [c for c in old_cols if c in new_cols and c != "period"]
    col_list = ", ".join(carried)
    conn.execute(
        text(
            f"INSERT INTO {table} ({col_list}, period) "
            f"SELECT {col_list}, :period FROM {tmp}"
        ),
        {"period": DEFAULT_PERIOD},
    )
    conn.execute(text(f"DROP TABLE {tmp}"))
    logger.info("migration: %s を時期(period)スコープに作り直しました", table)
    return True


def _has_unique_constraint(conn, table: str) -> bool:
    """テーブルにUNIQUE制約由来のインデックス（origin='u'）が残っているか。
    SQLiteは名前付きのUNIQUE制約でも sqlite_autoindex_* という内部名で
    作ることがあり、CONSTRAINT名で存在チェックするのは当てにならないため、
    origin列（'u'=UNIQUE制約由来）で判定する。"""
    rows = conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
    return any(row[3] == "u" for row in rows)


def _drop_unique_constraints_and_rebuild(conn, model) -> bool:
    """モデル側でUNIQUE制約を外したのに、既存DBのテーブルにまだ
    UNIQUE制約由来のインデックスが残っていれば、作り直して外す。
    列構成は変えず、行もそのままコピーする。
    SQLiteはUNIQUE制約を後から外せないための共通処理。"""
    table = model.__tablename__
    if not _table_exists(conn, table):
        return False
    if not _has_unique_constraint(conn, table):
        return False  # 既に外れている（または最初から無い）

    tmp = f"{table}__pre_drop_unique"
    index_names = [
        row[1]
        for row in conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
        if not row[1].startswith("sqlite_autoindex_")
    ]
    for name in index_names:
        conn.execute(text(f"DROP INDEX IF EXISTS {name}"))

    conn.execute(text(f"ALTER TABLE {table} RENAME TO {tmp}"))
    model.__table__.create(bind=conn)

    cols = _columns(conn, table)
    col_list = ", ".join(cols)
    conn.execute(text(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM {tmp}"))
    conn.execute(text(f"DROP TABLE {tmp}"))
    logger.info("migration: %s のUNIQUE制約を外しました（本棚に同じ本を複数冊置けるように）", table)
    return True


def run_migrations(engine) -> None:
    # プールに残った接続がテーブルの読み取りロックを持っていると
    # テーブル再構築の DDL が "table is locked" で失敗する。
    engine.dispose()

    with engine.begin() as conn:
        # --- 既存の単発マイグレーション（旧 main.py から移設） ---
        _add_column_if_missing(conn, "registered_books", "spine_color", "VARCHAR")
        _add_column_if_missing(conn, "shelfdesign", "last_forced_concept_count", "INTEGER DEFAULT 0")

        # --- フェーズ1: 属性タグ基盤（高さ・色の手動補正の出所を記録） ---
        _add_column_if_missing(conn, "registered_books", "spine_color_source", "VARCHAR DEFAULT 'auto_colorthief'")
        _add_column_if_missing(conn, "registered_books", "height_source", "VARCHAR DEFAULT 'ndl_extent'")

        # --- 被験者スコープの導入 ---
        rebuilt = []
        for model in (ShelfLayout, MyHand):
            if _rebuild_with_participant(conn, model):
                rebuilt.append(model.__tablename__)

        # ShelfDesign は UNIQUE の付け替えが不要なので列追加だけで済む。
        # ただし participant_id は UNIQUE なので、既存行が複数あると衝突する。
        if _table_exists(conn, "shelfdesign") and "participant_id" not in _columns(conn, "shelfdesign"):
            conn.execute(text("ALTER TABLE shelfdesign ADD COLUMN participant_id VARCHAR"))
            # 既存行は最初の1行だけを P00 の設定として残し、余分は捨てる
            # （単一ユーザ時代は first() しか読んでいなかったため）
            conn.execute(
                text("DELETE FROM shelfdesign WHERE id NOT IN (SELECT MIN(id) FROM shelfdesign)")
            )
            conn.execute(
                text("UPDATE shelfdesign SET participant_id = :pid WHERE participant_id IS NULL"),
                {"pid": DEFAULT_PARTICIPANT_ID},
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_shelfdesign_participant_id "
                    "ON shelfdesign (participant_id)"
                )
            )
            rebuilt.append("shelfdesign")

        if rebuilt:
            logger.info("migration: 被験者スコープを適用: %s", ", ".join(rebuilt))

        # --- My本棚の「過去/現在」2本棚化 ---
        rebuilt_period = []
        for model in (ShelfLayout, ShelfDesign):
            if _rebuild_with_period(conn, model):
                rebuilt_period.append(model.__tablename__)

        if rebuilt_period:
            logger.info("migration: 時期(period)スコープを適用: %s", ", ".join(rebuilt_period))

        # --- 本棚に同じ本を複数冊置けるように、ISBNのユニーク制約を外す ---
        _drop_unique_constraints_and_rebuild(conn, ShelfLayout)
