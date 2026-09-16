// 新UI: 自由配置・詳細表示(色・厚み)・即時反映。
// ドラッグ操作はHTML5 Drag and Drop APIで実装(既存のSpineShelfViewのような
// D3実装より単純だが、「自由な座標配置」「即時反映」という要件は満たす)。
import { useState } from "react";
import { uiabPost, uiabDelete } from "../../utils/uiabIdentity";

const FRAME = 16;
const ROWS = 3;
const ROW_HEIGHT = 170;

function spineSize(book) {
  const width = Math.min(50, Math.max(16, (book.pages || 200) * 0.13));
  const height = Math.min(150, Math.max(60, (book.height_mm || 180) * 0.65));
  return { width, height };
}

export default function NewFreeShelf({ period, positions, unplaced, selectedIsbns, onToggleSelect, onFocus, onChanged }) {
  const [detailIsbn, setDetailIsbn] = useState(null);

  const rowsData = Array.from({ length: ROWS }, (_, i) =>
    positions.filter(p => (p.shelf_index ?? 0) === i)
  );

  const logEvent = (eventType, isbn, extra) => {
    uiabPost(`/uiab/${period}/event`, { event_type: eventType, isbn, extra: extra || {} }).catch(err => console.error(err));
  };

  const onDragStart = (e, isbn) => {
    e.dataTransfer.setData("text/isbn", isbn);
  };

  const dropOnShelf = async (e, shelfIndex) => {
    e.preventDefault();
    const isbn = e.dataTransfer.getData("text/isbn");
    if (!isbn) return;
    const prev = positions.find(p => p.isbn === isbn);
    const rect = e.currentTarget.getBoundingClientRect();
    const xPos = Math.max(0, Math.round(e.clientX - rect.left - FRAME));
    try {
      await uiabPost(`/uiab/${period}/shelf/position`, { isbn, shelf_index: shelfIndex, x_pos: xPos });
      logEvent("move", isbn, {
        from_shelf_index: prev?.shelf_index ?? null, from_x_pos: prev?.x_pos ?? null,
        to_shelf_index: shelfIndex, to_x_pos: xPos,
      });
      onChanged();
    } catch (err) {
      console.error(err);
    }
  };

  const dropOnTray = async (e) => {
    e.preventDefault();
    const isbn = e.dataTransfer.getData("text/isbn");
    const prev = positions.find(p => p.isbn === isbn);
    if (!isbn || !prev) return;
    try {
      await uiabDelete(`/uiab/${period}/shelf/position/${isbn}`);
      logEvent("move", isbn, {
        from_shelf_index: prev.shelf_index, from_x_pos: prev.x_pos,
        to_shelf_index: null, to_x_pos: null,
      });
      onChanged();
    } catch (err) {
      console.error(err);
    }
  };

  const toggleDetail = (isbn) => {
    if (detailIsbn === isbn) {
      logEvent("detail_view_close", isbn, {});
      setDetailIsbn(null);
    } else {
      if (detailIsbn) logEvent("detail_view_close", detailIsbn, {});
      logEvent("detail_view_open", isbn, {});
      setDetailIsbn(isbn);
    }
  };

  return (
    <div style={s.wrap}>
      {rowsData.map((books, shelfIndex) => (
        <div
          key={shelfIndex}
          style={{ ...s.row, height: ROW_HEIGHT }}
          onDragOver={e => e.preventDefault()}
          onDrop={e => dropOnShelf(e, shelfIndex)}
        >
          {[...books].sort((a, b) => a.x_pos - b.x_pos).map(book => {
            const { width, height } = spineSize(book);
            const selected = selectedIsbns.includes(book.isbn);
            return (
              <div key={book.isbn} style={s.spineOuter}>
                <div
                  draggable
                  onDragStart={e => onDragStart(e, book.isbn)}
                  onClick={() => onFocus(book.isbn)}
                  title={book.title}
                  style={{
                    ...s.spine, width, height,
                    background: book.spine_color ? `rgb(${book.spine_color})` : "#968c78",
                    outline: selected ? "2px solid #64b4ff" : "1px solid rgba(0,0,0,0.15)",
                  }}
                >
                  <span style={s.spineText}>{book.title}</span>
                </div>
                <div style={s.spineControls}>
                  <input
                    type="checkbox" checked={selected} onChange={() => onToggleSelect(book.isbn)}
                    title="グループに選択"
                  />
                  <button style={s.detailBtn} onClick={() => toggleDetail(book.isbn)}>詳細</button>
                </div>
                {detailIsbn === book.isbn && (
                  <div style={s.detailPanel}>
                    <div>{book.pages}p ／ 高さ{book.height_mm}mm</div>
                    <div style={s.detailColorRow}>
                      色
                      <span style={{ ...s.colorDot, background: book.spine_color ? `rgb(${book.spine_color})` : "#968c78" }} />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}

      <div style={s.tray} onDragOver={e => e.preventDefault()} onDrop={dropOnTray}>
        <div style={s.trayLabel}>未配置(ここへドラッグすると棚から外せます)</div>
        <div style={s.trayItems}>
          {unplaced.map(book => (
            <div
              key={book.isbn}
              draggable
              onDragStart={e => onDragStart(e, book.isbn)}
              onClick={() => onFocus(book.isbn)}
              style={s.trayChip}
              title={book.title}
            >
              {book.title}
            </div>
          ))}
          {unplaced.length === 0 && <span style={s.trayEmpty}>すべて配置済みです</span>}
        </div>
      </div>
    </div>
  );
}

const s = {
  wrap: { display: "flex", flexDirection: "column", gap: 12 },
  row: {
    display: "flex", alignItems: "flex-end", gap: 6, padding: `0 ${FRAME}px 10px`,
    background: "#241a10", borderRadius: 8, borderBottom: "8px solid #4a3018",
    overflowX: "auto",
  },
  spineOuter: { display: "flex", flexDirection: "column", alignItems: "center", gap: 4, position: "relative" },
  spine: {
    borderRadius: 2, cursor: "grab", position: "relative", overflow: "hidden",
    boxShadow: "0 2px 6px rgba(0,0,0,0.4)", display: "flex", alignItems: "flex-end", justifyContent: "center",
  },
  spineText: {
    writingMode: "vertical-rl", color: "#fff", fontSize: 9, padding: 3,
    fontFamily: "serif", fontWeight: 700, textShadow: "0 1px 2px rgba(0,0,0,0.5)",
    maxHeight: "100%", overflow: "hidden",
  },
  spineControls: { display: "flex", alignItems: "center", gap: 4 },
  detailBtn: {
    fontSize: 9.5, padding: "1px 6px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.3)",
    background: "transparent", color: "#ddd", cursor: "pointer",
  },
  detailPanel: {
    position: "absolute", bottom: "100%", left: "50%", transform: "translateX(-50%)",
    marginBottom: 6, background: "#fff", color: "#2a1f0e", fontSize: 10.5,
    padding: "6px 10px", borderRadius: 8, boxShadow: "0 4px 14px rgba(0,0,0,0.25)",
    whiteSpace: "nowrap", zIndex: 5,
  },
  detailColorRow: { display: "flex", alignItems: "center", gap: 6, marginTop: 3 },
  colorDot: { width: 12, height: 12, borderRadius: "50%", border: "1px solid rgba(0,0,0,0.2)" },
  tray: {
    minHeight: 70, border: "1px dashed #d0c4a8", borderRadius: 10, padding: 10,
    background: "#faf8f2",
  },
  trayLabel: { fontSize: 10.5, color: "#9a8b76", marginBottom: 6 },
  trayItems: { display: "flex", flexWrap: "wrap", gap: 6 },
  trayChip: {
    padding: "5px 10px", borderRadius: 8, background: "#fff", border: "1px solid #e5ded0",
    fontSize: 11.5, cursor: "grab", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  trayEmpty: { fontSize: 11, color: "#bbb" },
};
