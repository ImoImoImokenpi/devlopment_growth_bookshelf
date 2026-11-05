"""本棚の寸法（画面の frontend/src/components/SpineShelfView.js と同じ計算）。

- 本棚の幅は固定（SHELF_WIDTH_PX）。本があふれたら段を足す。
- ShelfLayout.x_pos は「(画面のx − 枠) / 1.2」で保存されている。
- 背幅はページ数から決まる（文庫は紙が薄いので細め）。

画面側の定数を変えたら、ここも合わせて変えること。
"""

SHELF_WIDTH_PX = 400          # 本棚全体の幅（固定）
FRAME_PX = 20                 # 左右の枠
SHELF_INNER_PX = SHELF_WIDTH_PX - FRAME_PX * 2  # 本を置ける幅
PX_TO_X = 1.2                 # 画面のpx ÷ x_pos
BUNKO_MAX_HEIGHT_MM = 160
BUNKO_WIDTH_FACTOR = 0.75


def spine_px(pages: int | None, height_mm: int | None) -> float:
    """背幅（画面のpx）。"""
    if not pages:
        return 20
    factor = BUNKO_WIDTH_FACTOR if height_mm and height_mm <= BUNKO_MAX_HEIGHT_MM else 1
    return min(100, max(1, pages * 0.08 * factor))


def spine_x(pages: int | None, height_mm: int | None) -> float:
    """背幅（x_pos の単位）。"""
    return spine_px(pages, height_mm) / PX_TO_X


INNER_X = SHELF_INNER_PX / PX_TO_X  # 本を置ける幅（x_pos の単位）


# ── 本棚の型 ──────────────────────────────────────────────
# "grid"  : 格子状のグリッド。1マスに1冊、どのマスへも自由に動かせる（画面は GridShelfView.js）
# "spine" : 背表紙を並べる本棚（画面は SpineShelfView.js）。戻すときはここと
#           frontend/src/pages/Home.js の SHELF_VIEW を "spine" にする。
SHELF_MODE = "grid"

# グリッドの寸法。ShelfLayout には 段=shelf_index（行）、列=order_index で保存し、
# x_pos は列を本棚の幅に割り付けた値（背表紙の本棚に戻しても左右の順が保たれる）。
# 1行のマス数は持ち主ごとに変えられる（ShelfDesign.grid_cols）。空のときは GRID_COLS。
GRID_COLS = 8                       # 1行のマス数の既定値
GRID_MIN_COLS = 4
GRID_MAX_COLS = 12


def grid_x(col: int, cols: int = GRID_COLS) -> float:
    """列番号 → x_pos（1行のマスを本棚の幅に割り付ける）。"""
    return round(col * INNER_X / cols, 2)
