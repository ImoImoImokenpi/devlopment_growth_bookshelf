// 「グリッド表示」モードの中身（背表紙表示との切り替え用）。
//
// My本棚（自分のデータ）と、みんなの本棚（他者のデータ・読み取り専用）の
// 両方から、カードグリッドの見た目とソートだけを共有するための
// 純粋な表示コンポーネント。データの取得方法・クリック時の挙動は
// 呼び出し側（OwnBookGrid.js / explore/ReadOnlyBookGrid.js）に任せる。
import { useEffect, useMemo, useState } from "react";

const API = "http://localhost:8000";

const SORTS = {
  title:    { label: "タイトル",    key: b => b.title || "" },
  author:   { label: "著者",        key: b => (b.authors && b.authors[0]) || "" },
  ndc:      { label: "ジャンル(NDC)", key: b => b.ndc || "" },
  registered_at: { label: "登録日", key: b => b.registered_at || "" },
};

export default function BookGridPane({ books, focusIsbn, onFocus, highlightIsbns, emptyMessage = "棚に本がありません。" }) {
  const [sortKey, setSortKey] = useState("title");
  const [sortDir, setSortDir] = useState("asc");

  const sortedBooks = useMemo(() => {
    const keyFn = SORTS[sortKey].key;
    const sorted = [...books].sort((a, b) => {
      const av = keyFn(a), bv = keyFn(b);
      return String(av).localeCompare(String(bv), "ja");
    });
    return sortDir === "asc" ? sorted : sorted.reverse();
  }, [books, sortKey, sortDir]);

  const highlightSet = useMemo(() => new Set(highlightIsbns || []), [highlightIsbns]);

  // 対話側でハイライトされた本が画面外だと何の話か分からないので、
  // 先頭の1冊まで自動スクロールして視界に入れる。
  useEffect(() => {
    if (!highlightIsbns || highlightIsbns.length === 0) return;
    const el = document.getElementById(`grid-book-${CSS.escape(highlightIsbns[0])}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightIsbns]);

  return (
    <div>
      <div style={s.controls}>
        <label style={s.sortLabel}>
          並び替え
          <select value={sortKey} onChange={e => setSortKey(e.target.value)} style={s.select}>
            {Object.entries(SORTS).map(([key, { label }]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </label>
        <button
          style={s.dirButton}
          onClick={() => setSortDir(d => (d === "asc" ? "desc" : "asc"))}
          title="昇順・降順を切り替え"
        >
          {sortDir === "asc" ? "昇順 ↑" : "降順 ↓"}
        </button>
      </div>

      {sortedBooks.length === 0 ? (
        <p style={s.empty}>{emptyMessage}</p>
      ) : (
        <div style={s.grid}>
          {sortedBooks.map(book => (
            <GridBook
              key={book.isbn}
              book={book}
              isFocused={book.isbn === focusIsbn}
              isHighlighted={highlightSet.has(book.isbn) && book.isbn !== focusIsbn}
              onClick={() => onFocus?.(book.isbn)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function GridBook({ book, isFocused, isHighlighted, onClick }) {
  const proxySrc = `${API}/register/cover/${book.isbn}`;
  const [src, setSrc] = useState(book.cover || proxySrc);
  const [failed, setFailed] = useState(false);

  const handleError = () => {
    if (src !== proxySrc) setSrc(proxySrc);
    else setFailed(true);
  };

  return (
    <div
      id={`grid-book-${book.isbn}`}
      style={{
        ...s.card,
        ...(isHighlighted ? s.cardHighlighted : {}),
        ...(isFocused ? s.cardFocused : {}),
      }}
      title={book.title}
      onClick={onClick}
    >
      <div style={s.thumbWrap}>
        {!failed ? (
          <img src={src} alt={book.title} style={s.thumb} onError={handleError} />
        ) : (
          <div style={s.thumbFallback}>{book.title}</div>
        )}
      </div>
      <div style={s.title}>{book.title}</div>
      <div style={s.meta}>{(book.authors || []).join(", ")}</div>
    </div>
  );
}

const s = {
  controls: { display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" },
  sortLabel: { display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#555" },
  select: {
    fontSize: 13, padding: "4px 8px", borderRadius: 6,
    border: "1px solid #ccc", background: "#fff",
  },
  dirButton: {
    fontSize: 13, padding: "5px 10px", borderRadius: 6,
    border: "1px solid #ccc", background: "#fff", cursor: "pointer",
  },
  empty: { color: "#888", fontSize: 14 },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
    gap: 18,
  },
  card: { display: "flex", flexDirection: "column", gap: 4, cursor: "pointer", borderRadius: 6, padding: 4 },
  cardHighlighted: { outline: "2px solid #c9a84c", outlineOffset: 2, background: "#fbf6e4" },
  cardFocused: { outline: "2px solid #ff9d3d", outlineOffset: 2 },
  thumbWrap: {
    width: "100%", aspectRatio: "3 / 4",
    background: "#eee", borderRadius: 4, overflow: "hidden",
    display: "flex", alignItems: "center", justifyContent: "center",
    border: "1px solid #ddd",
  },
  thumb: { width: "100%", height: "100%", objectFit: "cover" },
  thumbFallback: {
    fontSize: 11, color: "#666", textAlign: "center", padding: 6,
    overflow: "hidden", display: "-webkit-box",
    WebkitLineClamp: 4, WebkitBoxOrient: "vertical",
  },
  title: { fontSize: 12.5, fontWeight: 600, color: "#222", lineHeight: 1.35 },
  meta: { fontSize: 11, color: "#777" },
};
