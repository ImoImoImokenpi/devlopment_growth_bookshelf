import { useState, useEffect, useLayoutEffect, useRef, useContext } from "react";
import axios from "axios";
import { MyHandContext } from "../context/MyHandContext";

const API           = "http://localhost:8000";
const SHELF_PAD     = 8;
const MAX_SPINE_H   = 230;
const WALL_W        = 20;

function resolveSpineHeight(book) {
  return Math.min(1000, Math.max(10, book.height_mm * 1.2));
}
function resolveSpineWidth(book) {
  const fromPages = book?.pages ? Math.min(100, Math.max(1, book.pages * 0.08)) : 20;
  return fromPages;
}

// 棚の幅に収まる単位でグループ化
function chunkByWidth(books, maxW) {
  const shelves = [];
  let cur = [], used = SHELF_PAD * 2;
  for (const b of books) {
    const w = resolveSpineWidth(b);
    if (used + w > maxW && cur.length > 0) {
      shelves.push(cur);
      cur = [b]; used = SHELF_PAD * 2 + w;
    } else {
      cur.push(b); used += w;
    }
  }
  if (cur.length > 0) shelves.push(cur);
  return shelves;
}

// 背表紙カラーパレット（画像なしの本用）
const PALETTES = [
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
];
function hashCode(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}
function getPalette(isbn) {
  return PALETTES[hashCode(isbn || "") % PALETTES.length];
}

// ── 1冊分の背表紙 ───────────────────────────────────
function SpineBook({ book, onClick, scale = 1 }) {
  const sw  = resolveSpineWidth(book) * scale;
  const sh  = resolveSpineHeight(book) * scale;
  const src = book.spine_image || book.cover || null;
  const pal = getPalette(book.isbn);

  return (
    <div
      className="spine-book"
      style={{
        width:      `${sw}px`,
        height:     `${sh}px`,
        position:   "relative",
        overflow:   "hidden",
        flexShrink: 0,
        cursor:     "pointer",
        borderRadius: "2px 2px 0 0",
        filter:     "drop-shadow(2px 4px 4px rgba(0,0,0,0.55))",
        transition: "transform 0.18s ease, filter 0.18s ease",
        backgroundColor: src ? undefined : pal.bg,
      }}
      onClick={onClick}
      title={book.title}
    >
      {src ? (
        <img
          src={src}
          alt={book.title}
          style={{
            position:  "absolute",
            width:     `${sh}px`,
            height:    `${sw}px`,
            objectFit: "fill",
            top: "50%", left: "50%",
            transform: "translate(-50%, -50%) rotate(90deg)",
          }}
        />
      ) : (
        <>
          <div style={{ position:"absolute", top:0, left:0, right:0, height:"3px", backgroundColor:pal.accent, opacity:0.7 }} />
          <div style={{ position:"absolute", bottom:0, left:0, right:0, height:"3px", backgroundColor:pal.accent, opacity:0.7 }} />
          <div style={{
            position: "absolute", inset: "6px 2px",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span style={{
              color: pal.text, fontSize: "9px", writingMode: "vertical-rl",
              fontFamily: "serif", fontWeight: "600",
              overflow: "hidden", maxHeight: `${sh - 16}px`,
              textAlign: "center",
            }}>
              {book.title}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

// ── メイン ──────────────────────────────────────────
export default function Gallery() {
  const { myHand, setMyHand } = useContext(MyHandContext);
  const [books,      setBooks]      = useState([]);
  const [selected,   setSelected]   = useState(null);
  const [shelfWidth, setShelfWidth] = useState(window.innerWidth - WALL_W * 2);
  const [adding,     setAdding]     = useState(false);
  const bookcaseRef = useRef(null);

  const addedIsbns = new Set(myHand.map(b => b.isbn));

  const handleAddToHand = async (book) => {
    if (adding || addedIsbns.has(book.isbn)) return;
    setAdding(true);
    try {
      await axios.post(`${API}/books/add_to_hand`, { isbn: book.isbn });
      setMyHand(prev => [...prev, {
        isbn:           book.isbn,
        title:          book.title,
        authors:        book.authors,
        cover:          book.cover,
        spine_image:    book.spine_image,
        height_mm:      book.height_mm,
        pages:          book.pages,
        size_label:     book.size_label,
      }]);
    } catch {
    } finally {
      setAdding(false);
    }
  };

  useEffect(() => {
    axios.get(`${API}/register/list`)
      .then(res => setBooks(res.data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const update = () => {
      if (bookcaseRef.current)
        setShelfWidth(bookcaseRef.current.clientWidth - WALL_W * 2);
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  // books ロード後に bookcase が DOM に現れるので正確な幅を再測定する
  useLayoutEffect(() => {
    if (bookcaseRef.current)
      setShelfWidth(bookcaseRef.current.clientWidth - WALL_W * 2);
  }, [books.length]);

  const shelves   = chunkByWidth(books, shelfWidth);
  const handBooks = books.filter(b => addedIsbns.has(b.isbn));

  return (
    <div style={s.page}>
      <style>{`
        .spine-book:hover {
          transform: translateY(-14px) !important;
          filter: drop-shadow(2px 12px 8px rgba(0,0,0,0.75)) !important;
          z-index: 10;
        }
      `}</style>

      <h2 style={s.heading}>Gallery</h2>

      <div style={s.bookcase} ref={bookcaseRef}>
        {books.length === 0 ? (
          <p style={s.empty}>登録された本がありません。「登録」ページから背表紙を登録してください。</p>
        ) : (
          <>
            <div style={s.topBoard} />
            <div style={s.frame}>
              <div style={s.leftWall} />
              <div style={{ flex: 1, minWidth: 0 }}>
                {shelves.map((shelf, si) => {
                  const availW = shelfWidth - SHELF_PAD * 2;
                  const totalW = shelf.reduce((sum, b) => sum + resolveSpineWidth(b), 0);
                  const scale  = totalW > availW ? availW / totalW : 1;
                  return (
                    <div key={si}>
                      <div style={{ ...s.shelfArea, minHeight: `${Math.ceil(MAX_SPINE_H * scale) + SHELF_PAD}px` }}>
                        {shelf.map((b) => (
                          <SpineBook key={b.isbn} book={b} onClick={() => setSelected(b)} scale={scale} />
                        ))}
                      </div>
                      <div style={s.board} />
                    </div>
                  );
                })}
              </div>
              <div style={s.rightWall} />
            </div>
            <div style={s.bottomBoard} />
          </>
        )}
      </div>

      {/* ── ライトボックス ── */}
      {selected && (
        <div style={s.overlay} onClick={() => setSelected(null)}>
          <div style={s.lightboxCard} onClick={(e) => e.stopPropagation()}>
            <img
              src={`${API}/register/cover/${selected.isbn}`}
              alt={selected.title}
              style={s.lightboxImg}
              onError={(e) => {
                e.target.onerror = null;
                const fallback = selected.spine_image || "";
                if (fallback) { e.target.src = fallback; }
                else { e.target.style.display = "none"; }
              }}
            />
            <div style={s.lightboxInfo}>
              <div style={s.lightboxTitle}>{selected.title}</div>
              {selected.authors?.length > 0 && (
                <div style={s.lightboxMeta}>{selected.authors.join(", ")}</div>
              )}
              {selected.publisher && (
                <div style={s.lightboxMeta}>
                  {selected.publisher}{selected.published_year ? ` (${selected.published_year})` : ""}
                </div>
              )}
              {selected.description && (
                <p style={s.lightboxDesc}>{selected.description}</p>
              )}
              <div style={s.lightboxDim}>
                {selected.height_mm && `${selected.height_mm} mm`}
                {selected.height_mm && selected.pages && " · "}
                {selected.pages && `${selected.pages} ページ`}
              </div>
              <div style={s.lightboxIsbn}>ISBN: {selected.isbn}</div>
              {selected.spine_color && (
                <div style={s.colorRow}>
                  <div style={{ ...s.colorSwatch, backgroundColor: `rgb(${selected.spine_color})` }} />
                  <span style={s.colorLabel}>代表色 rgb({selected.spine_color})</span>
                </div>
              )}
              <button
                style={{
                  ...s.addBtn,
                  ...(addedIsbns.has(selected.isbn) ? s.addBtnDone : {}),
                  ...(adding ? s.addBtnDisabled : {}),
                }}
                onClick={() => handleAddToHand(selected)}
                disabled={adding || addedIsbns.has(selected.isbn)}
              >
                {addedIsbns.has(selected.isbn) ? "手元に追加済み ✓" : adding ? "追加中…" : "手元に追加"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const s = {
  page: {
    paddingTop: "70px",
    margin: 0,
    minHeight: "100vh",
    position: "relative",
    backgroundColor: "#fff",
  },
  heading: {
    position: "fixed",
    top: "72px",
    left: "40px",
    zIndex: 100,
    fontSize: "22px",
    fontWeight: "700",
    color: "#e8d5a3",
    fontFamily: "serif",
    letterSpacing: "0.08em",
    textShadow: "0 2px 10px rgba(0,0,0,0.9)",
    pointerEvents: "none",
  },
  empty: {
    color: "#a08060",
    fontSize: "14px",
    padding: "80px 40px",
  },
  bookcase: {
    width: "100%",
    overflow: "hidden",
  },
  topBoard: {
    height: "20px",
    backgroundImage: "url('/sources/wood_texture.jpg')",
    backgroundSize: "300px 300px",
    backgroundColor: "#7a4a25",
    boxShadow: "inset 0 -3px 6px rgba(0,0,0,0.3)",
  },
  frame: {
    display: "flex",
    flexDirection: "row",
  },
  leftWall: {
    width: `${WALL_W}px`,
    flexShrink: 0,
    backgroundImage: "url('/sources/wood_texture.jpg')",
    backgroundSize: "300px 300px",
    backgroundColor: "#7a4a25",
    boxShadow: "inset -3px 0 8px rgba(0,0,0,0.4)",
  },
  rightWall: {
    width: `${WALL_W}px`,
    flexShrink: 0,
    backgroundImage: "url('/sources/wood_texture.jpg')",
    backgroundSize: "300px 300px",
    backgroundColor: "#7a4a25",
    boxShadow: "inset 3px 0 8px rgba(0,0,0,0.4)",
  },
  bottomBoard: {
    height: "20px",
    backgroundImage: "url('/sources/wood_texture.jpg')",
    backgroundSize: "300px 300px",
    backgroundColor: "#7a4a25",
    boxShadow: "inset 0 3px 6px rgba(0,0,0,0.3)",
  },
  shelfArea: {
    display: "flex",
    flexDirection: "row",
    alignItems: "flex-end",
    gap: "0",
    padding: `${SHELF_PAD}px 8px 0`,
    minHeight: `${MAX_SPINE_H + SHELF_PAD}px`,
    backgroundImage: "url('/sources/dark_wood_texture.jpg')",
    backgroundSize: "500px 500px",
    backgroundColor: "#120b03",
    overflowX: "visible",
  },
  board: {
    height: "20px",
    backgroundImage: "url('/sources/wood_texture.jpg')",
    backgroundSize: "300px 300px",
    backgroundColor: "#7a4a25",
    boxShadow: "inset 0 3px 5px rgba(255,255,255,0.08), 0 6px 10px rgba(0,0,0,0.45)",
  },
  overlay: {
    position: "fixed", inset: 0,
    backgroundColor: "rgba(0,0,0,0.85)",
    display: "flex", justifyContent: "center", alignItems: "center",
    zIndex: 2000, cursor: "zoom-out",
  },
  lightboxCard: {
    display: "flex", gap: "24px", alignItems: "flex-start",
    backgroundColor: "#fff", borderRadius: "14px", padding: "24px",
    maxWidth: "560px", width: "90vw",
    cursor: "default", boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
  },
  lightboxImg: {
    width: "120px", flexShrink: 0,
    objectFit: "contain", borderRadius: "4px", border: "1px solid #eee",
  },
  lightboxInfo: { flex: 1 },
  lightboxTitle: {
    fontSize: "18px", fontWeight: "700", color: "#2a1f0e",
    fontFamily: "serif", marginBottom: "10px", lineHeight: "1.4",
  },
  lightboxMeta: { fontSize: "13px", color: "#666", marginBottom: "4px" },
  lightboxDesc: {
    fontSize: "12px", color: "#555", lineHeight: "1.7",
    marginTop: "10px", marginBottom: "4px",
    borderTop: "1px solid #f0ebe0", paddingTop: "10px",
    maxHeight: "120px", overflowY: "auto",
  },
  lightboxDim:  { fontSize: "12px", color: "#aaa", marginTop: "8px" },
  lightboxIsbn: { fontSize: "11px", color: "#bbb", marginTop: "6px", fontFamily: "monospace" },
  colorRow: {
    display: "flex", alignItems: "center", gap: "8px", marginTop: "8px",
  },
  colorSwatch: {
    width: "18px", height: "18px", borderRadius: "4px",
    border: "1px solid rgba(0,0,0,0.12)", flexShrink: 0,
  },
  colorLabel: { fontSize: "11px", color: "#bbb", fontFamily: "monospace" },
  addBtn: {
    marginTop: "16px", width: "100%", padding: "10px",
    backgroundColor: "#c9a84c", color: "#fff",
    border: "none", borderRadius: "8px",
    fontSize: "13px", fontWeight: "700", cursor: "pointer",
  },
  addBtnDone: {
    backgroundColor: "#e8f5e9", color: "#2e7d32", cursor: "default",
  },
  addBtnDisabled: {
    opacity: 0.6, cursor: "not-allowed",
  },
};
