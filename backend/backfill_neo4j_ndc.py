"""
registered_books の NDC を Neo4j Book ノードに反映するスクリプト。
add_book_with_meaning は MERGE を使うので既存ノードの上書き更新が安全にできる。
backend/ ディレクトリで実行:
  python backfill_neo4j_ndc.py
"""
import sqlite3
from pathlib import Path
from admin_neo4j.neo4j_crud import add_book_with_meaning

DB_PATH = Path(__file__).parent / "bookshelf.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur  = conn.cursor()
cur.execute("""
    SELECT isbn, title, authors, publisher, published_year,
           ndc, pages, height_mm, cover
    FROM registered_books
    WHERE ndc IS NOT NULL AND ndc != ''
""")
books = cur.fetchall()
conn.close()

if not books:
    print("NDCが設定された本がありません。")
else:
    print(f"{len(books)} 冊の NDC 接続を Neo4j に反映します...")
    for b in books:
        book_dict = dict(b)
        try:
            add_book_with_meaning(book_dict)
            print(f"  [OK] {book_dict['isbn']}  NDC={book_dict['ndc']}")
        except Exception as e:
            print(f"  [NG] {book_dict['isbn']}  {e}")

    print("\n完了")
