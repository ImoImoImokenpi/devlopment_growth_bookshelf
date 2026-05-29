"""
spine_color が未設定のレコードを spine_image ファイルから補完するスクリプト。
プロジェクトルートから実行:
  python backend/scripts/backfill_spine_color.py
"""
from pathlib import Path

from colorthief import ColorThief
import sqlite3

DB_PATH    = Path(__file__).parent.parent / "bookshelf.db"
IMAGE_ROOT = Path(__file__).parent.parent.parent / "frontend" / "public"


def extract_dominant_color(image_path: Path) -> str | None:
    try:
        r, g, b = ColorThief(str(image_path)).get_color(quality=1)
        return f"{r},{g},{b}"
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None


conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.execute(
    "SELECT isbn, spine_image FROM registered_books WHERE spine_image IS NOT NULL"
)
rows = cur.fetchall()
print(f"対象: {len(rows)} 件（全件再計算）")

updated = 0
skipped = 0
for isbn, spine_image in rows:
    image_path = IMAGE_ROOT / spine_image.lstrip("/")
    if not image_path.exists():
        print(f"  [SKIP] {isbn} — ファイルなし: {image_path}")
        skipped += 1
        continue

    color = extract_dominant_color(image_path)
    if color:
        cur.execute(
            "UPDATE registered_books SET spine_color = ? WHERE isbn = ?",
            (color, isbn),
        )
        print(f"  [OK]   {isbn} -> {color}")
        updated += 1
    else:
        print(f"  [FAIL] {isbn} — 色抽出失敗")
        skipped += 1

conn.commit()
conn.close()
print(f"\n完了: {updated} 件更新 / {skipped} 件スキップ")
