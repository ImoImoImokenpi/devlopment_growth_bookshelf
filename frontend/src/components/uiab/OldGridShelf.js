// 旧UI: 固定グリッドへの配置のみ、背表紙は簡易表示(タイトル・著者)のみ。
// 新UIにある「詳細表示(色・厚み)」に相当する機能は意図的に持たせない
// (これが2群の比較対象そのものなので、フェアにするための機能追加はしない)。
import { useState } from "react";
import { uiabPost, uiabDelete } from "../../utils/uiabIdentity";

const COLS = 6;
const ROWS = 4;

export default function OldGridShelf({ period, positions, unplaced, selectedIsbns, onToggleSelect, onFocus, onChanged }) {
  const [armedIsbn, setArmedIsbn] = useState(null);

  const cellMap = {};
  positions.forEach(p => { cellMap[`${p.grid_row ?? 0}:${p.grid_col ?? 0}`] = p; });

  const logMove = (isbn, prev, row, col) => {
    uiabPost(`/uiab/${period}/event`, {
      event_type: "move", isbn,
      extra: {
        from_grid_row: prev?.grid_row ?? null, from_grid_col: prev?.grid_col ?? null,
        to_grid_row: row, to_grid_col: col,
      },
    }).catch(err => console.error(err));
  };

  const placeAt = async (row, col) => {
    if (!armedIsbn || cellMap[`${row}:${col}`]) return;
    const prev = positions.find(p => p.isbn === armedIsbn);
    try {
      await uiabPost(`/uiab/${period}/shelf/position`, { isbn: armedIsbn, grid_row: row, grid_col: col });
      logMove(armedIsbn, prev, row, col);
      setArmedIsbn(null);
      onChanged();
    } catch (err) {
      console.error(err);
    }
  };

  const pickUp = (isbn) => setArmedIsbn(prev => (prev === isbn ? null : isbn));

  const removeFromGrid = async (isbn) => {
    const prev = positions.find(p => p.isbn === isbn);
    try {
      await uiabDelete(`/uiab/${period}/shelf/position/${isbn}`);
      logMove(isbn, prev, null, null);
      onChanged();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div style={s.wrap}>
      <div style={s.grid}>
        {Array.from({ length: ROWS }).map((_, row) => (
          <div key={row} style={s.gridRow}>
            {Array.from({ length: COLS }).map((_, col) => {
              const book = cellMap[`${row}:${col}`];
              if (book) {
                const selected = selectedIsbns.includes(book.isbn);
                return (
                  <div key={col} style={{ ...s.cell, ...s.cellFilled, ...(armedIsbn === book.isbn ? s.cellArmed : {}) }}>
                    <div style={s.cellTitle} onClick={() => onFocus(book.isbn)} title={book.title}>{book.title}</div>
                    <div style={s.cellAuthor}>{book.authors}</div>
                    <div style={s.cellControls}>
                      <input type="checkbox" checked={selected} onChange={() => onToggleSelect(book.isbn)} />
                      <button style={s.smallBtn} onClick={() => pickUp(book.isbn)}>移動</button>
                      <button style={s.smallBtn} onClick={() => removeFromGrid(book.isbn)}>外す</button>
                    </div>
                  </div>
                );
              }
              return (
                <button
                  key={col}
                  style={{ ...s.cell, ...s.cellEmpty, ...(armedIsbn ? s.cellTargetable : {}) }}
                  onClick={() => placeAt(row, col)}
                  disabled={!armedIsbn}
                />
              );
            })}
          </div>
        ))}
      </div>

      <div style={s.tray}>
        <div style={s.trayLabel}>未配置の本(クリックして選び、空きマスをクリックして置いてください)</div>
        <div style={s.trayItems}>
          {unplaced.map(book => (
            <button
              key={book.isbn}
              style={{ ...s.trayChip, ...(armedIsbn === book.isbn ? s.trayChipArmed : {}) }}
              onClick={() => pickUp(book.isbn)}
            >
              {book.title}
            </button>
          ))}
          {unplaced.length === 0 && <span style={s.trayEmpty}>すべて配置済みです</span>}
        </div>
      </div>
    </div>
  );
}

const s = {
  wrap: { display: "flex", flexDirection: "column", gap: 12 },
  grid: {
    display: "flex", flexDirection: "column", gap: 6, background: "#e9e3d4",
    padding: 10, borderRadius: 8,
  },
  gridRow: { display: "flex", gap: 6 },
  cell: {
    width: 110, height: 110, borderRadius: 6, boxSizing: "border-box",
    display: "flex", flexDirection: "column", padding: 6, fontSize: 11,
  },
  cellEmpty: {
    border: "1px dashed #c4b8a2", background: "#fdfcf8", cursor: "not-allowed",
  },
  cellTargetable: { cursor: "pointer", background: "#fff3d6", borderColor: "#c9a84c" },
  cellFilled: { border: "1px solid #d0c4a8", background: "#fff", justifyContent: "space-between" },
  cellArmed: { outline: "2px solid #64b4ff" },
  cellTitle: {
    fontWeight: 700, color: "#2a1f0e", cursor: "pointer",
    overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
  },
  cellAuthor: { fontSize: 9.5, color: "#9a8b76", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  cellControls: { display: "flex", alignItems: "center", gap: 3, marginTop: 2 },
  smallBtn: {
    fontSize: 8.5, padding: "1px 5px", borderRadius: 5, border: "1px solid #d0c4a8",
    background: "#fff", color: "#8a7960", cursor: "pointer",
  },
  tray: { minHeight: 60, border: "1px dashed #d0c4a8", borderRadius: 10, padding: 10, background: "#faf8f2" },
  trayLabel: { fontSize: 10.5, color: "#9a8b76", marginBottom: 6 },
  trayItems: { display: "flex", flexWrap: "wrap", gap: 6 },
  trayChip: {
    padding: "5px 10px", borderRadius: 8, background: "#fff", border: "1px solid #e5ded0",
    fontSize: 11.5, cursor: "pointer", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  trayChipArmed: { borderColor: "#64b4ff", background: "#eef6ff" },
  trayEmpty: { fontSize: 11, color: "#bbb" },
};
