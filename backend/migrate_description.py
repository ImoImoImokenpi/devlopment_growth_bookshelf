"""
registered_books テーブルに description カラムを追加するスクリプト。
backend/ ディレクトリで実行してください:
  python migrate_description.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bookshelf.db"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.execute("PRAGMA table_info(registered_books)")
columns = [row[1] for row in cur.fetchall()]

if "description" in columns:
    print("OK: description column already exists")
else:
    cur.execute("ALTER TABLE registered_books ADD COLUMN description TEXT")
    conn.commit()
    print("OK: description column added")

conn.close()
