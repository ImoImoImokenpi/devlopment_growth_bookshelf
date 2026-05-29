"""
registered_books の ndc が NULL の本を NDL SRU API で一括補完するスクリプト。
プロジェクトルートから実行:
  python backend/scripts/backfill_ndc.py
"""
import asyncio
import re
import sqlite3
import httpx
from pathlib import Path
from lxml import etree

DB_PATH     = Path(__file__).parent.parent / "bookshelf.db"
NDL_SRU_URL = "https://ndlsearch.ndl.go.jp/api/sru"
BIB_NS = {
    "rdf":     "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dcterms": "http://purl.org/dc/terms/",
    "dc":      "http://purl.org/dc/elements/1.1/",
    "dcndl":   "http://ndl.go.jp/dcndl/terms/",
    "foaf":    "http://xmlns.com/foaf/0.1/",
}
SRW_NS = {"srw": "http://www.loc.gov/zing/srw/"}


RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NDC9_PREFIX = "http://id.ndl.go.jp/class/ndc9/"


def _extract_ndc_from_bib(bib):
    """
    BibResource ノードから NDC を抽出。
    - dc:subject テキスト（旧形式）
    - dcterms:subject rdf:resource="…/ndc9/NNN" 属性（新形式）
    の両方に対応する。
    """
    # 旧形式: dc:subject テキスト
    for s in bib.xpath("dc:subject/text()", namespaces=BIB_NS):
        if re.match(r"\d{3}", s):
            return s

    # 新形式: dcterms:subject rdf:resource 属性
    rdf_resource_attr = f"{{{RDF_NS}}}resource"
    for el in bib.xpath("dcterms:subject", namespaces=BIB_NS):
        resource = el.get(rdf_resource_attr, "")
        if resource.startswith(NDC9_PREFIX):
            return resource[len(NDC9_PREFIX):]

    return None


async def fetch_ndc(client: httpx.AsyncClient, isbn: str):
    params = {
        "operation":      "searchRetrieve",
        "query":          f'isbn="{isbn}"',
        "maximumRecords": 1,
        "recordSchema":   "dcndl",
    }
    try:
        r = await client.get(NDL_SRU_URL, params=params, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  [NDL] {isbn} fetch error: {e}")
        return None

    try:
        root = etree.fromstring(r.content)
    except etree.XMLSyntaxError:
        return None

    record_nodes = root.xpath("//srw:recordData", namespaces=SRW_NS)
    if not record_nodes:
        return None

    raw_text = (record_nodes[0].text or "").strip()
    if not raw_text:
        return None

    try:
        rdf = etree.fromstring(raw_text.encode("utf-8"))
    except etree.XMLSyntaxError:
        return None

    bib_list = rdf.xpath(".//dcndl:BibResource", namespaces=BIB_NS)
    if not bib_list:
        return None

    return _extract_ndc_from_bib(bib_list[0])


async def main():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT isbn FROM registered_books WHERE ndc IS NULL OR ndc = ''")
    targets = [r[0] for r in cur.fetchall()]

    if not targets:
        print("All books already have NDC.")
        conn.close()
        return

    print(f"Fetching NDC for {len(targets)} books...")

    updated = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for isbn in targets:
            ndc = await fetch_ndc(client, isbn)
            if ndc:
                cur.execute(
                    "UPDATE registered_books SET ndc = ? WHERE isbn = ?",
                    (ndc, isbn),
                )
                updated += 1
                print(f"  [OK] {isbn} -> {ndc}")
            else:
                print(f"  [--] {isbn}  NDC not found")
            await asyncio.sleep(0.3)

    conn.commit()
    conn.close()
    print(f"\nDone: {updated}/{len(targets)} books updated.")


if __name__ == "__main__":
    asyncio.run(main())
