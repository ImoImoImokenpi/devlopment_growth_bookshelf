import React from "react";
import Navbar from "./Navbar";

const Layout = ({ children }) => {
  return (
    <div
      style={{ position: "relative", height: "10000vh", overflow: "visible" }}
    >
      <Navbar />
      {/* メインコンテンツ */}
      <main style={mainContentStyle}>
        {children}
      </main>
    </div>
  );
}

// Layout.js 内のスタイル
const mainContentStyle = {
  width: "100%",
  maxWidth: "1400px", // 少し広げることで本棚の並びをゆったりさせる
  margin: "0 auto",
  padding: "20px", // 左右の余白をしっかり取る
  boxSizing: "border-box",
};

export default Layout;
