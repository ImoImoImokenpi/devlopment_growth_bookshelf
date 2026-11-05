from sqlalchemy.orm import Session
from models import ShelfLayout, ShelfDesign, RegisteredBook
from graph.main_kg.neo4j_crud import groups_from_neo4j
from shelf_period import DEFAULT_PERIOD
from utils.shelf_geometry import GRID_COLS, GRID_MAX_COLS, GRID_MIN_COLS, INNER_X, SHELF_MODE, grid_x, spine_x
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

    def add_to_shelf(self, db: Session, book, participant_id: str, period: str = DEFAULT_PERIOD) -> str:
        """本をその被験者の（時期ごとの）棚に配置する。

        棚には同じ本を複数冊置けるので、既に同じisbnが棚にあっても
        新しい1冊として置く（"already_on_shelf" では弾かない）。

        戻り値:
          "placed" … 棚に置いた
          "error"  … 配置に失敗した
        """
        try:
            self._place_one(db, book, participant_id, period)
            db.commit()
            return "placed"

        except Exception as e:
            db.rollback()
            logger.error(f"[add_to_shelf] 配置エラー [{book.isbn}]: {e}")
            return "error"

    # ── 内部: 全体再構築 ──────────────────────────────────────────

    def _rebuild_all(self, db: Session, participant_id: str, trigger_book=None):
        """
        Neo4jのグループ順にISBNを並べ、棚幅(px)で折り返して配置する。
        trigger_book がNeo4jに未登録なら末尾追加。
        """
        design = self._get_design(db, participant_id)
        shelf_max_px = getattr(design, "shelf_max_width", self.SHELF_MAX_WIDTH_PX)

        groups = groups_from_neo4j(participant_id)
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

        rows = self._pack_into_shelves(isbns, books_map, shelf_max_px, participant_id)

        if rows:
            design.total_shelves = rows[-1]["shelf_index"] + 1

        db.query(ShelfLayout).filter(ShelfLayout.participant_id == participant_id).delete()
        db.bulk_insert_mappings(ShelfLayout, rows)
        logger.info(f"[_rebuild_all] {len(rows)}冊 → {design.total_shelves}段")

    def _pack_into_shelves(self, isbns, books_map, shelf_max_px, participant_id):
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
                "participant_id": participant_id,
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

    # ── グリッド ────────────────────────────────────────────────

    def grid_cols(self, db: Session, participant_id: str, period: str = DEFAULT_PERIOD) -> int:
        """この持ち主の1行のマス数。"""
        cols = self._get_design(db, participant_id, period).grid_cols or GRID_COLS
        return max(GRID_MIN_COLS, min(GRID_MAX_COLS, cols))

    def set_grid_cols(self, db: Session, participant_id: str, period: str, cols: int) -> int:
        """1行のマス数を変える。減らしたときは、はみ出したマスの本をすぐ下に足した行へ
        折り返す（列 c → 下へ c // cols 行、列 c % cols）。ほかの本と空きマスはそのまま。"""
        self.normalize_grid(db, participant_id, period)
        cols = max(GRID_MIN_COLS, min(GRID_MAX_COLS, int(cols)))
        rows = (
            db.query(ShelfLayout)
            .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.period == period)
            .order_by(ShelfLayout.shelf_index, ShelfLayout.order_index)
            .all()
        )
        by_shelf: dict[int, list] = {}
        for r in rows:
            by_shelf.setdefault(r.shelf_index, []).append(r)
        shift = 0
        for si in sorted(by_shelf):
            extra = 0
            for r in by_shelf[si]:
                wrap = r.order_index // cols
                r.shelf_index = si + shift + wrap
                r.order_index = r.order_index % cols
                extra = max(extra, wrap)
            shift += extra
        for r in rows:
            r.x_pos = grid_x(r.order_index, cols)
        design = self._get_design(db, participant_id, period)
        design.grid_cols = cols
        if rows:
            design.total_shelves = max(r.shelf_index for r in rows) + 1
        return cols
    def normalize_grid(self, db: Session, participant_id: str, period: str = DEFAULT_PERIOD) -> bool:
        """並びをグリッドのマス（1マス1冊・横 cols マス）に合わせる。変えたら True。

        背表紙の本棚で保存された並びは、段ごとに左から順にマスへ詰め、
        cols を超える分は次の行へ折り返す（その下の行は1つずつ下げる）。
        すでにグリッドとして正しい行は動かさない。
        """
        cols = self.grid_cols(db, participant_id, period)
        rows = (
            db.query(ShelfLayout)
            .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.period == period)
            .order_by(ShelfLayout.shelf_index, ShelfLayout.x_pos, ShelfLayout.order_index)
            .all()
        )
        by_shelf: dict[int, list] = {}
        for r in rows:
            by_shelf.setdefault(r.shelf_index, []).append(r)

        def valid(group) -> bool:
            used = [r.order_index for r in group]
            return (
                len(set(used)) == len(used)
                and all(c is not None and 0 <= c < cols for c in used)
                and all(abs((r.x_pos or 0) - grid_x(r.order_index, cols)) < 0.05 for r in group)
            )

        if all(valid(g) for g in by_shelf.values()):
            return False

        shift = 0  # 折り返しで増えた行の数（空いている行はそのまま残す）
        for si in sorted(by_shelf):
            group = by_shelf[si]
            if valid(group):
                for r in group:
                    r.shelf_index = si + shift
                continue
            for i, r in enumerate(group):  # x_pos の順（左から）
                r.shelf_index = si + shift + i // cols
                r.order_index = i % cols
                r.x_pos = grid_x(r.order_index, cols)
            shift += (len(group) - 1) // cols

        design = self._get_design(db, participant_id, period)
        design.total_shelves = max(r.shelf_index for r in rows) + 1
        logger.info(f"[normalize_grid] {participant_id} ({period}) の並びをグリッドに合わせました")
        return True

    def _place_one_grid(self, db: Session, book, participant_id: str, period: str = DEFAULT_PERIOD):
        """最後の本の次のマスに置く（空きマスは持ち主が空けた間なので埋めない）。"""
        self.normalize_grid(db, participant_id, period)
        cols = self.grid_cols(db, participant_id, period)
        last = (
            db.query(ShelfLayout)
            .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.period == period)
            .order_by(ShelfLayout.shelf_index.desc(), ShelfLayout.order_index.desc())
            .first()
        )
        if last is None:
            row, col = 0, 0
        elif last.order_index + 1 < cols:
            row, col = last.shelf_index, last.order_index + 1
        else:
            row, col = last.shelf_index + 1, 0
        design = self._get_design(db, participant_id, period)
        design.total_shelves = max(design.total_shelves or 1, row + 1)
        db.add(ShelfLayout(
            participant_id=participant_id, period=period, isbn=book.isbn,
            shelf_index=row, order_index=col, x_pos=grid_x(col, cols),
            height_mm=book.height_mm, pages=book.pages,
        ))
        logger.info(f"[_place_one_grid] {book.isbn} → 行{row} 列{col} (period={period})")

    def _place_one(self, db: Session, book, participant_id: str, period: str = DEFAULT_PERIOD):
        """本棚の幅は固定（utils/shelf_geometry.py）。上の段から順に、左端から続く並びの
        終わりに収まる段を探して置く。どの段にも収まらなければ、いちばん下に段を足す。
        寸法は画面（SpineShelfView.js）と同じ計算を使う。"""
        if SHELF_MODE == "grid":
            return self._place_one_grid(db, book, participant_id, period)
        design = self._get_design(db, participant_id, period)
        w = spine_x(book.pages, book.height_mm)

        by_shelf: dict[int, list] = {}
        for row in db.query(ShelfLayout).filter(
            ShelfLayout.participant_id == participant_id,
            ShelfLayout.period == period,
        ).order_by(
            ShelfLayout.shelf_index, ShelfLayout.x_pos
        ).all():
            by_shelf.setdefault(row.shelf_index, []).append(row)

        def left_run_end(rows) -> float:
            """左端から隙間なく続く並びの終わり"""
            x = 0.0
            for r in rows:
                if r.x_pos > x + 0.5:
                    break
                x = r.x_pos + spine_x(r.pages, r.height_mm)
            return x

        def free_gap_fits(rows, x) -> bool:
            """x から幅 w を置いても、右隣の本・棚の右端にぶつからないか"""
            right_limit = min([r.x_pos for r in rows if r.x_pos >= x - 0.01] + [INNER_X])
            return x + w <= right_limit + 0.01

        shelf_idx = None
        for si in sorted(by_shelf):
            x = left_run_end(by_shelf[si])
            if free_gap_fits(by_shelf[si], x):
                shelf_idx, x_pos, order_idx = si, x, sum(1 for r in by_shelf[si] if r.x_pos < x)
                break

        if shelf_idx is None:
            shelf_idx = max(by_shelf) + 1 if by_shelf else 0
            x_pos     = 0.0
            order_idx = 0
        design.total_shelves = max(design.total_shelves or 1, shelf_idx + 1)

        # 右側に並んでいる本の順番を1つずつ後ろへ
        for r in by_shelf.get(shelf_idx, []):
            if r.x_pos >= x_pos - 0.01:
                r.order_index = (r.order_index or 0) + 1

        new_layout = ShelfLayout(
            participant_id=participant_id,
            period=period,
            isbn=book.isbn,
            shelf_index=shelf_idx,
            order_index=order_idx,
            x_pos=x_pos,
            height_mm=book.height_mm,
            pages=book.pages,
        )

        db.add(new_layout)
        logger.info(f"[_place_one] {book.isbn} → 棚{shelf_idx} x={x_pos} (period={period})")

    # ── ユーティリティ ────────────────────────────────────────────

    @staticmethod
    def _get_design(db: Session, participant_id: str, period: str = DEFAULT_PERIOD) -> ShelfDesign:
        design = (
            db.query(ShelfDesign)
            .filter(ShelfDesign.participant_id == participant_id, ShelfDesign.period == period)
            .first()
        )
        if not design:
            design = ShelfDesign(participant_id=participant_id, period=period, total_shelves=1)
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

