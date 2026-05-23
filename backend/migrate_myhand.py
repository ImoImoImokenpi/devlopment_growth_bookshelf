"""
myhand テーブルを新スキーマ（registered_book_id FK）に移行するスクリプト。
backend/ ディレクトリで実行してください:
  python migrate_myhand.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bookshelf.db"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# 旧テーブルに登録済みの ISBN を取得（registered_books に存在するものだけ引き継ぐ）
cur.execute("SELECT isbn FROM myhand")
old_isbns = [row[0] for row in cur.fetchall()]

# 旧テーブルを削除して新テーブルを作成
cur.execute("DROP TABLE IF EXISTS myhand")
cur.execute("""
    CREATE TABLE myhand (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        registered_book_id INTEGER NOT NULL UNIQUE
            REFERENCES registered_books(id)
    )
""")

# 旧データを引き継ぐ（registered_books に存在する ISBN のみ）
migrated = []
skipped  = []
for isbn in old_isbns:
    cur.execute("SELECT id FROM registered_books WHERE isbn = ?", (isbn,))
    row = cur.fetchone()
    if row:
        cur.execute("INSERT INTO myhand (registered_book_id) VALUES (?)", (row[0],))
        migrated.append(isbn)
    else:
        skipped.append(isbn)

conn.commit()
conn.close()

print(f"✓ 移行完了: {len(migrated)} 件")
if migrated:
    print("  引き継いだ ISBN:", migrated)
if skipped:
    print(f"  registered_books に存在しないためスキップ: {skipped}")
