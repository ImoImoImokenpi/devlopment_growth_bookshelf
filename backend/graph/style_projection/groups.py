"""グループ階層（サブグループ）の管理。

BELONGS_TO は「本が直接属する子グループ」だけを張り、HAS_SUBGROUP も
「親→直下の子」だけを張る（祖先への冗長なエッジは張らない）。そのため、
ある本の祖先グループ一覧や、階層の深さは HAS_SUBGROUP をたどって都度導出する。
"""
from __future__ import annotations

import statistics

from graph.main_kg.neo4j_driver import get_session


def get_ancestor_groups(shelved_id: str) -> list[dict]:
    """指定した本(ShelvedBook)が属する、直接の所属グループと
    その祖先グループすべてを depth の浅い順に返す。

    BELONGS_TO は直接の子グループにしか張られていないため、
    (ancestor)-[:HAS_SUBGROUP*0..]->(直接グループ) をたどって祖先を導出する。
    """
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:ShelvedBook {shelved_id: $shelved_id})-[:BELONGS_TO]->(g:Group)
            MATCH (ancestor:Group)-[:HAS_SUBGROUP*0..]->(g)
            RETURN DISTINCT ancestor.group_id AS group_id, ancestor.name AS name,
                   coalesce(ancestor.depth, 0) AS depth
            ORDER BY depth ASC
            """,
            shelved_id=shelved_id,
        )
        return [dict(r) for r in rows]


def recompute_group_depths(participant_id: str) -> int:
    """この参加者が作成したグループ群について、HAS_SUBGROUP チェーンから
    depth（ルート=0）を再計算し、Groupノードに書き戻す。
    ingest後や階層変更後にバッチで呼ぶ想定。戻り値は更新件数。"""
    with get_session() as session:
        session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:CREATED]->(root:Group)
            WHERE NOT (:Group)-[:HAS_SUBGROUP]->(root)
            SET root.depth = 0
            """,
            pid=participant_id,
        )
        result = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:CREATED]->(root:Group)
            WHERE NOT (:Group)-[:HAS_SUBGROUP]->(root)
            MATCH path = (root)-[:HAS_SUBGROUP*1..]->(descendant:Group)
            WITH descendant, min(length(path)) AS d
            SET descendant.depth = d
            RETURN count(descendant) AS updated
            """,
            pid=participant_id,
        ).single()
        return result["updated"] if result else 0


def get_shelf_group_overlay(participant_id: str) -> dict:
    """本棚ビジュアルにグルーピング状況を重ねて見せるための読み取り専用クエリ。
    構造指標(metrics.py)と違い、これは表示用なのでGroup.nameを含めてよい。
    isbn（Work.work_idと一致）を主キーに、参加者の本棚UIとそのまま突き合わせられる形で返す。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)-[:INSTANCE_OF]->(w:Work)
            OPTIONAL MATCH (s)-[:BELONGS_TO]->(g:Group)
            RETURN w.work_id AS isbn, collect(DISTINCT {group_id: g.group_id, name: g.name}) AS memberships
            """,
            pid=participant_id,
        )
        groups: dict[str, dict] = {}
        isolated_isbns: list[str] = []
        for r in rows:
            isbn = r["isbn"]
            memberships = [m for m in r["memberships"] if m.get("group_id")]
            if not memberships:
                isolated_isbns.append(isbn)
                continue
            for m in memberships:
                entry = groups.setdefault(m["group_id"], {"group_id": m["group_id"], "name": m["name"], "isbns": []})
                entry["isbns"].append(isbn)
        return {
            "groups": sorted(groups.values(), key=lambda g: -len(g["isbns"])),
            "isolated_isbns": isolated_isbns,
        }


def get_candidate_groups(owner_id: str, top_n: int = 3, min_size: int = 2) -> list[dict]:
    """観察画面の「部分推測」に出す候補グループを、システム側の基準で自動選定する。

    「帰属のギャップ」が出やすい（＝面白い差分になりやすい）グループを狙うため、
    次の3つのシグナルを合成したスコアで上位を選ぶ:
      - ジャンルの混在度（1グループ内のジャンルの種類数）
      - コメント文字数の合計（所有者の思い入れが強いグループほど言葉が多い想定）
      - グループサイズの極端さ（中央値からの乖離。極端に大きい/小さいグループ）

    戻り値には group_id と isbn一覧のみを含み、Group.name（意味データ）は含めない。
    名前を見せると閲覧者の推測の答えを教えてしまうため、この関数の呼び出し側は
    候補提示のUIでGroup.nameを絶対に表示しないこと。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)-[:BELONGS_TO]->(g:Group)
            MATCH (s)-[:INSTANCE_OF]->(w:Work)
            OPTIONAL MATCH (s)-[:HAS_COMMENT]->(c:Comment)
            WITH g, s, w, sum(size(coalesce(c.text, ''))) AS book_comment_chars
            WITH g,
                 collect(DISTINCT w.work_id) AS isbns,
                 collect(DISTINCT w.genre) AS genres,
                 sum(book_comment_chars) AS total_comment_chars
            RETURN g.group_id AS group_id, isbns,
                   [x IN genres WHERE x IS NOT NULL] AS genre_list,
                   total_comment_chars
            """,
            pid=owner_id,
        )
        candidates = [dict(r) for r in rows]

    eligible = [c for c in candidates if len(c["isbns"]) >= min_size]
    if not eligible:
        return []

    sizes = [len(c["isbns"]) for c in eligible]
    median_size = statistics.median(sizes)
    max_size_dev = max(abs(sz - median_size) for sz in sizes) or 1
    max_comment_chars = max((c["total_comment_chars"] or 0) for c in eligible) or 1
    max_genre_count = max(len(set(c["genre_list"])) for c in eligible) or 1

    scored = []
    for c in eligible:
        size = len(c["isbns"])
        genre_diversity = len(set(c["genre_list"])) / max_genre_count
        comment_volume = (c["total_comment_chars"] or 0) / max_comment_chars
        size_extremity = abs(size - median_size) / max_size_dev
        score = genre_diversity + comment_volume + size_extremity
        scored.append({"group_id": c["group_id"], "isbns": c["isbns"], "size": size, "_score": score})

    scored.sort(key=lambda c: -c["_score"])
    top = scored[:top_n]
    for c in top:
        c.pop("_score", None)
    return top


def get_group_semantic_content(group_id: str) -> dict:
    """指定グループの意味データ（name・所属本のComment本文）だけを返す。

    2.6 意味差分生成API専用。対象グループ以外のデータは一切含めないため、
    LLMへの入力を「このグループ限定」に絞れる（プロンプトインジェクション対策・
    分析範囲の限定）。構造指標側（metrics.py等）はこの関数を使わないこと。"""
    with get_session() as session:
        row = session.run(
            """
            MATCH (g:Group {group_id: $group_id})
            OPTIONAL MATCH (s:ShelvedBook)-[:BELONGS_TO]->(g)
            OPTIONAL MATCH (s)-[:HAS_COMMENT]->(c:Comment)
            RETURN g.name AS name, collect(DISTINCT c.text) AS comments
            """,
            group_id=group_id,
        ).single()
        if not row:
            return {"name": None, "comments": []}
        return {"name": row["name"], "comments": [c for c in row["comments"] if c]}


def get_max_group_depth(participant_id: str) -> int:
    with get_session() as session:
        row = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:CREATED]->(g:Group)
            RETURN max(coalesce(g.depth, 0)) AS max_depth
            """,
            pid=participant_id,
        ).single()
        return row["max_depth"] if row and row["max_depth"] is not None else 0
