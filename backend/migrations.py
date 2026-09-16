"""起動時に走らせる、既存 bookshelf.db 向けの軽量マイグレーション。

Alembic を入れていないので、必要な変更だけを冪等に適用する。
すべて「既に適用済みなら何もしない」形で書くこと。
"""
import logging

from sqlalchemy import text

from models import MyHand, ShelfDesign, ShelfLayout
from participant import DEFAULT_PARTICIPANT_ID

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

        # --- フェーズ2: 区切り確認を段単位からgap（本と本の間）単位に作り直し ---
        if _table_exists(conn, "section_awareness"):
            conn.execute(text("DROP TABLE section_awareness"))
            logger.info("migration: section_awareness を廃止しました（section_boundaryに置き換え）")

        # --- フェーズ2: 興味分野タグを固定語彙→現在棚にあるジャンルに変更 ---
        # 質問の意味そのものが変わった（固定16語彙への複数選択 → 棚にあるジャンルの
        # タップ順ランキング）ため、旧語彙での回答は新しい候補と噛み合わない。
        # rank列を足す一度きりのタイミングで、旧回答を消してから作り直す。
        if _table_exists(conn, "interest_tag") and "rank" not in _columns(conn, "interest_tag"):
            conn.execute(text("DELETE FROM interest_tag"))
            logger.info("migration: interest_tag の旧語彙による回答をクリアしました（質問仕様の変更のため）")
        _add_column_if_missing(conn, "interest_tag", "rank", "INTEGER DEFAULT 1")

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
