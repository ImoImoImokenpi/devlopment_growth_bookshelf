"""(3) 著者管理: 表記ゆれの正規化と統合候補の提示。

既存の (:Book)-[:WRITTEN_BY]->(:Author {name}) は完全一致でMERGEされるため、
"山田太郎" と "山田 太郎" のような表記ゆれは別ノードに分裂する。

ここでは Author ノードを削除・統合（破壊的マージ）はせず、
  - canonicalName プロパティを全Authorに付与（空白・全角半角の差を吸収した比較キー）
  - 研究者が確認の上で明示的に呼ぶ merge_author_alias() で
    (:Author)-[:ALIAS_OF]->(:Author) を張り、alias側の著作をprimary側にも複製する
という非破壊的な方針にする。他の分析コードが旧 name を参照していても壊れない。
"""
from __future__ import annotations

import re
import unicodedata

from graph.main_kg.neo4j_driver import get_session


def normalize_author_name(raw: str | None) -> str | None:
    """空白（全角含む）を除去し、NFKC正規化（全角英数→半角等）した比較用キー。
    日本語の人名は「姓 姓」のように空白の有無だけが揺れることが多いため、
    空白は保持せず完全に除去する。"""
    if not raw:
        return None
    normalized = unicodedata.normalize("NFKC", raw)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized or None


def sync_author_canonical_names() -> int:
    """全Authorノードにcanonical_nameを付与する（既存のnameは変えない）。戻り値は更新件数。"""
    with get_session() as session:
        rows = session.run("MATCH (a:Author) RETURN a.name AS name").data()
        updates = [
            {"name": r["name"], "canonical": normalize_author_name(r["name"])}
            for r in rows if r["name"]
        ]
        updates = [u for u in updates if u["canonical"]]
        if updates:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Author {name: row.name})
                SET a.canonicalName = row.canonical
                """,
                rows=updates,
            )
        return len(updates)


def find_author_duplicate_groups() -> list[dict]:
    """canonicalNameが同じで元のnameの表記が違う（表記ゆれの疑いがある）Authorの
    グループを返す。研究者向け管理APIで統合候補として提示する。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (a:Author)
            WHERE a.canonicalName IS NOT NULL
            WITH a.canonicalName AS canonical, collect(DISTINCT a.name) AS names
            WHERE size(names) > 1
            RETURN canonical, names
            ORDER BY canonical
            """
        ).data()
        return rows


def merge_author_alias(primary_name: str, alias_name: str) -> bool:
    """研究者が確認した上で、alias_name の著作をprimary_nameへ付け替える。
    Authorノード自体は削除せず、(:alias)-[:ALIAS_OF]->(:primary) を張った上で
    aliasの著作にもprimaryからのWRITTEN_BYを追加する（aliasからも辿れるため、
    旧nameを参照しているコードが壊れない）。

    注意: count()等の集約はマッチ0件でも1行（0）を返すため、単純に
    「結果行があるか」だけでは存在確認にならない。先に両ノードの存在を
    明示的に確認してから統合処理を行う。"""
    if primary_name == alias_name:
        return False
    with get_session() as session:
        existence = session.run(
            """
            OPTIONAL MATCH (primary:Author {name: $primary_name})
            OPTIONAL MATCH (alias:Author {name: $alias_name})
            RETURN primary IS NOT NULL AS primary_exists, alias IS NOT NULL AS alias_exists
            """,
            primary_name=primary_name,
            alias_name=alias_name,
        ).single()
        if not existence or not existence["primary_exists"] or not existence["alias_exists"]:
            return False

        session.run(
            """
            MATCH (primary:Author {name: $primary_name})
            MATCH (alias:Author {name: $alias_name})
            MERGE (alias)-[:ALIAS_OF]->(primary)
            WITH primary, alias
            OPTIONAL MATCH (alias)<-[:WRITTEN_BY]-(b:Book)
            FOREACH (book IN CASE WHEN b IS NULL THEN [] ELSE [b] END |
                MERGE (book)-[:WRITTEN_BY]->(primary)
            )
            """,
            primary_name=primary_name,
            alias_name=alias_name,
        )
        return True


def author_group_key(canonical_name: str | None, raw_name: str | None) -> str | None:
    """本の「著者グルーピング」判定に使う比較キー。canonicalNameがあればそれを
    優先し、無ければその場でnormalizeする（sync未実行のAuthorでも動くように）。"""
    return canonical_name or normalize_author_name(raw_name)
