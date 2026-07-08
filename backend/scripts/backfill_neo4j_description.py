"""
registered_books の全フィールド（description含む）を Neo4j Book ノードに再同期するスクリプト。
add_book_with_meaning は MERGE を使うので既存ノードの上書き更新が安全にできる。
※ 一部カラムのみ渡すと未指定カラムが NULL 上書きされるため、必ず全カラムを渡すこと。
プロジェクトルートから実行:
  python backend/scripts/backfill_neo4j_description.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from admin_neo4j.neo4j_crud import add_book_with_meaning
from admin_neo4j.neo4j_driver import get_session

DB_PATH = Path(__file__).parent.parent / "bookshelf.db"

with get_session() as session:
    existing_isbns = {r["isbn"] for r in session.run("MATCH (b:Book) RETURN b.isbn AS isbn").data()}

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur  = conn.cursor()
cur.execute("""
    SELECT isbn, title, authors, publisher, published_year,
           ndc, pages, height_mm, size_label, spine_image, cover, description
    FROM registered_books
""")
books = [b for b in cur.fetchall() if b["isbn"] in existing_isbns]
conn.close()

print(f"Neo4j上の既存ノード {len(existing_isbns)} 件のうち、{len(books)} 件がSQLiteと一致（新規ノードは作成しません）")

if not books:
    print("registered_books にデータがありません。")
else:
    print(f"{len(books)} 冊を Neo4j に再同期します...")
    updated = 0
    for b in books:
        book_dict = dict(b)
        try:
            add_book_with_meaning(book_dict)
            updated += 1
            desc = book_dict.get("description")
            print(f"  [OK] {book_dict['isbn']}  description={'あり' if desc else 'なし'}")
        except Exception as e:
            print(f"  [NG] {book_dict['isbn']}  {e}")

    print(f"\n完了: {updated}/{len(books)} 冊を反映しました。")
