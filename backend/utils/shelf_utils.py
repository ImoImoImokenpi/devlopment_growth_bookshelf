from sqlalchemy.orm import Session
from models import ShelfLayout, ShelfDesign, MyHand
from admin_neo4j.neo4j_crud import groups_from_neo4j, update_shelf_layout_chain
import random
import logging

logger = logging.getLogger(__name__)

# ── サイズ計算 ────────────────────────────────────────────────

SHELF_MAX_WIDTH_PX = 800  # ShelfDesign.shelf_max_width に置き換えてもよい

SCALE = 0.9

def calc_virtual_width(pages: int | None) -> int:
    if not pages:
        return 20
    return int(pages * 0.065)  # SCALEなしでもOK

def calc_spine_height_px(height_mm: int | None) -> int:
    if not height_mm:
        return 180

    raw = height_mm * SCALE
    return int(min(220, max(140, raw)))

def spine_fields(book):
    return {
        "width_unit": calc_virtual_width(book.pages),
        "height_mm": book.height_mm,
        "cover": book.cover,
        "size_label": book.size_label,
    }

# ── 外部API ──────────────────────────────────────────────────

def add_to_shelf(db: Session, book) -> bool:
    if db.query(ShelfLayout).filter(ShelfLayout.isbn == book.isbn).first():
        return False

    try:
        existing_count = db.query(ShelfLayout).count()

        if existing_count == 0:
            _rebuild_all(db, trigger_book=book)
        else:
            _place_one(db, book)

        db.commit()
        return True

    except Exception as e:
        db.rollback()   # ← ★これ絶対必要
        logger.error(f"[add_to_shelf] 配置エラー [{book.isbn}]: {e}")
        return False


def rebuild_shelf_from_neo4j(db: Session):
    """
    Neo4jのグループ順で棚全体を再構築する。
    本棚の並び替え後などに呼ぶ。
    """
    _rebuild_all(db, trigger_book=None)
    db.flush()
    # _sync_to_neo4j(db)

# ── 内部: 全体再構築 ──────────────────────────────────────────

def _rebuild_all(db: Session, trigger_book=None):
    """
    Neo4jのグループ順にISBNを並べ、棚幅(px)で折り返して配置する。
    trigger_book がNeo4jに未登録なら末尾追加。
    """
    design = _get_design(db)
    shelf_max_px = getattr(design, "shelf_max_width", SHELF_MAX_WIDTH_PX)

    # Neo4jからグループ順のISBNリストを取得
    groups   = groups_from_neo4j()
    isbns    = _flatten_groups(groups)

    # trigger_book が含まれていなければ末尾へ
    if trigger_book and trigger_book.isbn not in set(isbns):
        isbns.append(trigger_book.isbn)
    
    books = db.query(MyHand).filter(MyHand.isbn.in_(isbns)).all()

    # ISBNごとの描画フィールドを一括取得
    books_map = {}
    for b in books:
        books_map[b.isbn] = {
            "isbn": b.isbn,
            "pages": b.pages,
            "height_mm": b.height_mm,
            "size_label": b.size_label,
        }

    # trigger_book が MyHand にある場合もカバー
    if trigger_book:
        books_map.setdefault(trigger_book.isbn, {
            "isbn": trigger_book.isbn,
            "size_label": trigger_book.size_label,
            "pages": trigger_book.pages,
            "height_mm": trigger_book.height_mm,
        })

    # 棚幅(px)で折り返しながら座標決定
    rows = _pack_into_shelves(isbns, books_map, shelf_max_px)

    # 最大棚番号を記録
    if rows:
        design.total_shelves = rows[-1]["shelf_index"] + 1

    db.query(ShelfLayout).delete()
    db.bulk_insert_mappings(ShelfLayout, rows)
    logger.info(f"[_rebuild_all] {len(rows)}冊 → {design.total_shelves}段")

FRAME     = 20
SPINE_GAP = 2

def _pack_into_shelves(isbns, books_map, shelf_max_px):
    rows = []

    shelf_index = 0
    x_cursor = 0

    for i, isbn in enumerate(isbns):
        b = books_map.get(isbn)
        if not b:
            continue

        width = calc_virtual_width(b["pages"])
        height = b["height_mm"]  # ← mmそのまま # ← 絶対ここだけ見る

        # 棚折り返し
        if x_cursor + width > shelf_max_px:
            shelf_index += 1
            x_cursor = 0

        rows.append({
            "isbn": isbn,
            "shelf_index": shelf_index,
            "x_pos": x_cursor,
            "order_index": i,
            "height_mm": height,
            "pages": b["pages"],
        })

        x_cursor += width

    return rows

# ── 内部: 1冊ランダム配置 ─────────────────────────────────────
def _place_one(db: Session, book):
    design       = _get_design(db)
    shelf_max_px = getattr(design, "shelf_max_width", SHELF_MAX_WIDTH_PX)

    w = calc_virtual_width(book.pages)

    # 棚ごとの使用状況
    shelf_info: dict[int, dict] = {}
    
    for row in db.query(ShelfLayout).order_by(
        ShelfLayout.shelf_index, ShelfLayout.x_pos
    ).all():
        si = row.shelf_index

        if si not in shelf_info:
            shelf_info[si] = {"count": 0, "next_x": FRAME}

        shelf_info[si]["count"] += 1

        # ✅ width_unit を使わない
        row_width = calc_virtual_width(row.pages)

        right = row.x_pos + row_width + SPINE_GAP
        if right > shelf_info[si]["next_x"]:
            shelf_info[si]["next_x"] = right

    # 空き棚チェック
    free_shelves = [
        si for si, info in shelf_info.items()
        if info["next_x"] + w + FRAME <= shelf_max_px
    ]

    if free_shelves:
        shelf_idx = random.choice(free_shelves)
        x_pos     = shelf_info[shelf_idx]["next_x"]
        order_idx = shelf_info[shelf_idx]["count"]
    else:
        shelf_idx = design.total_shelves or 0
        x_pos     = FRAME
        order_idx = 0
        design.total_shelves = shelf_idx + 1

    # ✅ width_unit 完全削除
    new_layout = ShelfLayout(
        isbn=book.isbn,
        shelf_index=shelf_idx,
        order_index=order_idx,
        x_pos=x_pos,
        height_mm=book.height_mm,
        pages=book.pages,
    )

    db.add(new_layout)
    logger.info(f"[_place_one] {book.isbn} → 棚{shelf_idx} x={x_pos}")
    
# ── ユーティリティ ────────────────────────────────────────────

def _get_design(db: Session) -> ShelfDesign:
    design = db.query(ShelfDesign).first()
    if not design:
        raise Exception("ShelfDesign が存在しません")
    return design

def _flatten_groups(groups: list) -> list[str]:
    """Neo4jグループリスト → 重複なしISBNリスト (グループ順)"""
    seen, result = set(), []
    for group in groups:
        for b in group.get("books", []):
            if b["isbn"] not in seen:
                result.append(b["isbn"])
                seen.add(b["isbn"])
    return result

def _sync_to_neo4j(db: Session):
    layouts = db.query(ShelfLayout).all()
    payload = [
        {"isbn": l.isbn, "shelf_index": l.shelf_index, "order_index": l.order_index}
        for l in layouts
    ]
    update_shelf_layout_chain(payload)