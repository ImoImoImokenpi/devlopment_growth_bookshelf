import React, { useContext, useState } from "react";
import axios from "axios";
import { MyHandContext } from "../context/MyHandContext";
import { MyBookshelfContext } from "../context/MyBookshelfContext";

function HandPanel({ isOpen, onClose }) {
  const { myHand, setMyHand } = useContext(MyHandContext);
  const { myBookshelf, fetchBookshelf } = useContext(MyBookshelfContext);
  const [selectedIds, setSelectedIds] = useState([]);

  // 手元から削除する処理
  const removeFromHand = async (bookIsbn) => {
    try {
      const res = await axios.delete(
        `http://localhost:8000/books/remove_from_hand/${bookIsbn}`
      );

      setMyHand((prev) => prev.filter((b) => b.isbn !== bookIsbn));
      alert("本を手元から削除しました。");
    } catch (error) {
      console.error("削除エラー：", error);
      if (error.response?.status === 404) {
        alert("本が見つかりませんでした。");
      } else {
        alert("削除に失敗しました");
      }
    }
  };

  // チェック切り替え
  const toggleSelect = (bookIsbn) => {
    setSelectedIds((prev) =>
      prev.includes(bookIsbn)
        ? prev.filter((id) => id !== bookIsbn)
        : [...prev, bookIsbn]
    );
  };

  // まとめて追加
  const addSelectedBooks = async () => {
    if (selectedIds.length === 0) return;

    if (!window.confirm(`${selectedIds.length}冊を本棚に追加しますか？`))
      return;

    try {
      await axios.post("http://localhost:8000/books/add_from_hand", {
        isbns: selectedIds,
      });

      // ✅ 手元だけは即時更新してOK
      setMyHand((prev) => prev.filter((b) => !selectedIds.includes(b.isbn)));

      // ✅ 本棚は必ず GET で再取得
      await fetchBookshelf();

      setSelectedIds([]);
    } catch (error) {
      console.error("一括追加エラー：", error);
      alert("一括追加に失敗しました");
    }
  };

  return (
    <>
      {/* 背景 */}
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          background: isOpen ? "rgba(0,0,0,0.4)" : "transparent",
          pointerEvents: isOpen ? "auto" : "none",
          transition: "background 0.3s ease",
          zIndex: 9998,
        }}
      />

      {/* パネル */}
      <div
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          width: "350px",
          height: "100%",
          background: "#fff",
          boxShadow: "-3px 0 10px rgba(0,0,0,0.2)",
          transform: isOpen ? "translateX(0)" : "translateX(100%)",
          transition: "transform 0.35s ease",
          zIndex: 9999,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            padding: "15px",
            borderBottom: "1px solid #ddd",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <h3>📖 手元一覧</h3>
          <button
            onClick={onClose}
            style={{
              fontSize: "20px",
              background: "none",
              border: "none",
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {/* 一括操作バー */}
        {selectedIds.length > 0 && (
          <div
            style={{
              padding: "8px 12px",
              background: "#f7f7f7",
              borderBottom: "1px solid #ddd",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: "12px",
            }}
          >
            <span>{selectedIds.length}冊選択中</span>
            <button
              onClick={addSelectedBooks}
              style={{
                padding: "4px 8px",
                fontSize: "12px",
                borderRadius: "4px",
                background: "#e6f0ff",
                border: "1px solid #99b",
                cursor: "pointer",
              }}
            >
              + まとめて追加
            </button>
          </div>
        )}

        {/* 本リスト */}
        <div style={{ overflowY: "auto", flex: 1 }}>
          {myHand.length === 0 ? (
            <p style={{ padding: "20px" }}>まだ手元に本がありません。</p>
          ) : (
            myHand.map((b) => {
              const checked = selectedIds.includes(b.isbn);

              return (
                <div
                  key={b.isbn}
                  style={{
                    padding: "12px",
                    borderBottom: "1px solid #eee",
                    display: "flex",
                    gap: "12px",
                    alignItems: "flex-start",
                  }}
                >
                  {/* チェックボックス */}
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleSelect(b.isbn)}
                    style={{ marginTop: "6px" }}
                  />

                  {/* 表紙画像 */}
                  {b.cover ? (
                    <img
                      src={b.cover}
                      alt={b.title}
                      style={{
                        width: "55px",
                        height: "80px",
                        objectFit: "cover",
                        borderRadius: "5px",
                        background: "#f2f2f2",
                      }}
                      onError={(e) => (e.target.style.display = "none")}
                    />
                  ) : (
                    <div
                      style={{
                        width: "55px",
                        height: "80px",
                        backgroundColor: "#f0f0f0",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: "10px",
                        color: "#888",
                      }}
                    >
                      No Image
                    </div>
                  )}

                  {/* 本情報 */}
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontSize: "14px",
                        fontWeight: "bold",
                        marginBottom: "4px",
                      }}
                    >
                      {b.title}
                    </div>

                    <div style={{ fontSize: "12px", color: "#666" }}>
                      {b.authors}
                    </div>
                  </div>

                  {/* 削除ボタン */}
                  <button
                    onClick={() => removeFromHand(b.isbn)}
                    style={{
                      padding: "5px 8px",
                      fontSize: "12px",
                      borderRadius: "5px",
                      backgroundColor: "#fdd",
                      border: "1px solid #c99",
                      cursor: "pointer",
                      alignSelf: "center",
                    }}
                  >
                    🗑 削除
                  </button>
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
