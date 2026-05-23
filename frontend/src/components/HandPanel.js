import React, { useContext, useState } from "react";
import axios from "axios";
import { MyHandContext } from "../context/MyHandContext";
import { getSpineDimensions } from "../utils/spineSize";
import { MyBookshelfContext } from "../context/MyBookshelfContext";

function HandPanel({ isOpen, onClose }) {
  const { myHand, setMyHand } = useContext(MyHandContext);
  const { fetchBookshelf } = useContext(MyBookshelfContext);
  const [selectedIds, setSelectedIds] = useState([]);

  const removeFromHand = async (bookIsbn) => {
    try {
      await axios.delete(`http://localhost:8000/books/remove_from_hand/${bookIsbn}`);
      setMyHand((prev) => prev.filter((b) => b.isbn !== bookIsbn));
    } catch (error) {
      console.error("削除エラー：", error);
    }
  };

  const toggleSelect = (bookIsbn) => {
    setSelectedIds((prev) =>
      prev.includes(bookIsbn) ? prev.filter((id) => id !== bookIsbn) : [...prev, bookIsbn]
    );
  };

  const addSelectedBooks = async () => {
    if (selectedIds.length === 0) return;
    if (!window.confirm(`${selectedIds.length}冊を本棚に追加しますか？`)) return;
    try {
      const res = await axios.post("http://localhost:8000/books/add_from_hand", { isbns: selectedIds });
      const { added, skipped } = res.data;
      setMyHand((prev) => prev.filter((b) => !added.includes(b.isbn)));
      await fetchBookshelf();
      setSelectedIds([]);
      if (skipped?.length > 0) alert(`${skipped.length}冊は追加できませんでした`);
    } catch (error) {
      console.error("一括追加エラー：", error);
      setSelectedIds([]);
    }
  };

  return (
    <>
      {/* オーバーレイ */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", top: 0, left: 0, width: "100%", height: "100%",
          background: isOpen ? "rgba(0,0,0,0.35)" : "transparent",
          pointerEvents: isOpen ? "auto" : "none",
          transition: "background 0.3s ease",
          zIndex: 99998,
          backdropFilter: isOpen ? "blur(2px)" : "none",
        }}
      />

      {/* パネル本体 */}
      <div style={{
        position: "fixed", top: 0, right: 0,
        width: "400px", height: "100%",
        background: "#fdfcf8",
        boxShadow: "-8px 0 40px rgba(0,0,0,0.12)",
        transform: isOpen ? "translateX(0)" : "translateX(100%)",
        transition: "transform 0.35s cubic-bezier(0.4,0,0.2,1)",
        zIndex: 99999,
        display: "flex", flexDirection: "column",
        borderLeft: "1px solid #ede8da",
      }}>

        {/* ヘッダー */}
        <div style={{
          padding: "24px 28px 20px",
          borderBottom: "1px solid #ede8da",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div>
            <h3 style={{
              margin: 0, fontSize: "16px", fontWeight: "700",
              fontFamily: "serif", color: "#2a1f0e", letterSpacing: "0.04em",
            }}>
              手元の本
            </h3>
            {myHand.length > 0 && (
              <p style={{ margin: "3px 0 0", fontSize: "12px", color: "#aaa" }}>
                {myHand.length}冊
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              width: "32px", height: "32px", borderRadius: "50%",
              border: "1px solid #e0d8c0", background: "transparent",
              cursor: "pointer", color: "#888", fontSize: "14px",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "background 0.15s",
            }}
            onMouseEnter={e => e.currentTarget.style.background = "#f5f0e8"}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}
          >
            ✕
          </button>
        </div>

        {/* 一括操作バー */}
        {selectedIds.length > 0 && (
          <div style={{
            padding: "10px 20px",
            background: "#f5f0e8",
            borderBottom: "1px solid #ede8da",
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <span style={{ fontSize: "13px", color: "#6b5a3e", fontWeight: "600" }}>
              {selectedIds.length}冊選択中
            </span>
            <button
              onClick={addSelectedBooks}
              style={{
                padding: "6px 16px", borderRadius: "999px",
                border: "none", background: "#c9a84c", color: "#fff",
                fontWeight: "700", cursor: "pointer", fontSize: "12px",
                letterSpacing: "0.03em",
              }}
            >
              本棚へ追加
            </button>
          </div>
        )}

        {/* 本リスト */}
        <div style={{ overflowY: "auto", flex: 1, padding: "16px" }}>
          {myHand.length === 0 ? (
            <div style={{
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              height: "200px", gap: "12px", color: "#bbb",
            }}>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 11V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2"/>
                <path d="M14 10V4a2 2 0 0 0-2-2 2 2 0 0 0-2 2v2"/>
                <path d="M10 10.5V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2v8"/>
                <path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>
              </svg>
              <span style={{ fontSize: "13px" }}>手元に本がありません</span>
            </div>
          ) : (
            myHand.map((b) => {
              const checked = selectedIds.includes(b.isbn);
              const { heightPx, widthPx } = getSpineDimensions(b);
              return (
                <div
                  key={b.isbn}
                  onClick={() => toggleSelect(b.isbn)}
                  style={{
                    display: "flex", gap: "14px", padding: "14px",
                    marginBottom: "8px", borderRadius: "12px", cursor: "pointer",
                    background: checked ? "rgba(201,168,76,0.08)" : "#fff",
                    border: `1px solid ${checked ? "#c9a84c" : "#ede8da"}`,
                    transition: "background 0.15s, border-color 0.15s",
                    alignItems: "flex-start",
                  }}
                >
                  {/* チェック */}
                  <div style={{
                    width: "18px", height: "18px", borderRadius: "5px", flexShrink: 0, marginTop: "2px",
                    border: `2px solid ${checked ? "#c9a84c" : "#d0c4a8"}`,
                    background: checked ? "#c9a84c" : "transparent",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    transition: "all 0.15s",
                  }}>
                    {checked && (
                      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round">
                        <polyline points="2,6 5,9 10,3"/>
                      </svg>
                    )}
                  </div>

                  {/* 背表紙 */}
                  <div style={{
                    width: `${widthPx}px`, height: `${heightPx}px`,
                    flexShrink: 0, overflow: "hidden", position: "relative",
                    borderRadius: "2px",
                    boxShadow: "2px 3px 8px rgba(0,0,0,0.2)",
                    backgroundColor: "#3a3a5c",
                  }}>
                    {b.spine_image ? (
                      <img
                        src={b.spine_image}
                        alt={b.title}
                        style={{
                          position: "absolute",
                          width: `${heightPx}px`, height: `${widthPx}px`,
                          objectFit: "fill",
                          top: "50%", left: "50%",
                          transform: "translate(-50%, -50%) rotate(90deg)",
                        }}
                        onError={(e) => { e.target.style.display = "none"; }}
                      />
                    ) : (
                      <span style={{
                        position: "absolute", inset: 0,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        writingMode: "vertical-rl", color: "#e8d5a3",
                        fontSize: "8px", overflow: "hidden",
                        whiteSpace: "nowrap", letterSpacing: "1px",
                        fontFamily: "'Noto Serif JP', serif",
                      }}>
                        {b.title}
                      </span>
                    )}
                  </div>

                  {/* テキスト情報 */}
                  <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", justifyContent: "space-between", height: `${heightPx}px` }}>
                    <div>
                      <div style={{
                        fontSize: "13px", fontWeight: "700", lineHeight: "1.5",
                        color: "#2a1f0e", fontFamily: "serif",
                        display: "-webkit-box", WebkitLineClamp: 3,
                        WebkitBoxOrient: "vertical", overflow: "hidden",
                      }}>
                        {b.title}
                      </div>
                      {b.authors && (
                        <div style={{ fontSize: "11px", color: "#aaa", marginTop: "4px" }}>
                          {Array.isArray(b.authors) ? b.authors.join(", ") : b.authors}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeFromHand(b.isbn); }}
                      style={{
                        alignSelf: "flex-start", border: "none", background: "none",
                        color: "#ccc", cursor: "pointer", padding: "2px",
                        display: "flex", alignItems: "center",
                        transition: "color 0.15s",
                      }}
                      onMouseEnter={e => e.currentTarget.style.color = "#c9506a"}
                      onMouseLeave={e => e.currentTarget.style.color = "#ccc"}
                      title="手元から削除"
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                        <path d="M10 11v6M14 11v6"/>
                        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                      </svg>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </>
  );
}

export default HandPanel;
