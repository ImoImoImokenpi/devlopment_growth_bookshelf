"""
registered_books の著者・出版社ノードと関係性を Neo4j に一括追加するスクリプト。
既存の Book ノードはそのまま、Author / Publisher ノードと
WRITTEN_BY / PUBLISHED_BY リレーションが追加される。
プロジェクトルートから実行:
  python backend/scripts/backfill_neo4j_relations.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from admin_neo4j.neo4j_crud import add_book_with_meaning

DB_PATH = Path(__file__).parent.parent / "bookshelf.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
    SELECT isbn, title, authors, publisher, published_year,
           ndc, pages, height_mm, size_label, cover, spine_image, description
    FROM registered_books
""")
books = cur.fetchall()
conn.close()

if not books:
    print("登録済みの本がありません。")
else:
    print(f"{len(books)} 冊の関係性を Neo4j に追加します...")
    ok, ng = 0, 0
    for b in books:
        book_dict = dict(b)
        try:
            add_book_with_meaning(book_dict)
            authors = book_dict.get("authors") or ""
            publisher = book_dict.get("publisher") or ""
            print(f"  [OK] {book_dict['isbn']}  著者={authors[:30]}  出版社={publisher}")
            ok += 1
        except Exception as e:
            print(f"  [NG] {book_dict['isbn']}  {e}")
            ng += 1

    print(f"\n完了: {ok} 件成功 / {ng} 件失敗")
