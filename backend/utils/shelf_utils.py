from sqlalchemy.orm import Session
from models import ShelfLayout, ShelfDesign, RegisteredBook
from admin_neo4j.neo4j_crud import groups_from_neo4j
import logging

logger = logging.getLogger(__name__)


class ShelfService:

    SHELF_MAX_WIDTH_PX = 800
    SCALE      = 0.9
    FRAME      = 20
    SPINE_GAP  = 2

    # ── サイズ計算 ────────────────────────────────────────────────

    @staticmethod
    def calc_virtual_width(pages: int | None) -> int:
        if not pages:
            return 20
        return int(pages * 0.065)

    @staticmethod
    def calc_spine_height_px(height_mm: int | None) -> int:
        if not height_mm:
            return 180
        raw = height_mm * ShelfService.SCALE
        return int(min(220, max(140, raw)))

    # ── 外部API ──────────────────────────────────────────────────

    def add_to_shelf(self, db: Session, book) -> bool:
        if db.query(ShelfLayout).filter(ShelfLayout.isbn == book.isbn).first():
            return False

        try:
            self._place_one(db, book)
            db.commit()
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"[add_to_shelf] 配置エラー [{book.isbn}]: {e}")
            return False

    # ── 内部: 全体再構築 ──────────────────────────────────────────

    def _rebuild_all(self, db: Session, trigger_book=None):
        """
        Neo4jのグループ順にISBNを並べ、棚幅(px)で折り返して配置する。
        trigger_book がNeo4jに未登録なら末尾追加。
        """
        design = self._get_design(db)
        shelf_max_px = getattr(design, "shelf_max_width", self.SHELF_MAX_WIDTH_PX)

        groups = groups_from_neo4j()
        isbns  = self._flatten_groups(groups)

        if trigger_book and trigger_book.isbn not in set(isbns):
            isbns.append(trigger_book.isbn)

        reg_books = (
            db.query(RegisteredBook)
            .filter(RegisteredBook.isbn.in_(isbns))
            .all()
        )

        books_map = {}
        for b in reg_books:
            books_map[b.isbn] = {
                "isbn":       b.isbn,
                "pages":      b.pages,
                "height_mm":  b.height_mm,
                "size_label": b.size_label,
            }

        if trigger_book:
            books_map.setdefault(trigger_book.isbn, {
                "isbn":       trigger_book.isbn,
                "size_label": trigger_book.size_label,
                "pages":      trigger_book.pages,
                "height_mm":  trigger_book.height_mm,
            })

        rows = self._pack_into_shelves(isbns, books_map, shelf_max_px)

        if rows:
            design.total_shelves = rows[-1]["shelf_index"] + 1

        db.query(ShelfLayout).delete()
        db.bulk_insert_mappings(ShelfLayout, rows)
        logger.info(f"[_rebuild_all] {len(rows)}冊 → {design.total_shelves}段")

    def _pack_into_shelves(self, isbns, books_map, shelf_max_px):
        rows = []

        shelf_index = 0
        x_cursor    = 0

        for i, isbn in enumerate(isbns):
            b = books_map.get(isbn)
            if not b:
                continue

            width  = self.calc_virtual_width(b["pages"])
            height = b["height_mm"]  # ← mmそのまま # ← 絶対ここだけ見る

            if x_cursor + width > shelf_max_px:
                shelf_index += 1
                x_cursor = 0

            rows.append({
                "isbn":        isbn,
                "shelf_index": shelf_index,
                "x_pos":       x_cursor,
                "order_index": i,
                "height_mm":   height,
                "pages":       b["pages"],
            })

            x_cursor += width

        return rows

    # ── 内部: 1冊ランダム配置 ─────────────────────────────────────

    def _place_one(self, db: Session, book):
        design       = self._get_design(db)
        shelf_max_px = getattr(design, "shelf_max_width", self.SHELF_MAX_WIDTH_PX)

        w = self.calc_virtual_width(book.pages)

        shelf_info: dict[int, dict] = {}

        for row in db.query(ShelfLayout).order_by(
            ShelfLayout.shelf_index, ShelfLayout.x_pos
        ).all():
            si = row.shelf_index

            if si not in shelf_info:
                shelf_info[si] = {"count": 0, "next_x": self.FRAME}

            shelf_info[si]["count"] += 1

            # ✅ width_unit を使わない
            row_width = self.calc_virtual_width(row.pages)

            right = row.x_pos + row_width + self.SPINE_GAP
            if right > shelf_info[si]["next_x"]:
                shelf_info[si]["next_x"] = right

        free_shelves = [
            si for si, info in shelf_info.items()
            if info["next_x"] + w + self.FRAME <= shelf_max_px
        ]

        if free_shelves:
            shelf_idx = min(free_shelves)
            x_pos     = shelf_info[shelf_idx]["next_x"]
            order_idx = shelf_info[shelf_idx]["count"]
        else:
            shelf_idx = max(shelf_info.keys()) + 1 if shelf_info else 0
            x_pos     = self.FRAME
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

    @staticmethod
    def _get_design(db: Session) -> ShelfDesign:
        design = db.query(ShelfDesign).first()
        if not design:
            design = ShelfDesign(total_shelves=1)
            db.add(design)
            db.flush()
        return design

    @staticmethod
    def _flatten_groups(groups: list) -> list[str]:
        """Neo4jグループリスト → 重複なしISBNリスト (グループ順)"""
        seen, result = set(), []
        for group in groups:
            for b in group.get("books", []):
                if b["isbn"] not in seen:
                    result.append(b["isbn"])
                    seen.add(b["isbn"])
        return result


# ============================================================
# モジュールレベル互換（既存の呼び出し元を変更なしで動作させる）
# ============================================================

_shelf_service = ShelfService()

calc_virtual_width   = ShelfService.calc_virtual_width
calc_spine_height_px = ShelfService.calc_spine_height_px
add_to_shelf         = _shelf_service.add_to_shelf

