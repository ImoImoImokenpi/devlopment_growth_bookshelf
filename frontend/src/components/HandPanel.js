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
      alert(error.response?.status === 404 ? "本が見つかりませんでした。" : "削除に失敗しました");
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

      if (skipped?.length > 0) {
        alert(`${skipped.length}冊は追加できませんでした`);
      }
    } catch (error) {
      console.error("一括追加エラー：", error);
      alert("一括追加に失敗しました");
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
          background: isOpen ? "rgba(0,0,0,0.4)" : "transparent",
          pointerEvents: isOpen ? "auto" : "none",
          transition: "background 0.3s ease",
          zIndex: 99998,
        }}
      />

      {/* パネル本体 */}
      <div style={{
        position: "fixed", top: 0, right: 0,
        width: "480px", height: "100%",
        background: "#fdfdfd",
        boxShadow: "-5px 0 20px rgba(0,0,0,0.15)",
        transform: isOpen ? "translateX(0)" : "translateX(100%)",
        transition: "transform 0.35s cubic-bezier(0.4,0,0.2,1)",
        zIndex: 99999,
        display: "flex", flexDirection: "column",
      }}>

        {/* ヘッダー */}
        <div style={{
          padding: "22px 28px", borderBottom: "1px solid #eee",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <h3 style={{ margin: 0, fontSize: "1.1rem" }}>📖 手元一覧</h3>
          <button onClick={onClose} style={{
            fontSize: "20px", background: "none", border: "none",
            cursor: "pointer", color: "#999", lineHeight: 1,
          }}>✕</button>
        </div>

        {/* 一括操作バー */}
        {selectedIds.length > 0 && (
          <div style={{
            padding: "10px 16px", background: "#333", color: "#fff",
            display: "flex", justifyContent: "space-between", alignItems: "center",
            fontSize: "13px",
          }}>
            <span>{selectedIds.length}冊選択中</span>
            <button onClick={addSelectedBooks} style={{
              padding: "5px 14px", borderRadius: "20px", border: "none",
              background: "#ff9900", color: "#fff", fontWeight: "700",
              cursor: "pointer", fontSize: "12px",
            }}>
              + まとめて本棚へ
            </button>
          </div>
        )}

        {/* 本リスト */}
        <div style={{ overflowY: "auto", flex: 1, padding: "16px 20px" }}>
          {myHand.length === 0 ? (
            <p style={{ padding: "20px", color: "#aaa", textAlign: "center" }}>
              まだ手元に本がありません。
            </p>
          ) : (
            myHand.map((b) => {
              const checked = selectedIds.includes(b.isbn);
              const { heightPx, widthPx } = getSpineDimensions(b);
              return (
                <div
                  key={b.isbn}
                  onClick={() => toggleSelect(b.isbn)}
                  style={{
                    display: "flex", gap: "16px", padding: "16px",
                    marginBottom: "12px", borderRadius: "12px", cursor: "pointer",
                    background: checked ? "#f0f7ff" : "#fff",
                    border: `1px solid ${checked ? "#99b8dd" : "#ebebeb"}`,
                    transition: "background 0.15s, border 0.15s",
                    alignItems: "flex-end",
                  }}
                >
                  {/* チェックボックス */}
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {}}
                    onClick={(e) => e.stopPropagation()}
                    style={{ marginBottom: "4px", cursor: "pointer", flexShrink: 0 }}
                  />

                  {/* 背表紙（実寸比） */}
                  <div style={{
                    width: `${widthPx}px`, height: `${heightPx}px`,
                    backgroundColor: "#3a3a5c",
                    borderLeft: "2px solid #c9a84c",
                    borderTop: "2px solid #c9a84c",
                    boxShadow: "2px 2px 6px rgba(0,0,0,0.25)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    flexShrink: 0, overflow: "hidden",
                  }}>
                    <span style={{
                      writingMode: "vertical-rl", color: "#e8d5a3",
                      fontSize: "8px", overflow: "hidden",
                      whiteSpace: "nowrap", letterSpacing: "1px",
                      maxHeight: `${heightPx - 8}px`,
                      fontFamily: "'Noto Serif JP', serif",
                    }}>
                      {b.title}
                    </span>
                  </div>

                  {/* 表紙画像 */}
                  <div style={{
                    width: "70px", height: "100px", flexShrink: 0,
                    borderRadius: "4px", overflow: "hidden",
                    background: "#eee",
                    boxShadow: "0 2px 6px rgba(0,0,0,0.12)",
                  }}>
                    {b.cover ? (
                      <img
                        src={b.cover} alt={b.title}
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        referrerPolicy="no-referrer"
                        onError={(e) => (e.target.style.display = "none")}
                      />
                    ) : (
                      <div style={{
                        height: "100%", display: "flex", alignItems: "center",
                        justifyContent: "center", fontSize: "9px", color: "#aaa",
                      }}>
                        No Image
                      </div>
                    )}
                  </div>

                  {/* テキスト情報 */}
                  <div style={{
                    flex: 1, display: "flex", flexDirection: "column",
                    justifyContent: "space-between", minWidth: 0,
                    height: "100px",
                  }}>
                    <div>
                      <div style={{
                        fontSize: "14px", fontWeight: "700", lineHeight: "1.4",
                        marginBottom: "5px",
                        display: "-webkit-box", WebkitLineClamp: 3,
                        WebkitBoxOrient: "vertical", overflow: "hidden",
                      }}>
                        {b.title}
                      </div>
                      <div style={{ fontSize: "12px", color: "#888" }}>
                        {Array.isArray(b.authors) ? b.authors.join(", ") : b.authors}
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeFromHand(b.isbn); }}
                      style={{
                        alignSelf: "flex-start", border: "none", background: "none",
                        color: "#c66", fontSize: "12px", cursor: "pointer",
                        padding: 0, textDecoration: "underline",
                      }}
                    >
                      🗑 削除
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