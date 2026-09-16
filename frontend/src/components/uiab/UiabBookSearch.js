// ISBN検索→時期別蔵書への追加。書誌検索自体は既存の /register/fetch/{isbn}
// (NDL連携)をそのまま使う。色は「数年前の本を物理的に持っていない」ケースを
// 想定して手動・任意入力にしている(自動抽出は不要、フェーズ1と同じ考え方)。
import { useState } from "react";
import { API_ORIGIN, uiabPost } from "../../utils/uiabIdentity";

export default function UiabBookSearch({ period, onAdded }) {
  const [isbn, setIsbn] = useState("");
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState(null);
  const [color, setColor] = useState("#968c78");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState(null);

  const search = async () => {
    const cleaned = isbn.trim();
    if (!cleaned) return;
    setSearching(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_ORIGIN}/register/fetch/${cleaned}`);
      if (!res.ok) throw new Error("見つかりませんでした");
      setResult(await res.json());
    } catch (err) {
      setError(err.message || "検索に失敗しました");
    } finally {
      setSearching(false);
    }
  };

  const add = async () => {
    if (!result) return;
    setAdding(true);
    setError(null);
    try {
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);
      await uiabPost(`/uiab/${period}/collection`, {
        isbn: result.isbn, title: result.title, authors: result.authors,
        publisher: result.publisher, published_year: result.published_year,
        height_mm: result.height_mm, pages: result.pages, cover: result.cover,
        spine_color: `${r},${g},${b}`,
      });
      setResult(null);
      setIsbn("");
      onAdded?.();
    } catch (err) {
      setError(err.message || "追加に失敗しました");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div style={s.wrap}>
      <div style={s.row}>
        <input
          style={s.input}
          value={isbn}
          onChange={e => setIsbn(e.target.value)}
          placeholder="ISBN(例: 978-4-...)"
          onKeyDown={e => e.key === "Enter" && search()}
        />
        <button style={s.searchBtn} onClick={search} disabled={searching}>
          {searching ? "検索中…" : "検索"}
        </button>
      </div>

      {error && <div style={s.error}>{error}</div>}

      {result && (
        <div style={s.resultCard}>
          <div style={s.resultTitle}>{result.title || "（タイトル不明）"}</div>
          <div style={s.resultMeta}>{result.authors}</div>
          <div style={s.colorRow}>
            <span style={s.colorLabel}>背表紙の色(任意・手元にあれば見た目に近い色を)</span>
            <input type="color" value={color} onChange={e => setColor(e.target.value)} />
          </div>
          <button style={s.addBtn} onClick={add} disabled={adding}>
            {adding ? "追加中…" : "この本を蔵書に追加"}
          </button>
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: { display: "flex", flexDirection: "column", gap: 8 },
  row: { display: "flex", gap: 6 },
  input: {
    flex: 1, padding: "8px 10px", borderRadius: 8, border: "1px solid #d0c4a8",
    fontSize: 12.5, outline: "none",
  },
  searchBtn: {
    padding: "8px 14px", background: "#c9a84c", color: "#fff", border: "none",
    borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap",
  },
  error: { fontSize: 11.5, color: "#c9506a" },
  resultCard: {
    padding: "10px 12px", borderRadius: 10, border: "1px solid #ede8da",
    background: "#fffdf7", display: "flex", flexDirection: "column", gap: 8,
  },
  resultTitle: { fontSize: 13, fontWeight: 700, color: "#2a1f0e" },
  resultMeta: { fontSize: 11.5, color: "#8a7960" },
  colorRow: { display: "flex", alignItems: "center", gap: 8 },
  colorLabel: { fontSize: 10.5, color: "#9a8b76" },
  addBtn: {
    padding: "8px 0", background: "#c9a84c", color: "#fff", border: "none",
    borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
  },
};
