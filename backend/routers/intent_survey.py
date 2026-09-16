"""フェーズ2: 意図を明示的に聞く機能（最小構成）。

(a) 優先度質問  (b) 区切り確認  (c) 興味分野質問 の3つを扱う。

重要な制約（依頼文より）:
  - いずれも、配置パターンから統計的に推定した暗黙の優先度
    （graph.placement_analysis の PlacementProfile / DesignEvidence）を
    一切見せずに回答させること。このモジュールは意図的にそれらを
    importしない・参照しない。将来ここにPlacementProfileの結果を
    混ぜて「答え合わせ」を先に見せてしまうと、アンカリングで研究データが
    汚染されるため、触れないこと自体を設計上のガードにしている。
  - (c)は配置画面と同時に見せない。フロント側は独立したページ/導線から
    しか呼ばない想定（このルータ自体は配置APIと物理的に無関係）。
"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import PriorityResponse, SectionBoundary, InterestTag, ShelfLayout, RegisteredBook, GenreTag
from participant import resolve_participant_id
from schemas import PriorityRequest, SectionAwarenessRequest, InterestTagRequest

router = APIRouter(prefix="/intent-survey", tags=["intent-survey"])

PRIORITY_CHOICES = {
    "height":   "高さ",
    "genre":    "ジャンル",
    "color":    "色",
    "author":   "著者",
    "interest": "興味の強さ",
    "none":     "特に意識していない",
}


# ============================================================
# (a) 優先度質問
# ============================================================

@router.get("/priority")
def get_priority(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    latest = (
        db.query(PriorityResponse)
        .filter(PriorityResponse.participant_id == participant_id)
        .order_by(PriorityResponse.created_at.desc())
        .first()
    )
    return {
        "answered": latest is not None,
        "choice": latest.choice if latest else None,
        "choices": PRIORITY_CHOICES,
    }


@router.post("/priority")
def post_priority(
    body: PriorityRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    if body.choice not in PRIORITY_CHOICES:
        raise HTTPException(status_code=422, detail=f"choice は {list(PRIORITY_CHOICES)} のいずれかにしてください")
    db.add(PriorityResponse(participant_id=participant_id, choice=body.choice))
    db.commit()
    return {"answered": True, "choice": body.choice}


# ============================================================
# (b) 区切り確認
#
# 段(shelf_index)単位ではなく、実際に並んでいる本と本の「間」を単位にする。
# 既存の配置順（x_posでソート）から機械的に「間」の一覧を作り、それぞれを
# ON/OFFでタップ選択させるだけ。自由に線を引かせる操作はしない。
# ============================================================

def _shelf_books_by_row(db: Session, participant_id: str) -> dict[int, list]:
    rows = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.participant_id == participant_id)
        .order_by(ShelfLayout.shelf_index, ShelfLayout.x_pos)
        .all()
    )
    by_shelf: dict[int, list] = defaultdict(list)
    for row in rows:
        by_shelf[row.shelf_index].append(row)
    return by_shelf


@router.get("/shelf")
def get_shelf_for_boundary_picker(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """(b)を「本棚上を直接選ぶ」形にするための、段ごとの本の並び。
    実配置(x_pos順)そのままに、見た目の再現に必要な最小限の書誌属性
    （表紙・代表色・サイズ）を添えて返す。並べ方の推定結果（PlacementProfile等）は
    一切含まない——ここにあるのは今の配置そのものであり、推定ではない。"""
    by_shelf = _shelf_books_by_row(db, participant_id)
    isbns = [row.isbn for books in by_shelf.values() for row in books]
    books_by_isbn = {
        b.isbn: b
        for b in db.query(RegisteredBook).filter(RegisteredBook.isbn.in_(isbns)).all()
    }
    boundary_map = {
        (b.shelf_index, b.gap_index): b.is_intentional
        for b in db.query(SectionBoundary).filter(SectionBoundary.participant_id == participant_id).all()
    }

    def _spine(row):
        b = books_by_isbn.get(row.isbn)
        return {
            "isbn":         row.isbn,
            "title":        b.title if b else None,
            "spine_image":  b.spine_image if b else None,
            "spine_color":  b.spine_color if b else None,
            "height_mm":    b.height_mm if b else None,
            "pages":        b.pages if b else None,
        }

    shelves = []
    for shelf_index in sorted(by_shelf):
        books = by_shelf[shelf_index]
        shelves.append({
            "shelf_index": shelf_index,
            "books": [_spine(row) for row in books],
            "boundaries": [
                boundary_map.get((shelf_index, gap_index), False)
                for gap_index in range(max(0, len(books) - 1))
            ],
        })
    return shelves


@router.get("/sections")
def list_sections(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """段ごとに、隣り合う本の「間」を左から順に一覧する（分析・エクスポート用の
    フラットな一覧。フロントの選択UIは /intent-survey/shelf を使う）。"""
    by_shelf = _shelf_books_by_row(db, participant_id)
    isbns = [row.isbn for books in by_shelf.values() for row in books]
    titles = {
        b.isbn: b.title
        for b in db.query(RegisteredBook.isbn, RegisteredBook.title).filter(RegisteredBook.isbn.in_(isbns)).all()
    }
    boundary_map = {
        (b.shelf_index, b.gap_index): b.is_intentional
        for b in db.query(SectionBoundary).filter(SectionBoundary.participant_id == participant_id).all()
    }

    gaps = []
    for shelf_index in sorted(by_shelf):
        books = by_shelf[shelf_index]
        for gap_index in range(len(books) - 1):
            left, right = books[gap_index], books[gap_index + 1]
            gaps.append({
                "shelf_index":     shelf_index,
                "gap_index":       gap_index,
                "left":            {"isbn": left.isbn, "title": titles.get(left.isbn)},
                "right":           {"isbn": right.isbn, "title": titles.get(right.isbn)},
                "is_intentional":  boundary_map.get((shelf_index, gap_index), False),
            })
    return gaps


@router.post("/sections/{shelf_index}/{gap_index}")
def set_section_boundary(
    shelf_index: int,
    gap_index: int,
    body: SectionAwarenessRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    books = _shelf_books_by_row(db, participant_id).get(shelf_index, [])
    if gap_index < 0 or gap_index + 1 >= len(books):
        raise HTTPException(status_code=404, detail="指定された区切りが見つかりません")
    left, right = books[gap_index], books[gap_index + 1]

    row = (
        db.query(SectionBoundary)
        .filter(
            SectionBoundary.participant_id == participant_id,
            SectionBoundary.shelf_index == shelf_index,
            SectionBoundary.gap_index == gap_index,
        )
        .first()
    )
    if row:
        row.is_intentional = body.is_intentional
        row.left_isbn, row.right_isbn = left.isbn, right.isbn
    else:
        db.add(SectionBoundary(
            participant_id=participant_id, shelf_index=shelf_index, gap_index=gap_index,
            left_isbn=left.isbn, right_isbn=right.isbn, is_intentional=body.is_intentional,
        ))
    db.commit()
    return {"shelf_index": shelf_index, "gap_index": gap_index, "is_intentional": body.is_intentional}


# ============================================================
# (c) 興味分野質問（配置画面とは独立した画面専用）
#
# 選択肢は固定語彙ではなく「現在棚に並んでいる本のジャンルタグ」
# （フェーズ1のGenreTag。ndc_auto/manual両方、ShelfLayoutにある本に限る）
# から動的に作る。タップした順番がそのまま興味の強い順になる
# （フルランキングは強制しない。興味がある分だけタップすればよい）。
#
# 注意（設計トレードオフ）: 依頼文の原則は「(c)は配置内容を一切見せない」
# だったが、本人からの明示的な指示でジャンル一覧を見せる方式に変更した。
# 見せているのは「自分が今持っているジャンルの集合」であり、並べ方
# （PlacementProfile等の推定結果）そのものではないため、位置情報由来の
# アンカリングは避けられている。ただし「自分の蔵書を意識した上で答える」
# 形にはなるため、完全に独立した自己申告ではなくなる点は留意。
# ============================================================

def _current_genre_candidates(db: Session, participant_id: str) -> list[dict]:
    shelved_isbns = {
        row[0] for row in
        db.query(ShelfLayout.isbn).filter(ShelfLayout.participant_id == participant_id).all()
    }
    if not shelved_isbns:
        return []
    counts: dict[str, int] = defaultdict(int)
    for t in (
        db.query(GenreTag)
        .filter(GenreTag.participant_id == participant_id, GenreTag.isbn.in_(shelved_isbns))
        .all()
    ):
        counts[t.tag] += 1
    return sorted(
        [{"tag": tag, "book_count": n} for tag, n in counts.items()],
        key=lambda x: (-x["book_count"], x["tag"]),
    )


@router.get("/interests")
def list_interests(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    ranked = (
        db.query(InterestTag)
        .filter(InterestTag.participant_id == participant_id)
        .order_by(InterestTag.rank)
        .all()
    )
    return {
        "genres": _current_genre_candidates(db, participant_id),
        "ranked": [{"tag": r.tag, "rank": r.rank} for r in ranked],
    }


@router.post("/interests")
def add_interest(
    body: InterestTagRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    candidates = {c["tag"] for c in _current_genre_candidates(db, participant_id)}
    if body.tag not in candidates:
        raise HTTPException(status_code=422, detail="現在棚にあるジャンルの中から選んでください")

    exists = (
        db.query(InterestTag)
        .filter(InterestTag.participant_id == participant_id, InterestTag.tag == body.tag)
        .first()
    )
    if not exists:
        max_rank = (
            db.query(InterestTag)
            .filter(InterestTag.participant_id == participant_id)
            .count()
        )
        db.add(InterestTag(participant_id=participant_id, tag=body.tag, rank=max_rank + 1))
        db.commit()
    return list_interests(db, participant_id)


@router.delete("/interests/{tag}")
def remove_interest(
    tag: str,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    row = (
        db.query(InterestTag)
        .filter(InterestTag.participant_id == participant_id, InterestTag.tag == tag)
        .first()
    )
    if row:
        removed_rank = row.rank
        db.delete(row)
        # 抜けた順位を詰め直し、次にタップしたときの順位が正しく続くようにする
        for later in (
            db.query(InterestTag)
            .filter(InterestTag.participant_id == participant_id, InterestTag.rank > removed_rank)
            .all()
        ):
            later.rank -= 1
        db.commit()
    return list_interests(db, participant_id)


# ============================================================
# 分析用: フェーズ1属性・配置座標・フェーズ2回答をまとめて取り出す
# ============================================================

@router.get("/export")
def export_for_analysis(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """participant_id をキーに、属性(フェーズ1)・配置座標・意図の自己申告(フェーズ2)を
    1つにまとめて返す。分析側はこれをそのまま pandas.json_normalize 等に渡せる。"""
    priority = (
        db.query(PriorityResponse)
        .filter(PriorityResponse.participant_id == participant_id)
        .order_by(PriorityResponse.created_at.desc())
        .first()
    )

    sections = list_sections(db, participant_id)
    interests = list_interests(db, participant_id)

    genre_tags_by_isbn: dict[str, list[dict]] = {}
    for t in db.query(GenreTag).filter(GenreTag.participant_id == participant_id).all():
        genre_tags_by_isbn.setdefault(t.isbn, []).append({"tag": t.tag, "origin": t.origin})

    books = []
    layout_by_isbn = {
        row.isbn: {"shelf_index": row.shelf_index, "x_pos": row.x_pos, "order_index": row.order_index}
        for row in db.query(ShelfLayout).filter(ShelfLayout.participant_id == participant_id).all()
    }
    for b in db.query(RegisteredBook).filter(RegisteredBook.isbn.in_(layout_by_isbn.keys())).all():
        books.append({
            "isbn":               b.isbn,
            "title":              b.title,
            "authors":            b.authors.split(",") if b.authors else [],
            "height_mm":          b.height_mm,
            "height_source":      b.height_source,
            "spine_color":        b.spine_color,
            "spine_color_source": b.spine_color_source,
            "ndc":                b.ndc,
            "genre_tags":         genre_tags_by_isbn.get(b.isbn, []),
            "placement":          layout_by_isbn.get(b.isbn),
        })

    return {
        "participant_id": participant_id,
        "priority_response": {"choice": priority.choice, "answered_at": priority.created_at.isoformat()} if priority else None,
        "section_boundaries": sections,
        "interest_ranking": interests["ranked"],
        "books": books,
    }
