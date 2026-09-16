"""ISBN→書名の簡易ルックアップ。研究者向け・参加者向け画面で、どの本の話を
しているかを一目でわかるようにするための共通ヘルパー。Book.titleは全参加者
共有の客観データなので、どのモジュールから呼んでも問題ない。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session


def fetch_titles(isbns: list[str]) -> dict[str, str]:
    if not isbns:
        return {}
    with get_session() as session:
        rows = session.run(
            "MATCH (b:Book) WHERE b.isbn IN $isbns RETURN b.isbn AS isbn, b.title AS title",
            isbns=list(set(isbns)),
        ).data()
        return {r["isbn"]: r["title"] for r in rows}


def attach_titles(items: list[dict], isbns_key: str = "isbns") -> list[dict]:
    """items内の各要素が持つISBNリスト（isbns_keyで指定）から書名一覧を引いて
    "titles" キー（isbnsと同じ順序）を追加する。"""
    all_isbns = [isbn for item in items for isbn in item.get(isbns_key, [])]
    titles = fetch_titles(all_isbns)
    for item in items:
        item["titles"] = [titles.get(isbn) or isbn for isbn in item.get(isbns_key, [])]
    return items
