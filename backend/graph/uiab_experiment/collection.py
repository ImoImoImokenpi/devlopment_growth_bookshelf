"""時期別の蔵書申告。

書誌情報そのもの(:Book)は main_kg と同じ客観データとして共有する
(ISBNが同じなら同じ本なので、研究をまたいでも共有して問題ない)。
「どの参加者の、どの時期の蔵書か」だけを UiabParticipant-[:COLLECTED]->Book
で表す。

新UI側の「色・厚みを可能な限り再現した見た目」のうち、厚み(height_mm)は
書誌情報(NDL)から自動で決まるが、色は本来なら背表紙写真からの自動抽出が
要る。今回は「数年前」の本を参加者が物理的に持っていない/撮影できない
ケースを想定し、色は任意の手動指定（未指定ならニュートラルな既定色）にした。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session

DEFAULT_SPINE_COLOR = "150,140,120"  # 未指定時のニュートラルな既定色


def _ensure_book_node(isbn: str, book: dict) -> None:
    """main_kgのadd_book_with_meaningと違い、Participant/OWNSには一切触れない。
    書誌データ(:Book)だけをMERGEする。

    :Book は「投影のズレ」研究(main_kg)と共有のノードなので、ここから
    無条件に上書きしてはいけない。ON CREATE SET だけを使い、既に存在する
    Bookノード（＝main_kg側で登録済みの本）は一切書き換えない。
    この参加者の申告内容と既存データが食い違っていても、共有ノードを
    書き換えるのではなく、その違いは無視する（採用するなら別プロパティに
    分けて持たせるべきで、今回のMVP範囲では行わない）。"""
    with get_session() as session:
        session.run(
            """
            MERGE (b:Book {isbn: $isbn})
            ON CREATE SET
                b.title          = $title,
                b.authors        = $authors,
                b.publisher      = $publisher,
                b.published_year = $published_year,
                b.cover          = $cover,
                b.height_mm      = $height_mm,
                b.pages          = $pages,
                b.spine_color    = coalesce($spine_color, $default_color),
                b.updatedAt      = datetime()
            """,
            isbn=isbn,
            title=book.get("title"),
            authors=book.get("authors"),
            publisher=book.get("publisher"),
            published_year=book.get("published_year"),
            cover=book.get("cover"),
            height_mm=book.get("height_mm") or 180,
            pages=book.get("pages") or 200,
            spine_color=book.get("spine_color"),
            default_color=DEFAULT_SPINE_COLOR,
        )


def add_to_collection(participant_id: str, period: str, isbn: str, book: dict) -> None:
    _ensure_book_node(isbn, book)
    with get_session() as session:
        session.run(
            """
            MERGE (p:UiabParticipant {participantId: $pid})
            WITH p
            MATCH (b:Book {isbn: $isbn})
            MERGE (p)-[c:COLLECTED {period: $period}]->(b)
                ON CREATE SET c.addedAt = datetime()
            """,
            pid=participant_id,
            isbn=isbn,
            period=period,
        )


def remove_from_collection(participant_id: str, period: str, isbn: str) -> None:
    with get_session() as session:
        session.run(
            """
            MATCH (:UiabParticipant {participantId: $pid})
                  -[c:COLLECTED {period: $period}]->(:Book {isbn: $isbn})
            DELETE c
            """,
            pid=participant_id,
            isbn=isbn,
            period=period,
        )


def list_collection(participant_id: str, period: str) -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:UiabParticipant {participantId: $pid})
                  -[:COLLECTED {period: $period}]->(b:Book)
            RETURN b.isbn AS isbn, b.title AS title, b.authors AS authors,
                   b.publisher AS publisher, b.published_year AS published_year,
                   b.cover AS cover, b.height_mm AS height_mm, b.pages AS pages,
                   b.spine_color AS spine_color
            ORDER BY b.title
            """,
            pid=participant_id,
            period=period,
        )
        return [dict(r) for r in rows]
