import { useState, useContext } from "react";
import Layout from "../components/Layout";
import axios from "axios";
import { MyHandContext } from "../context/MyHandContext";

// ─── 背表紙の色パレット（ISBNからハッシュで決定） ───
const SPINE_PALETTES = [
  { bg: "#1a1a2e", text: "#e8d5a3", accent: "#c9a84c" },
  { bg: "#2d1b33", text: "#f0e6d3", accent: "#d4a0c0" },
  { bg: "#0d2137", text: "#cce5f0", accent: "#5ba3c9" },
  { bg: "#1e3a2f", text: "#d4edd8", accent: "#7ab893" },
  { bg: "#3b1f0e", text: "#f5dfc5", accent: "#d4823a" },
  { bg: "#2a2a2a", text: "#e8e8e8", accent: "#ff6b35" },
  { bg: "#1f2d3d", text: "#d8e4ec", accent: "#4a9eca" },
  { bg: "#3d1f1f", text: "#f5d5d5", accent: "#c9506a" },
  { bg: "#2d2d1a", text: "#eeeeda", accent: "#c8b84a" },
  { bg: "#1a2d2d", text: "#d5eeed", accent: "#4abcb8" },
  { bg: "#f5f0e8", text: "#2a2018", accent: "#8b4513" },
  { bg: "#eef5f0", text: "#1a2d22", accent: "#2d7a4a" },
  { bg: "#f5eef5", text: "#2a1a2a", accent: "#7a2d8b" },
  { bg: "#f0f5ee", text: "#1e2a1a", accent: "#4a8b2d" },
];

function hashCode(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function getPalette(book) {
  const seed = book.isbn || book.title || "";
  return SPINE_PALETTES[hashCode(seed) % SPINE_PALETTES.length];
}

// ─── 背表紙サイズ計算 ───
function getSpineDimensions(book) {
  // 高さ：実寸mm → px（1mm ≒ 1.2px、範囲 140〜230px）
  const heightPx = book.height_mm
    ? Math.min(230, Math.max(140, book.height_mm * 1.2))
    : 180;
  // 幅：ページ数 × 0.065mm/p × 1.8 拡大、範囲 18〜55px
  const widthMm = book.pages ? book.pages * 0.065 : 15;
  const widthPx = Math.min(55, Math.max(18, widthMm * 1.8));
  return { heightPx, widthPx };
}

// ─── 背表紙コンポーネント ───
function SpineCard({ book, onClick, onAdd }) {
  const [hovered, setHovered] = useState(false);
  const palette = getPalette(book);
  const { heightPx, widthPx } = getSpineDimensions(book);
  const fontSize = widthPx < 26 ? "0.6rem" : widthPx < 36 ? "0.7rem" : "0.8rem";

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        flexShrink: 0,
        zIndex: hovered ? 100 : 1,
      }}
    >
      {/* ── ホバーポップアップ ── */}
      {hovered && (
        <div
          style={{
            position: "absolute",
            bottom: `${heightPx + 10}px`,
            left: "50%",
            transform: "translateX(-50%)",
            width: "160px",
            backgroundColor: "#fff",
            borderRadius: "10px",
            boxShadow: "0 8px 32px rgba(0,0,0,0.28), 0 2px 8px rgba(0,0,0,0.12)",
            padding: "12px",
            zIndex: 200,
            pointerEvents: "auto",
            animation: "popIn 0.18s cubic-bezier(0.34,1.56,0.64,1)",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* 吹き出し三角 */}
          <div style={{
            position: "absolute",
            bottom: "-8px",
            left: "50%",
            transform: "translateX(-50%)",
            width: 0, height: 0,
            borderLeft: "8px solid transparent",
            borderRight: "8px solid transparent",
            borderTop: "8px solid #fff",
            filter: "drop-shadow(0 2px 2px rgba(0,0,0,0.10))",
          }} />

          {/* 表紙画像 */}
          <div style={{ width: "100%", height: "110px", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "8px", overflow: "hidden" }}>
            {book.cover ? (
              <img
                src={book.cover}
                alt={book.title}
                referrerPolicy="no-referrer"
                style={{ maxHeight: "110px", maxWidth: "100%", objectFit: "contain", borderRadius: "4px", boxShadow: "0 2px 6px rgba(0,0,0,0.18)" }}
              />
            ) : (
              <div style={{ width: "72px", height: "100px", background: palette.bg, borderRadius: "4px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontSize: "0.6rem", color: palette.text, textAlign: "center", padding: "4px" }}>No Image</span>
              </div>
            )}
          </div>

          {/* タイトル */}
          <p style={{
            fontSize: "0.75rem",
            fontWeight: "700",
            color: "#222",
            margin: "0 0 3px 0",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            lineHeight: "1.3",
          }}>
            {book.title}
          </p>

          {/* 著者 */}
          <p style={{ fontSize: "0.65rem", color: "#888", margin: "0 0 8px 0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {book.authors?.join(", ") || "著者不明"}
          </p>

          {/* ボタン群 */}
          <div style={{ display: "flex", gap: "5px" }}>
            <button
              onClick={() => onClick(book)}
              style={{ flex: 1, padding: "5px 0", fontSize: "0.7rem", borderRadius: "5px", border: "1px solid #ccc", background: "#f8f8f8", cursor: "pointer", fontWeight: "600" }}
            >
              詳細
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onAdd(book); }}
              style={{ flex: 1, padding: "5px 0", fontSize: "0.7rem", borderRadius: "5px", border: "1px solid #99c", background: "#ddf", cursor: "pointer", fontWeight: "600" }}
            >
              ✋追加
            </button>
          </div>
        </div>
      )}

      {/* ── 背表紙本体 ── */}
      <div
        onClick={() => onClick(book)}
        style={{
          width: `${widthPx}px`,
          height: `${heightPx}px`,
          backgroundColor: palette.bg,
          color: palette.text,
          cursor: "pointer",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 0",
          position: "relative",
          borderLeft: `2px solid ${palette.accent}`,
          borderRight: `1px solid rgba(255,255,255,0.08)`,
          borderTop: `3px solid ${palette.accent}`,
          borderBottom: `2px solid rgba(0,0,0,0.4)`,
          boxShadow: hovered
            ? `4px 0 20px rgba(0,0,0,0.5), -2px 0 8px rgba(0,0,0,0.2)`
            : `2px 0 6px rgba(0,0,0,0.3)`,
          transform: hovered ? "translateY(-10px) scaleX(1.06)" : "translateY(0) scaleX(1)",
          transition: "all 0.22s cubic-bezier(0.34, 1.56, 0.64, 1)",
        }}
      >
        {/* アクセントライン */}
        <div style={{
          position: "absolute",
          top: 0, left: 0, right: 0,
          height: "3px",
          background: `linear-gradient(90deg, ${palette.accent}, transparent)`,
        }} />

        {/* 縦書きタイトル */}
        <div style={{
          writingMode: "vertical-rl",
          textOrientation: "mixed",
          fontSize,
          fontFamily: "'Noto Serif JP', 'Yu Mincho', 'HiraMinProN-W3', serif",
          fontWeight: "600",
          lineHeight: "1.1",
          letterSpacing: "0.05em",
          overflow: "hidden",
          flex: 1,
          display: "flex",
          alignItems: "center",
          padding: "4px 2px",
          wordBreak: "break-all",
          maxHeight: `${heightPx - 40}px`,
        }}>
          {book.title}
        </div>

        {/* 著者名（幅に余裕があれば） */}
        {widthPx >= 28 && (
          <div style={{
            writingMode: "vertical-rl",
            fontSize: "0.5rem",
            color: palette.accent,
            opacity: 0.85,
            overflow: "hidden",
            maxHeight: "60px",
            whiteSpace: "nowrap",
            padding: "0 2px",
            letterSpacing: "0.02em",
          }}>
            {book.authors?.[0]?.split(" ")[0] || ""}
          </div>
        )}
      </div>

      {/* アニメーション定義 */}
      <style>{`
        @keyframes popIn {
          from { opacity: 0; transform: translateX(-50%) scale(0.88) translateY(6px); }
          to   { opacity: 1; transform: translateX(-50%) scale(1)    translateY(0);   }
        }
      `}</style>
    </div>
  );
}

// ─── グリッドカード ───
function GridCard({ book, onDetail, onAdd }) {
  return (
    <div style={cardStyle}>
      <div style={coverContainerStyle}>
        {book.cover ? (
          <img src={book.cover} alt={book.title} referrerPolicy="no-referrer" style={coverImageStyle} />
        ) : (
          <div style={noImageStyle}>No Image</div>
        )}
      </div>
      <h3 style={titleStyle}>{book.title}</h3>
      <p style={authorStyle}>{book.authors?.join(", ")}</p>
      <div style={{ marginTop: "auto", paddingTop: "10px" }}>
        <button onClick={() => onDetail(book)} style={detailButtonStyle}>詳細</button>
        <button onClick={() => onAdd(book)} style={addButtonStyle}>📚 追加</button>
      </div>
    </div>
  );
}

// ─── メイン ───
function Search() {
  const [query, setQuery] = useState("");
  const [books, setBooks] = useState([]);
  const { myHand, setMyHand } = useContext(MyHandContext);
  const [loading, setLoading] = useState(false);
  const [selectedBook, setSelectedBook] = useState(null);
  const [viewMode, setViewMode] = useState("grid"); // "grid" | "shelf"
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const perPage = 20;

  const searchBooks = async (p) => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await axios.get(
        `http://localhost:8000/search?q=${query}&page=${p}&per_page=${perPage}`
      );
      const data = res.data;
      const validBooks = (data.books || []).filter((b) => b.isbn);
      setBooks(validBooks);
      setPage(p);
      setTotalPages(data.total_pages || 1);
    } catch (error) {
      console.error("検索エラー：", error);
    }
    setLoading(false);
  };

  const addToHand = async (book) => {
    try {
      const bookData = {
        isbn: book.isbn,
        title: book.title,
        authors: book.authors,
        publisher: book.publisher,
        published_year: book.published_year,
        cover: book.cover,
        ndc_full: book.ndc?.ndc_full || "",
        height_mm: book.height_mm,
        pages: book.pages,
        size_label: book.size_label,
      };

      const res = await axios.post("http://localhost:8000/books/add_to_hand", bookData);
      
      if (res.data.status === "already exists") {
        alert("既に追加されています。");
        return;
      }
      setMyHand([...myHand, bookData]);

      alert(`✋『${book.title}』を手元に追加しました！`);
    } catch (error) {
      console.error("追加エラー：", error);
      alert("追加に失敗しました");
    }
  };

  return (
      <div style={{ paddingTop: "80px" }}>
        {/* 検索バー + 表示切替 */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px", flexWrap: "wrap" }}>
          <input
            type="text"
            placeholder="書名で検索..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && searchBooks(1)}
            style={{ padding: "8px 12px", width: "250px", borderRadius: "5px", border: "1px solid #ccc", fontSize: "0.95rem" }}
          />
          <button
            onClick={() => searchBooks(1)}
            style={{ padding: "8px 16px", borderRadius: "5px", background: "#333", color: "#fff", border: "none", cursor: "pointer" }}
          >
            検索
          </button>

          {books.length > 0 && (
            <div style={{ marginLeft: "auto", display: "flex", gap: "6px" }}>
              <button
                onClick={() => setViewMode("grid")}
                style={{ ...toggleBtnBase, background: viewMode === "grid" ? "#333" : "#fff", color: viewMode === "grid" ? "#fff" : "#333" }}
              >
                一覧
              </button>
              <button
                onClick={() => setViewMode("shelf")}
                style={{ ...toggleBtnBase, background: viewMode === "shelf" ? "#333" : "#fff", color: viewMode === "shelf" ? "#fff" : "#333" }}
              >
                本棚
              </button>
            </div>
          )}
        </div>

        {/* 詳細モーダル */}
        {selectedBook && (
          <div style={modalOverlayStyle} onClick={() => setSelectedBook(null)}>
            <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
              <div style={{ display: "flex", gap: "20px", flexWrap: "wrap" }}>
                <div style={{ flex: "0 0 150px" }}>
                  <img
                    src={selectedBook.cover || "/no-image.png"}
                    alt={selectedBook.title}
                    referrerPolicy="no-referrer"
                    style={{ width: "100%", borderRadius: "8px", boxShadow: "0 4px 8px rgba(0,0,0,0.1)" }}
                  />
                </div>
                <div style={{ flex: "1", minWidth: "250px", textAlign: "left" }}>
                  <h2 style={{ fontSize: "1.2rem", marginBottom: "10px" }}>{selectedBook.title}</h2>
                  <p><strong>👤 著者:</strong> {selectedBook.authors?.join(", ") || "不明"}</p>
                  <p><strong>🏢 出版社:</strong> {selectedBook.publisher || "不明"}</p>
                  <p><strong>📅 出版年:</strong> {selectedBook.published_year || "不明"}</p>
                  <hr />
                  <p><strong>🔢 ISBN:</strong> {selectedBook.isbn}</p>
                  <p><strong>🗂️ 分類 (NDC):</strong> {selectedBook.ndc?.ndc_full || "未分類"}</p>
                  <div style={{ background: "#f9f9f9", padding: "10px", borderRadius: "8px", marginTop: "10px" }}>
                    <h4 style={{ margin: "0 0 5px 0", fontSize: "0.9rem", color: "#666" }}>📏 物理フォーマット</h4>
                    <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "0.9rem" }}>
                      <li>高さ: {selectedBook.height_mm ? `${selectedBook.height_mm} mm` : "不明"}</li>
                      <li>ページ数: {selectedBook.pages ? `${selectedBook.pages} p` : "不明"}</li>
                      {selectedBook.size_label && <li>判型: {selectedBook.size_label}</li>}
                    </ul>
                  </div>
                </div>
              </div>
              <div style={{ marginTop: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <button
                  onClick={() => { addToHand(selectedBook); setSelectedBook(null); }}
                  style={{ padding: "9px 20px", backgroundColor: "#ddf", border: "1px solid #99c", borderRadius: "7px", cursor: "pointer", fontWeight: "600" }}
                >
                  ✋手元に追加
                </button>
                <button onClick={() => setSelectedBook(null)} style={closeButtonStyle}>閉じる</button>
              </div>
            </div>
          </div>
        )}

        {/* 検索結果 */}
        {loading ? (
          <p>検索中...</p>
        ) : (
          <>
            {viewMode === "grid" && (
              <div style={gridStyle}>
                {books.map((book) => (
                  <GridCard key={book.isbn} book={book} onDetail={setSelectedBook} onAdd={addToHand} />
                ))}
              </div>
            )}

            {viewMode === "shelf" && (
              <div>
                <p style={{ fontSize: "0.75rem", color: "#888", marginBottom: "12px" }}>
                  幅＝ページ数、高さ＝本の高さ（mm）を反映しています。クリックで詳細表示。
                </p>
                <div style={shelfWrapperStyle}>
                  <div style={shelfFloorStyle}>
                    <div style={spineRowStyle}>
                      {books.map((book) => (
                        <SpineCard key={book.isbn} book={book} onClick={setSelectedBook} onAdd={addToHand} />
                      ))}
                    </div>
                  </div>
                  <div style={shelfBoardStyle} />
                </div>
              </div>
            )}

            {books.length > 0 && (
              <div style={{ marginTop: "30px", paddingBottom: "50px", textAlign: "center" }}>
                <button onClick={() => searchBooks(page - 1)} disabled={page <= 1}>前へ</button>
                <span style={{ margin: "0 15px" }}>{page} / {totalPages}</span>
                <button onClick={() => searchBooks(page + 1)} disabled={page >= totalPages}>次へ</button>
              </div>
            )}
          </>
        )}
      </div>
  );
}

// ─── スタイル ───
const toggleBtnBase = {
  padding: "7px 14px",
  borderRadius: "6px",
  border: "1px solid #ccc",
  cursor: "pointer",
  fontSize: "0.85rem",
  fontWeight: "500",
  transition: "all 0.15s",
};

const shelfWrapperStyle = {
  position: "relative",
  marginBottom: "8px",
};

const shelfFloorStyle = {
  background: "linear-gradient(180deg, #f8f4ee 0%, #ede8df 100%)",
  borderRadius: "4px 4px 0 0",
  padding: "180px 16px 0 16px",
  minHeight: "260px",
  display: "flex",
  alignItems: "flex-end",
  overflowX: "auto",
  overflowY: "hidden",
  boxShadow: "inset 0 10px 20px rgba(0,0,0,0.04)",
};

const spineRowStyle = {
  display: "flex",
  alignItems: "flex-end",
  gap: "2px",
};

const shelfBoardStyle = {
  height: "18px",
  background: "linear-gradient(180deg, #c8a96e 0%, #a07840 40%, #8b6530 100%)",
  borderRadius: "0 0 3px 3px",
  boxShadow: "0 4px 8px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.3)",
};

const gridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
  gap: "25px",
  width: "100%",
};

const cardStyle = {
  border: "1px solid #ddd",
  borderRadius: "12px",
  padding: "15px",
  textAlign: "center",
  display: "flex",
  flexDirection: "column",
  backgroundColor: "#fff",
  boxShadow: "0 2px 8px rgba(0,0,0,0.05)",
  transition: "transform 0.2s",
};

const coverContainerStyle = {
  width: "100%",
  height: "180px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  marginBottom: "12px",
  overflow: "hidden",
};

const coverImageStyle = {
  maxHeight: "100%",
  maxWidth: "100%",
  objectFit: "contain",
  borderRadius: "4px",
  boxShadow: "0 2px 5px rgba(0,0,0,0.15)",
};

const noImageStyle = {
  width: "120px",
  height: "160px",
  backgroundColor: "#f0f0f0",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#999",
  fontSize: "0.8rem",
  borderRadius: "4px",
  border: "1px solid #eee",
};

const titleStyle = {
  fontSize: "0.9rem",
  margin: "0 0 8px 0",
  display: "-webkit-box",
  WebkitLineClamp: "2",
  WebkitBoxOrient: "vertical",
  overflow: "hidden",
  height: "2.7rem",
  lineHeight: "1.35rem",
};

const authorStyle = {
  fontSize: "0.75rem",
  color: "#666",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const modalOverlayStyle = {
  position: "fixed", top: 0, left: 0,
  width: "100%", height: "100%",
  backgroundColor: "rgba(0,0,0,0.6)",
  display: "flex", justifyContent: "center", alignItems: "center",
  zIndex: 1000, padding: "20px",
};

const modalContentStyle = {
  backgroundColor: "#fff",
  padding: "30px",
  borderRadius: "15px",
  maxWidth: "600px",
  width: "100%",
  maxHeight: "90vh",
  overflowY: "auto",
};

const detailButtonStyle = {
  marginRight: "6px", padding: "5px 10px",
  borderRadius: "5px", border: "1px solid #ccc",
  background: "#fff", cursor: "pointer", fontSize: "0.8rem",
};

const addButtonStyle = {
  padding: "5px 10px", borderRadius: "5px",
  backgroundColor: "#ddf", border: "1px solid #99c",
  cursor: "pointer", fontSize: "0.8rem",
};

const closeButtonStyle = {
  padding: "8px 20px",
  backgroundColor: "#333", color: "#fff",
  border: "none", borderRadius: "5px", cursor: "pointer",
};

export default Search;