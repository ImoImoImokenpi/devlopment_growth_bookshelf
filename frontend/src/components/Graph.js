import React, { useContext } from "react";
import { MyBookshelfContext } from "../context/MyBookshelfContext";

function GraphView() {
  const { myBookshelf } = useContext(MyBookshelfContext);

  if (myBookshelf.length === 0) {
    return <p>本棚に本がありません。</p>;
  }

  // 1️⃣ 行列サイズを自動計算
  const rows = Math.max(...myBookshelf.map((b) => b.row)) + 1;
  const cols = Math.max(...myBookshelf.map((b) => b.col)) + 1;

  // 2️⃣ 空マトリクス作成
  const matrix = Array.from({ length: rows }, () => Array(cols).fill(null));
  myBookshelf.forEach((b) => {
    if (b.row !== null && b.col !== null) {
      matrix[b.row][b.col] = b;
    }
  });

  return (
    <div style={{ display: "inline-block", padding: "20px" }}>
      {matrix.map((row, rIdx) => (
        <div
          key={rIdx}
          style={{ display: "flex", gap: "10px", marginBottom: "10px" }}
        >
          {row.map((book, cIdx) => (
            <div
              key={cIdx}
              style={{
                width: "80px",
                height: "120px",
                border: "1px solid #ccc",
                borderRadius: "5px",
                background: "#f9f9f9",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                overflow: "hidden",
              }}
            >
              {book ? (
                <img
                  src={book.cover}
                  alt={book.title}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  onError={(e) => (e.target.style.display = "none")}
                />
              ) : (
                <span style={{ fontSize: "10px", color: "#999" }}>空</span>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export default GraphView;
