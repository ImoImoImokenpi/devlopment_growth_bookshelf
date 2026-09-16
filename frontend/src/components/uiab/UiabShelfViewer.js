// 観察者向けの読み取り専用ビューア。新UI由来(自由配置)/旧UI由来(グリッド)の
// どちらの座標データが来ても、そのまま忠実に再現する。群のラベルやメタ情報は
// 一切表示しない(渡されてもいない)——ブラインド化はこのコンポーネントの外、
// バックエンドのレスポンス段階で保証されている。
function spineSize(book) {
  const width = Math.min(50, Math.max(16, (book.pages || 200) * 0.13));
  const height = Math.min(150, Math.max(60, (book.height_mm || 180) * 0.65));
  return { width, height };
}

export default function UiabShelfViewer({ shelf, groups }) {
  const isGrid = shelf.some(b => b.grid_row != null);

  return (
    <div style={s.wrap}>
      {isGrid ? <GridView shelf={shelf} /> : <FreeView shelf={shelf} />}
      {groups && groups.length > 0 && (
        <div style={s.groupBox}>
          <div style={s.groupHeading}>グループ</div>
          {groups.map(g => (
            <div key={g.group_id} style={s.groupRow}>
              <span style={s.groupLabel}>{g.label}</span>
              <span style={s.groupMembers}>{g.members.map(m => m.title || m.isbn).join(" / ")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FreeView({ shelf }) {
  const byShelf = {};
  shelf.forEach(b => {
    const idx = b.shelf_index ?? 0;
    (byShelf[idx] = byShelf[idx] || []).push(b);
  });
  const rows = Object.keys(byShelf).sort((a, b) => a - b);

  return (
    <div style={s.freeWrap}>
      {rows.map(idx => (
        <div key={idx} style={s.freeRow}>
          {[...byShelf[idx]].sort((a, b) => a.x_pos - b.x_pos).map(book => {
            const { width, height } = spineSize(book);
            return (
              <div
                key={book.isbn}
                title={book.title}
                style={{
                  ...s.spine, width, height,
                  background: book.spine_color ? `rgb(${book.spine_color})` : "#968c78",
                }}
              >
                <span style={s.spineText}>{book.title}</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function GridView({ shelf }) {
  const maxRow = Math.max(0, ...shelf.map(b => b.grid_row ?? 0));
  const maxCol = Math.max(0, ...shelf.map(b => b.grid_col ?? 0));
  const cellMap = {};
  shelf.forEach(b => { cellMap[`${b.grid_row ?? 0}:${b.grid_col ?? 0}`] = b; });

  return (
    <div style={s.gridWrap}>
      {Array.from({ length: maxRow + 1 }).map((_, row) => (
        <div key={row} style={s.gridRow}>
          {Array.from({ length: maxCol + 1 }).map((_, col) => {
            const book = cellMap[`${row}:${col}`];
            return (
              <div key={col} style={{ ...s.cell, ...(book ? s.cellFilled : s.cellEmpty) }}>
                {book && (
                  <>
                    <div style={s.cellTitle}>{book.title}</div>
                    <div style={s.cellAuthor}>{book.authors}</div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

const s = {
  wrap: { display: "flex", flexDirection: "column", gap: 16 },
  freeWrap: { display: "flex", flexDirection: "column", gap: 10 },
  freeRow: {
    display: "flex", alignItems: "flex-end", gap: 6, padding: "0 16px 10px",
    background: "#241a10", borderRadius: 8, borderBottom: "8px solid #4a3018", overflowX: "auto",
  },
  spine: {
    borderRadius: 2, position: "relative", overflow: "hidden",
    boxShadow: "0 2px 6px rgba(0,0,0,0.4)", display: "flex", alignItems: "flex-end", justifyContent: "center",
  },
  spineText: {
    writingMode: "vertical-rl", color: "#fff", fontSize: 9, padding: 3,
    fontFamily: "serif", fontWeight: 700, textShadow: "0 1px 2px rgba(0,0,0,0.5)",
    maxHeight: "100%", overflow: "hidden",
  },
  gridWrap: { display: "flex", flexDirection: "column", gap: 6, background: "#e9e3d4", padding: 10, borderRadius: 8 },
  gridRow: { display: "flex", gap: 6 },
  cell: { width: 100, height: 100, borderRadius: 6, boxSizing: "border-box", padding: 6, fontSize: 10.5 },
  cellEmpty: { border: "1px dashed #c4b8a2", background: "#fdfcf8" },
  cellFilled: { border: "1px solid #d0c4a8", background: "#fff" },
  cellTitle: {
    fontWeight: 700, color: "#2a1f0e",
    overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
  },
  cellAuthor: { fontSize: 9, color: "#9a8b76" },
  groupBox: { display: "flex", flexDirection: "column", gap: 6 },
  groupHeading: { fontSize: 10.5, fontWeight: 700, color: "#c9a84c", textTransform: "uppercase", letterSpacing: "0.05em" },
  groupRow: { fontSize: 11.5, color: "#4a3728" },
  groupLabel: { fontWeight: 700, marginRight: 8 },
  groupMembers: { color: "#9a8b76" },
};
