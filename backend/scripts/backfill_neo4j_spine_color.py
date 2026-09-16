"""registered_books.spine_color を Neo4j Book ノードへ同期する一回限りのスクリプト。

placement_analysis（背表紙色の分布分析）が Book.spine_color を参照するために必要。
add_book_with_meaning 経由だと participant_id や OWNS への副作用が絡むため、
ここでは Book ノードの spine_color プロパティだけを直接更新する。

実行:
    cd backend
    python -m scripts.backfill_neo4j_spine_color
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.main_kg.neo4j_driver import get_session

DB_PATH = Path(__file__).resolve().parent.parent / "bookshelf.db"


def run() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT isbn, spine_color FROM registered_books WHERE spine_color IS NOT NULL AND spine_color <> ''")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        print("spine_colorが設定された本がSQLiteにありません。")
        return

    with get_session() as session:
        result = session.run(
            """
            UNWIND $rows AS row
            MATCH (b:Book {isbn: row.isbn})
            SET b.spine_color = row.spine_color
            RETURN count(b) AS updated
            """,
            rows=rows,
        ).single()

    print(f"{result['updated'] if result else 0}/{len(rows)} 件の spine_color を Neo4j Book ノードへ反映しました。")


if __name__ == "__main__":
    run()
