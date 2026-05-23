"""
registered_books の description が NULL の本を OpenBD で一括補完するスクリプト。
backend/ ディレクトリで実行:
  python backfill_descriptions.py
"""
import asyncio
import sqlite3
import httpx
from pathlib import Path

DB_PATH  = Path(__file__).parent / "bookshelf.db"
OPENBD          = "https://api.openbd.jp/v1/get"
GOOGLE_BOOKS    = "https://www.googleapis.com/books/v1/volumes"
BATCH           = 50
ACCEPTED_TEXT_TYPES = {"02", "03"}


async def fetch_openbd_batch(client: httpx.AsyncClient, isbns: list) -> dict:
    r = await client.get(OPENBD, params={"isbn": ",".join(isbns)})
    r.raise_for_status()
    results = {}
    for item in r.json():
        if not item:
            continue
        isbn = item.get("summary", {}).get("isbn", "")
        for tc in item.get("onix", {}).get("CollateralDetail", {}).get("TextContent", []):
            if tc.get("TextType") in ACCEPTED_TEXT_TYPES:
                text = tc.get("Text", "").strip()
                if text:
                    results[isbn] = text
                    break
    return results


async def fetch_google_desc(client: httpx.AsyncClient, isbn: str) -> str | None:
    r = await client.get(GOOGLE_BOOKS, params={"q": f"isbn:{isbn}"}, timeout=10)
    if r.status_code == 429:
        print(f"  [Google] rate limited (429), stopping Google Books fetch")
        raise RuntimeError("rate_limited")
    r.raise_for_status()
    items = r.json().get("items")
    if not items:
        return None
    return items[0].get("volumeInfo", {}).get("description") or None


async def main():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT isbn FROM registered_books WHERE description IS NULL OR description = ''")
    targets = [r[0] for r in cur.fetchall()]

    if not targets:
        print("All books already have descriptions.")
        conn.close()
        return

    print(f"Fetching descriptions for {len(targets)} books...")

    updated = 0
    async with httpx.AsyncClient(timeout=15) as client:
        # Step 1: OpenBD (batch)
        for i in range(0, len(targets), BATCH):
            batch = targets[i:i + BATCH]
            try:
                descs = await fetch_openbd_batch(client, batch)
            except Exception as e:
                print(f"  OpenBD error: {e}")
                descs = {}
            for isbn, desc in descs.items():
                cur.execute(
                    "UPDATE registered_books SET description = ? WHERE isbn = ?",
                    (desc, isbn),
                )
                updated += 1
                print(f"  [OpenBD] {isbn}  {desc[:60]}...")

        conn.commit()

        # Step 2: Google Books for remaining
        cur.execute("SELECT isbn FROM registered_books WHERE description IS NULL OR description = ''")
        remaining = [r[0] for r in cur.fetchall()]
        print(f"Trying Google Books for {len(remaining)} remaining books...")
        for isbn in remaining:
            try:
                desc = await fetch_google_desc(client, isbn)
            except RuntimeError:
                break
            except Exception as e:
                print(f"  [Google] {isbn} error: {e}")
                desc = None
            if desc:
                cur.execute(
                    "UPDATE registered_books SET description = ? WHERE isbn = ?",
                    (desc, isbn),
                )
                updated += 1
                print(f"  [Google] {isbn}  {desc[:60]}...")
            else:
                print(f"  [Google] {isbn}  no description")
            await asyncio.sleep(0.5)  # Google Books レート制限を避ける

    conn.commit()
    conn.close()
    print(f"\nDone: {updated}/{len(targets)} books updated.")


if __name__ == "__main__":
    asyncio.run(main())
