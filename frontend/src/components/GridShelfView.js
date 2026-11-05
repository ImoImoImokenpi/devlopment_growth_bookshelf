// 育つ本棚の「グリッドの本棚」。格子状のマスに1冊ずつ表紙を置き、どのマスへも自由に動かせる。
//
//   - 本をドラッグして空いたマスに落とすと移動、ほかの本のマスに落とすとその本を押しのけて入る
//   - 下のゴミ箱に落とすと本棚から外す
//   - クリックすると右パネルに本の詳細
//   - Shift/Ctrl/⌘ を押しながらクリック（または「まとめて選ぶ」）で何冊か選び、まとめて動かせる。
//     選んだ本のどれかをドラッグすると、落としたマスから読む順に並べて入れる（そこにあった本は後ろへ押す）。
//     選んだ本は、まとめて別の本棚へ移したり、外したりもできる
//   - いちばん下には常に空いた行を1つ出しておき、そこへ置けば行が増える
//
// 保存の形は背表紙の本棚（SpineShelfView.js、今は使っていないが残してある）と同じ ShelfLayout:
//   行 = shelf_index、列 = order_index、x_pos = 列を本棚の幅に割り付けた値。
// 知識グラフの「隣」（SHELF_NEXT）は、同じ行で隣り合うマスの本どうし
// （backend/graph/main_kg/neo4j_crud.py、SHELF_MODE="grid" のとき）。
// 1行のマス数は持ち主ごとに変えられる（本棚の上の「1行の冊数」。保存先は ShelfDesign.grid_cols）。
// 寸法は backend/utils/shelf_geometry.py の GRID_COLS・GRID_MIN_COLS・GRID_MAX_COLS・grid_x と合わせること。
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { MyBookshelfContext } from "../context/MyBookshelfContext";
import { useShelfWorkspace } from "../context/ShelfWorkspaceContext";
import { useShelves } from "../context/ShelvesContext";

const API = "http://localhost:8000";
export const GRID_COLS = 8;               // 1行のマス数の既定値
const GRID_MIN_COLS = 4;
const GRID_MAX_COLS = 12;
const INNER_X = (400 - 40) / 1.2;         // 本棚の幅（x_pos の単位）
const SYNC_DELAY_MS = 10_000;            // 並べ替えは少し待ってからまとめて保存する（背表紙の本棚と同じ）
const ARRIVAL_GLOW_MS = 6_000;            // 新しく加わった本を光らせておく時間

const PALETTES = [
  { bg: "#1a1a2e", text: "#e8d5a3" }, { bg: "#2d1b33", text: "#f0e6d3" },
  { bg: "#0d2137", text: "#cce5f0" }, { bg: "#1e3a2f", text: "#d4edd8" },
  { bg: "#3b1f0e", text: "#f5dfc5" }, { bg: "#1f2d3d", text: "#d8e4ec" },
  { bg: "#3d1f1f", text: "#f5d5d5" }, { bg: "#f5f0e8", text: "#2a2018" },
];
const RECOMMENDED = { badge: "#b8923a" };

function hashCode(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}
const gridX = (col, cols) => Math.round(col * INNER_X / cols * 100) / 100;
const key = (row, col) => `${row}:${col}`;

// 保存されている位置をマスに割り当てる。範囲外・重なりがあれば次の空きマスへ（表示上の保険）
function assignCells(books, cols) {
  const taken = new Set();
  const placed = {};
  const sorted = [...books].sort((a, b) =>
    (a.shelf_index ?? 0) - (b.shelf_index ?? 0) || (a.order_index ?? 0) - (b.order_index ?? 0));
  sorted.forEach(b => {
    let row = Math.max(0, b.shelf_index ?? 0);
    let col = b.order_index ?? 0;
    if (col < 0 || col >= cols) col = 0;
    while (taken.has(key(row, col))) {
      col += 1;
      if (col >= cols) { col = 0; row += 1; }
    }
    taken.add(key(row, col));
    placed[b.id] = { row, col };
  });
  return placed;
}

// 本 id を (row, col) に置き、そこにいた本を押しのけた並びを返す（元の cells は変えない）。
//   - 置きたいマスが空いていればそのまま置く
//   - ふさがっていれば、同じ行で近いほうの空きマスへ向けて、間の本を1マスずつずらす
//   - 行に空きがなければ右へずらし、右端からあふれた本を次の行の先頭へ押し込む（空きに届くまで続く）
// 動かす本は先に元のマスから抜くので、元のマスも空きとして使われる。
function pushInto(cells, id, row, col, cols, allowLeft = true) {
  const next = { ...cells };
  delete next[id];
  const occ = new Map(Object.entries(next).map(([bid, c]) => [key(c.row, c.col), bid]));
  const moveTo = (bid, r, c) => { next[bid] = { row: r, col: c }; occ.set(key(r, c), bid); };

  const insert = (bid, r, c, allowLeft) => {
    if (!occ.has(key(r, c))) { moveTo(bid, r, c); return; }
    let right = null;
    for (let x = c + 1; x < cols; x++) if (!occ.has(key(r, x))) { right = x; break; }
    let left = null;
    if (allowLeft) for (let x = c - 1; x >= 0; x--) if (!occ.has(key(r, x))) { left = x; break; }

    if (right != null && (left == null || right - c <= c - left)) {
      for (let x = right; x > c; x--) moveTo(occ.get(key(r, x - 1)), r, x);
      moveTo(bid, r, c);
    } else if (left != null) {
      for (let x = left; x < c; x++) moveTo(occ.get(key(r, x + 1)), r, x);
      moveTo(bid, r, c);
    } else {
      // 行がいっぱい: 右端の本を次の行の先頭へ送り出す
      const carry = occ.get(key(r, cols - 1));
      occ.delete(key(r, cols - 1));
      for (let x = cols - 1; x > c; x--) moveTo(occ.get(key(r, x - 1)), r, x);
      moveTo(bid, r, c);
      insert(carry, r + 1, 0, false);
    }
  };
  insert(String(id), row, col, allowLeft);
  return next;
}

// 何冊かをまとめて入れる。入れた本どうしは離れずに、読む順のひと続きになる。
//   - 落としたマスから右に、入れる冊数ぶんの空きがその行にあれば（または左にも足りなければ）、
//     落としたマスから右へ並べ、そこにあった本は後ろ（右・次の行）へ押す
//   - 右に足りず左に足りるなら、落としたマスで終わるように左へ並べ、そこにあった本は左へ押す
//     （同じ行の中で右へ動かしたとき、空いた元のマスを詰めて使う。1冊のときと同じ考え方）
function pushGroup(cells, ids, row, col, cols) {
  if (ids.length === 1) return pushInto(cells, ids[0], row, col, cols);
  let next = { ...cells };
  ids.forEach(id => { delete next[id]; });
  const taken = new Set(Object.values(next).map(c => key(c.row, c.col)));
  let emptyRight = 0;
  let emptyLeft = 0;
  for (let x = 0; x < cols; x++) {
    if (taken.has(key(row, x))) continue;
    if (x >= col) emptyRight += 1; else emptyLeft += 1;
  }

  if (emptyRight >= ids.length || emptyLeft < ids.length) {
    let r = row;
    let c = col;
    ids.forEach(id => {
      next = pushInto(next, id, r, c, cols, false);
      c += 1;
      if (c >= cols) { c = 0; r += 1; }
    });
    return next;
  }

  // 左へ並べる: この行だけ左右を反転して「右へ並べる」と同じ手順で入れ、元に戻す
  const flip = (cellsMap) => {
    const out = {};
    Object.entries(cellsMap).forEach(([id, c]) => {
      out[id] = c.row === row ? { row, col: cols - 1 - c.col } : c;
    });
    return out;
  };
  next = flip(next);
  let c = cols - 1 - col;
  [...ids].reverse().forEach(id => {
    next = pushInto(next, id, row, c, cols, false);
    c += 1;
  });
  return flip(next);
}

// 読む順（上の行から、左から）に並べる
const readingOrder = (cells) => (a, b) =>
  (cells[a].row - cells[b].row) || (cells[a].col - cells[b].col);

export default function GridShelfView() {
  const { myBookshelf, fetchBookshelf, removeBook, period } = useContext(MyBookshelfContext);
  const {
    focusIsbn, setFocusIsbn,
    highlightIsbns, conceptHighlights,
    flushLayoutSyncRef, dialogueSessionIdRef,
  } = useShelfWorkspace();

  const books = useMemo(
    () => (myBookshelf?.shelves || []).flatMap(s => s.books || []),
    [myBookshelf]
  );
  const cols = myBookshelf?.grid_cols || GRID_COLS;
  const [changingCols, setChangingCols] = useState(false);

  // 画面上の位置 { [ShelfLayoutの行id]: {row, col} }。同じ本が2冊あっても行idで区別する
  const [cells, setCells] = useState({});
  const [deletedIds, setDeletedIds] = useState(new Set());
  const [dragId, setDragId] = useState(null);
  const [overCell, setOverCell] = useState(null);
  const [overTrash, setOverTrash] = useState(false);
  // まとめて動かすために選んだ本（ShelfLayoutの行id）。「まとめて選ぶ」がオンならクリックで選ぶ
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const { shelves, activeScopeId, moveBookToShelf } = useShelves();
  const otherShelves = shelves.filter(sh => sh.scope_id !== activeScopeId);

  // 画面を開いてから本棚に現れた本（行id）。しばらく光らせて、どこに加わったかを見せる
  const seenIdsRef = useRef(null);
  const [arrivedIds, setArrivedIds] = useState(new Set());
  const arrivalTimersRef = useRef([]);
  const syncTimerRef = useRef(null);
  const pendingLayoutRef = useRef(null);
  const movedIsbnsRef = useRef(new Set());

  useEffect(() => { fetchBookshelf(); }, [fetchBookshelf]);
  useEffect(() => { setDeletedIds(new Set()); seenIdsRef.current = null; }, [period]);
  useEffect(() => {
    const ids = books.map(b => b.id);
    if (seenIdsRef.current === null) {
      // 最初の読み込みで並んでいた本は光らせない
      if (books.length) seenIdsRef.current = new Set(ids);
      return;
    }
    const fresh = ids.filter(id => !seenIdsRef.current.has(id));
    ids.forEach(id => seenIdsRef.current.add(id));
    if (!fresh.length) return;
    setArrivedIds(prev => new Set([...prev, ...fresh]));
    // 取り直しが続いても消し忘れないよう、タイマーは画面を閉じるときにだけ止める
    arrivalTimersRef.current.push(setTimeout(() => {
      setArrivedIds(prev => new Set([...prev].filter(id => !fresh.includes(id))));
    }, ARRIVAL_GLOW_MS));
  }, [books]);
  useEffect(() => () => arrivalTimersRef.current.forEach(clearTimeout), []);
  useEffect(() => { setCells(assignCells(books, cols)); }, [books, cols]);
  // 本棚を取り直したら、もう本棚にない本は選択から外す
  useEffect(() => {
    const ids = new Set(books.map(b => b.id));
    setSelectedIds(prev => {
      const kept = [...prev].filter(id => ids.has(id));
      return kept.length === prev.size ? prev : new Set(kept);
    });
  }, [books]);
  // Esc で選択をやめる
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") { setSelectedIds(new Set()); setSelectMode(false); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => () => { if (syncTimerRef.current) clearTimeout(syncTimerRef.current); }, []);

  const dragGroup = useMemo(() => {
    if (dragId == null || !cells[dragId]) return [];
    if (!selectedIds.has(dragId) || selectedIds.size < 2) return [dragId];
    return [...selectedIds].filter(id => cells[id]).sort(readingOrder(cells));
  }, [dragId, selectedIds, cells]);

  // ドラッグ中は、落としたらどう押しのけるかを先に見せる
  const shownCells = useMemo(() => {
    if (!dragGroup.length || overCell == null) return cells;
    const [r, c] = overCell.split(":").map(Number);
    return pushGroup(cells, dragGroup, r, c, cols);
  }, [cells, dragGroup, overCell, cols]);

  const visibleBooks = useMemo(
    () => books.filter(b => !deletedIds.has(b.id) && cells[b.id]),
    [books, deletedIds, cells]
  );
  const byCell = useMemo(() => {
    const m = {};
    visibleBooks.forEach(b => {
      const c = shownCells[b.id];
      if (c) m[key(c.row, c.col)] = b;
    });
    return m;
  }, [visibleBooks, shownCells]);
  // 本のある最後の行の下に、空いた行を1つ足しておく
  const rowCount = useMemo(
    () => Math.max(2, visibleBooks.reduce((m, b) => Math.max(m, ((shownCells[b.id] || cells[b.id]).row) + 1), 0) + 1),
    [visibleBooks, shownCells, cells]
  );

  // ── 保存 ──
  const handleSyncLayout = useCallback(async (layoutData) => {
    const movedIsbns = [...movedIsbnsRef.current];
    movedIsbnsRef.current = new Set();
    pendingLayoutRef.current = null;
    try {
      await fetch(`${API}/bookshelf/sync-layout?period=${period}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layout: layoutData,
          moved_isbns: movedIsbns,
          dialogue_session_id: dialogueSessionIdRef.current,
        }),
      });
    } catch (err) { console.error("Sync failed", err); }
  }, [period, dialogueSessionIdRef]);

  // 対話の開始時などに、待ち中の並べ替えを今すぐ保存する
  useEffect(() => {
    flushLayoutSyncRef.current = async () => {
      if (!syncTimerRef.current) return;
      clearTimeout(syncTimerRef.current);
      syncTimerRef.current = null;
      if (pendingLayoutRef.current) await handleSyncLayout(pendingLayoutRef.current);
    };
    return () => { flushLayoutSyncRef.current = null; };
  }, [flushLayoutSyncRef, handleSyncLayout]);

  const scheduleSync = (nextCells) => {
    const layout = books
      .filter(b => !deletedIds.has(b.id) && nextCells[b.id])
      .map(b => ({
        id: b.id, isbn: b.isbn,
        shelf_index: nextCells[b.id].row,
        order_index: nextCells[b.id].col,
        x_pos: gridX(nextCells[b.id].col, cols),
      }));
    pendingLayoutRef.current = layout;
    if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    syncTimerRef.current = setTimeout(() => {
      syncTimerRef.current = null;
      handleSyncLayout(layout);
    }, SYNC_DELAY_MS);
  };

  // ── 1行の冊数 ──
  // 減らすときは、なくなる右端の列に本がないか確かめる。本があれば、下の行へ
  // 折り返してよいかを持ち主に聞き、よいと言われたときだけ減らす。
  const changeCols = async (nextCols) => {
    if (changingCols || nextCols < GRID_MIN_COLS || nextCols > GRID_MAX_COLS) return;
    let allowWrap = false;
    if (nextCols < cols) {
      const inRemoved = visibleBooks.filter(b => cells[b.id] && cells[b.id].col >= nextCols);
      if (inRemoved.length) {
        const names = inRemoved.slice(0, 5).map(b => `『${b.title}』`).join("、");
        const more = inRemoved.length > 5 ? ` ほか${inRemoved.length - 5}冊` : "";
        const ok = window.confirm(
          `右端の列に本が${inRemoved.length}冊あります（${names}${more}）。\n` +
          `1行を${nextCols}冊にすると、これらの本はすぐ下の行へ折り返します。よろしいですか？`
        );
        if (!ok) return;
        allowWrap = true;
      }
    }
    setChangingCols(true);
    try {
      if (flushLayoutSyncRef.current) await flushLayoutSyncRef.current();
      const res = await fetch(`${API}/bookshelf/grid-cols?period=${period}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cols: nextCols, allow_wrap: allowWrap }),
      });
      if (res.status === 409) {
        // 画面の表示より新しい並び（おすすめが加わった等）で、なくなる列に本があった
        window.alert("右端の列に本があるため、1行の冊数を減らせませんでした。本棚を読み込み直します。");
      }
      await fetchBookshelf();
    } catch (err) {
      console.error("1行の冊数を変えられませんでした", err);
    } finally {
      setChangingCols(false);
    }
  };

  // ── ドラッグ ──
  const endDrag = () => { setDragId(null); setOverCell(null); setOverTrash(false); };

  const dropOnCell = (row, col) => {
    const group = dragGroup;
    endDrag();
    if (!group.length) return;
    const from = cells[group[0]];
    if (group.length === 1 && from.row === row && from.col === col) return;
    const next = pushGroup(cells, group, row, col, cols); // ふさがっていれば押しのける
    setCells(next);
    // 記録するのは持ち主が動かした本だけ（まとめて動かした本はすべて）
    group.forEach(id => {
      const moved = books.find(b => b.id === id);
      if (moved) movedIsbnsRef.current.add(moved.isbn);
    });
    scheduleSync(next);
  };

  // 本棚から外す（何冊でも）。外すと本棚を取り直すので、まだ保存していない並べ替えを先に保存する
  const removeIds = async (ids) => {
    setDeletedIds(prev => new Set([...prev, ...ids]));
    if (flushLayoutSyncRef.current) await flushLayoutSyncRef.current();
    for (const id of ids) await removeBook(id);
    setSelectedIds(new Set());
  };

  const dropOnTrash = async () => {
    const group = dragGroup;
    endDrag();
    if (!group.length) return;
    if (group.length > 1 && !window.confirm(`選んだ${group.length}冊を本棚から外します。よろしいですか？`)) return;
    await removeIds(group);
  };

  // ── 選んだ本をまとめて扱う ──
  const toggleSelect = (id) => setSelectedIds(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const clearSelection = () => { setSelectedIds(new Set()); setSelectMode(false); };
  const selectedBooks = visibleBooks.filter(b => selectedIds.has(b.id));

  const moveSelectedToShelf = async (shelfId) => {
    const target = otherShelves.find(sh => String(sh.id) === String(shelfId));
    if (!target || !selectedBooks.length || bulkBusy) return;
    if (!window.confirm(
      `選んだ${selectedBooks.length}冊を「${target.name}」へ移します。\n` +
      "この本棚で付けた意味づけや対話の記録は、この本棚に残ります。よろしいですか？"
    )) return;
    setBulkBusy(true);
    try {
      if (flushLayoutSyncRef.current) await flushLayoutSyncRef.current();
      for (const b of selectedBooks) await moveBookToShelf(b.isbn, target.id);
      setSelectedIds(new Set());
      setSelectMode(false);
    } catch (err) {
      window.alert(`移せなかった本があります（${err.message}）`);
    } finally {
      await fetchBookshelf();
      setBulkBusy(false);
    }
  };

  const removeSelected = async () => {
    if (!selectedBooks.length || bulkBusy) return;
    if (!window.confirm(`選んだ${selectedBooks.length}冊を本棚から外します。よろしいですか？`)) return;
    setBulkBusy(true);
    try { await removeIds(selectedBooks.map(b => b.id)); } finally { setBulkBusy(false); }
  };

  // ── 強調（背表紙の本棚と同じ決まり）──
  // 意味づけの強調があればそれだけを光らせてほかを沈める。なければ
  // 詳細を開いている本 → 対話で話題にした本 の順に印を付ける。
  const { marks, dimOthers } = useMemo(() => {
    const layers = Object.values(conceptHighlights || {});
    if (layers.length) {
      const m = {};
      layers.forEach(l => (l.isbns || []).forEach(i => { if (!m[i]) m[i] = { color: l.color, dashed: false, width: 3 }; }));
      return { marks: m, dimOthers: true };
    }
    if (focusIsbn) return { marks: { [focusIsbn]: { color: "#ff9d3d", dashed: false, width: 2 } }, dimOthers: false };
    const m = {};
    (highlightIsbns || []).forEach(i => { m[i] = { color: "#ff9d3d", dashed: true, width: 3 }; });
    return { marks: m, dimOthers: false };
  }, [conceptHighlights, focusIsbn, highlightIsbns]);

  // 1行ずつ、マスの並びの下に棚板を敷く
  const rowsView = [];
  for (let row = 0; row < rowCount; row++) {
    const cellsGrid = [];
    for (let col = 0; col < cols; col++) {
      const k = key(row, col);
      const book = byCell[k];
      const isOver = overCell === k && dragId != null;
      const dragged = dragId != null ? books.find(b => b.id === dragId) : null;
      const origin = dragged && cells[dragId] && key(cells[dragId].row, cells[dragId].col) === k ? dragged : null;
      const tiles = [];
      if (book && book.id !== dragId) tiles.push({ b: book, ghost: false });
      if (origin) tiles.push({ b: origin, ghost: true });
      cellsGrid.push(
        <div
          key={k}
          style={{ ...s.cell, ...(isOver ? s.cellOver : {}) }}
          onDragOver={e => { if (dragId != null) { e.preventDefault(); if (overCell !== k) setOverCell(k); } }}
          onDrop={e => { e.preventDefault(); dropOnCell(row, col); }}
        >
          {tiles.map(({ b: tb, ghost }) => (
            <BookTile
              key={tb.id}
              book={tb}
              mark={marks[tb.isbn]}
              dimmed={dimOthers && !marks[tb.isbn]}
              dragging={ghost}
              arrived={arrivedIds.has(tb.id)}
              hidden={ghost && tiles.length > 1}
              selected={selectedIds.has(tb.id)}
              onClick={(e) => {
                if (selectMode || e.shiftKey || e.ctrlKey || e.metaKey) toggleSelect(tb.id);
                else setFocusIsbn(tb.isbn);
              }}
              onDragStart={e => {
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", String(tb.id));
                setDragId(tb.id);
              }}
              onDragEnd={endDrag}
            />
          ))}
        </div>
      );
    }
    rowsView.push(
      <div key={`row-${row}`} style={s.row}>
        <div style={{ ...s.grid, gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>{cellsGrid}</div>
        <div style={s.board} />
      </div>
    );
  }

  return (
    <div style={{ ...s.wrap, maxWidth: Math.min(1100, cols * 112 + 40) }}>
      <style>{`
        @keyframes gridBookArrive {
          0%   { transform: scale(0.6); box-shadow: 0 0 0 0 rgba(255,190,70,0.95); }
          25%  { transform: scale(1.06); box-shadow: 0 0 0 6px rgba(255,190,70,0.75); }
          100% { transform: scale(1); box-shadow: 0 0 14px 4px rgba(255,190,70,0.55); }
        }
        @keyframes gridBookGlow {
          0%, 100% { box-shadow: 0 0 14px 4px rgba(255,190,70,0.55); }
          50%      { box-shadow: 0 0 4px 1px rgba(255,190,70,0.25); }
        }
        .grid-book-arrived {
          animation: gridBookArrive 0.7s ease-out, gridBookGlow 1.4s ease-in-out 0.7s infinite;
        }
      `}</style>
      <div style={s.toolbar}>
        <button
          style={{ ...s.selectBtn, ...(selectMode ? s.selectBtnOn : {}) }}
          onClick={() => (selectMode ? clearSelection() : setSelectMode(true))}
          title="クリックで本を選び、まとめて動かす（Shift / Ctrl / ⌘ を押しながらクリックでも選べます）"
        >
          {selectMode ? "選ぶのをやめる" : "まとめて選ぶ"}
        </button>
        {selectedBooks.length > 0 && (
          <div style={s.bulkBar}>
            <span style={s.bulkCount}>{selectedBooks.length}冊を選択中</span>
            <span style={s.bulkHint}>選んだ本をドラッグすると、まとめて動きます</span>
            {otherShelves.length > 0 && (
              <select
                style={s.bulkSelect}
                value=""
                onChange={e => moveSelectedToShelf(e.target.value)}
                disabled={bulkBusy}
                title="選んだ本をまとめて別の本棚へ移す"
              >
                <option value="">別の本棚へ移す…</option>
                {otherShelves.map(sh => <option key={sh.id} value={sh.id}>{sh.name}</option>)}
              </select>
            )}
            <button style={s.bulkBtn} onClick={removeSelected} disabled={bulkBusy}>外す</button>
            <button style={s.bulkBtn} onClick={clearSelection} disabled={bulkBusy}>選択を解除</button>
          </div>
        )}
        <span style={{ flex: 1 }} />
        <span style={s.toolLabel}>1行の冊数</span>
        <button
          style={{ ...s.stepBtn, ...(cols <= GRID_MIN_COLS || changingCols ? s.stepBtnOff : {}) }}
          onClick={() => changeCols(cols - 1)}
          disabled={cols <= GRID_MIN_COLS || changingCols}
          title="1行の冊数を減らす（はみ出した本は下の行へ折り返します）"
          aria-label="1行の冊数を減らす"
        >−</button>
        <span style={s.colsValue}>{cols}冊</span>
        <button
          style={{ ...s.stepBtn, ...(cols >= GRID_MAX_COLS || changingCols ? s.stepBtnOff : {}) }}
          onClick={() => changeCols(cols + 1)}
          disabled={cols >= GRID_MAX_COLS || changingCols}
          title="1行の冊数を増やす"
          aria-label="1行の冊数を増やす"
        >＋</button>
      </div>
      {visibleBooks.length === 0 && (
        <div style={s.empty}>本棚に本がありません。登録した本がここに並びます。</div>
      )}
      <div style={s.shelf}>{rowsView}</div>

      {/* ゴミ箱（ドラッグ中だけ出す） */}
      <div
        style={{
          ...s.trash,
          opacity: dragId != null ? 1 : 0,
          pointerEvents: dragId != null ? "auto" : "none",
          ...(overTrash ? s.trashOver : {}),
        }}
        onDragOver={e => { e.preventDefault(); setOverTrash(true); if (overCell) setOverCell(null); }}
        onDragLeave={() => setOverTrash(false)}
        onDrop={e => { e.preventDefault(); dropOnTrash(); }}
        title="ここに落とすと本棚から外します"
      >
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
          <path d="M10 11v6M14 11v6"/>
          <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
        </svg>
      </div>
    </div>
  );
}

// 1冊の表紙。表紙が取れなければ書名入りの札にする
function BookTile({ book, mark, dimmed, dragging, hidden, arrived, selected, onClick, onDragStart, onDragEnd }) {
  const proxy = `${API}/register/cover/${book.isbn}`;
  const [src, setSrc] = useState(book.cover || proxy);
  const [failed, setFailed] = useState(false);
  useEffect(() => { setSrc(book.cover || proxy); setFailed(false); }, [book.cover, proxy]);

  const p = PALETTES[hashCode(book.isbn || "") % PALETTES.length];
  const tip = (book.is_new ? "【新しく加わった本】" : "") + (book.recommended
    ? `おすすめ：${book.title}${book.recommended_for ? `（${book.recommended_for}から）` : ""}`
    : book.title);

  return (
    <div
      draggable
      className={arrived ? "grid-book-arrived" : undefined}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      title={tip}
      style={{
        ...s.tile,
        opacity: hidden ? 0 : dragging ? 0.35 : dimmed ? 0.22 : 1,
        ...(mark ? {
          outline: `${mark.width}px ${mark.dashed ? "dashed" : "solid"} ${mark.color}`,
          outlineOffset: 3,
          boxShadow: `0 0 10px ${mark.color}99`,
        } : {}),
        ...(selected ? s.tileSelected : {}),
      }}
    >
      {!failed ? (
        <img
          src={src}
          alt={book.title}
          draggable={false}
          style={s.cover}
          onError={() => { if (src !== proxy) setSrc(proxy); else setFailed(true); }}
        />
      ) : (
        <div style={{ ...s.card, background: p.bg, color: p.text }}>{book.title}</div>
      )}
      {book.recommended && <span style={s.badge}>✦</span>}
      {book.is_new && <span style={s.newBadge}>新</span>}
      {selected && <span style={s.checkBadge}>✓</span>}
    </div>
  );
}

const s = {
  wrap: { position: "relative", width: "100%", margin: "0 auto", padding: "4px 4px 96px", boxSizing: "border-box" },
  toolbar: {
    display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
    margin: "0 0 10px",
  },
  selectBtn: {
    height: 30, padding: "0 14px", borderRadius: 999, border: "1px solid #e0d8c0",
    background: "#fff", color: "#6b5a3e", fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
  },
  selectBtnOn: { background: "#3a7bd5", borderColor: "#3a7bd5", color: "#fff" },
  bulkBar: {
    display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
    padding: "4px 6px 4px 12px", borderRadius: 999, background: "#eaf2fd", border: "1px solid #c7dbf7",
  },
  bulkCount: { fontSize: 12, fontWeight: 700, color: "#2a5ea8" },
  bulkHint: { fontSize: 11, color: "#5a7fb5" },
  bulkSelect: {
    height: 26, borderRadius: 999, border: "1px solid #c7dbf7", background: "#fff", color: "#2a5ea8",
    fontSize: 12, fontFamily: "inherit", padding: "0 8px",
  },
  bulkBtn: {
    height: 26, padding: "0 10px", borderRadius: 999, border: "1px solid #c7dbf7", background: "#fff",
    color: "#2a5ea8", fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
  },
  tileSelected: {
    outline: "3px solid #3a7bd5", outlineOffset: 2, boxShadow: "0 0 12px rgba(58,123,213,0.6)",
  },
  checkBadge: {
    position: "absolute", bottom: 4, right: 4, width: 18, height: 18, borderRadius: "50%",
    background: "#3a7bd5", color: "#fff", fontSize: 11, fontWeight: 700, lineHeight: "18px", textAlign: "center",
    boxShadow: "0 1px 3px rgba(0,0,0,0.4)", pointerEvents: "none",
  },
  toolLabel: { fontSize: 12, fontWeight: 700, color: "#8a7030", marginRight: 2 },
  stepBtn: {
    width: 28, height: 28, borderRadius: "50%", border: "1px solid #e0d8c0",
    background: "#fff", color: "#6b5a3e", fontSize: 15, fontWeight: 700, lineHeight: 1,
    cursor: "pointer", fontFamily: "inherit", padding: 0,
  },
  stepBtnOff: { opacity: 0.4, cursor: "default" },
  colsValue: { minWidth: 34, textAlign: "center", fontSize: 13, fontWeight: 700, color: "#4a3728" },
  empty: { textAlign: "center", color: "#9a8a6a", fontSize: 13, padding: "12px 0 16px" },
  // 本棚の外枠（暗い奥板と左右の側板）。中の行ごとに棚板で仕切る
  shelf: {
    padding: "14px 0 0", borderRadius: 6, overflow: "hidden",
    background: "linear-gradient(rgba(0,0,0,0.28), rgba(0,0,0,0.28)), url(/sources/dark_wood_texture.jpg) center / 500px",
    borderLeft: "14px solid #8a6238", borderRight: "14px solid #8a6238",
    boxShadow: "0 14px 30px rgba(60,40,10,0.22)",
  },
  row: { display: "flex", flexDirection: "column" },
  grid: {
    display: "grid", gap: 10,
    padding: "0 14px",
  },
  // 棚板（本はこの上に立つ）
  board: {
    height: 16, marginBottom: 14,
    background: "url(/sources/wood_texture.jpg) center / 300px, #a07443",
    boxShadow: "0 4px 6px rgba(0,0,0,0.35), inset 0 2px 0 rgba(255,255,255,0.18)",
  },
  cell: {
    aspectRatio: "2 / 3", borderRadius: 6,
    background: "rgba(255,255,255,0.04)",
    boxSizing: "border-box", position: "relative",
    transition: "background 0.12s, border-color 0.12s",
  },
  cellOver: { background: "rgba(100,180,255,0.18)", boxShadow: "inset 0 0 0 2px rgba(70,150,230,0.8)" },
  tile: {
    position: "absolute", inset: 0, borderRadius: 5, overflow: "hidden",
    cursor: "grab", background: "#fff",
    boxShadow: "0 3px 8px rgba(60,40,10,0.22)",
    transition: "opacity 0.15s",
  },
  cover: { width: "100%", height: "100%", objectFit: "cover", display: "block", pointerEvents: "none" },
  card: {
    width: "100%", height: "100%", padding: 6, boxSizing: "border-box",
    fontFamily: "serif", fontWeight: 600, fontSize: 11, lineHeight: 1.3,
    display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center",
    overflow: "hidden", wordBreak: "break-all",
  },
  // 前回の対話より後に加わった本の印（次の対話が始まると消える）
  newBadge: {
    position: "absolute", top: 3, left: 3, padding: "1px 5px", borderRadius: 999,
    background: "#e0533d", color: "#fff", fontSize: 10, fontWeight: 700, lineHeight: 1.4,
    boxShadow: "0 1px 3px rgba(0,0,0,0.35)", pointerEvents: "none",
  },
  badge: {
    position: "absolute", top: 3, right: 4, fontSize: 12, color: RECOMMENDED.badge,
    textShadow: "0 0 3px #fff, 0 0 3px #fff", pointerEvents: "none",
  },
  trash: {
    position: "fixed", bottom: 30, left: "50%", transform: "translateX(-50%)",
    width: 64, height: 64, borderRadius: "50%",
    border: "2px dashed #bbb", backgroundColor: "rgba(255,255,255,0.92)",
    display: "flex", alignItems: "center", justifyContent: "center", color: "#aaa",
    transition: "opacity 0.15s, background-color 0.15s, border-color 0.15s, transform 0.15s, color 0.15s",
    zIndex: 2000, backdropFilter: "blur(6px)", boxShadow: "0 4px 20px rgba(0,0,0,0.12)",
  },
  trashOver: {
    backgroundColor: "rgba(220,50,50,0.15)", borderColor: "#e53935", color: "#e53935",
    transform: "translateX(-50%) scale(1.18)",
  },
};
