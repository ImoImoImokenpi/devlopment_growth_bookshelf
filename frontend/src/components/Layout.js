import React from "react";
import AppNavbar, { NAV_H } from "./AppNavbar";

// メイン画面群（育つ本棚・ギャラリー・本を探す ほか）の共通の殻。
// 上部にナビバーを置き、その下に各画面を出す。
// fill=true の画面（育つ本棚）は画面の残りの高さぴったりに収め、
// スクロールは画面側（本棚ペイン）で行う。
const Layout = ({ children, fill = false }) => {
  return (
    <div style={pageStyle}>
      <AppNavbar />
      {fill ? (
        <div style={fillStyle}>{children}</div>
      ) : (
        <main style={mainContentStyle}>{children}</main>
      )}
    </div>
  );
};

const pageStyle = {
  position: "relative",
  minHeight: "100vh",
  background: "#fdfcf8",
};

const fillStyle = {
  height: `calc(100vh - ${NAV_H}px)`,
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

// 3画面（育つ本棚・ギャラリー・本を探す）で枠をそろえる。
// どれも画面幅いっぱいを使い、左右の余白はナビバーと同じ32px、
// 見出し(PageHeader)は上から20pxの同じ位置に出す（育つ本棚は Home.js 側で同じ値を使う）。
export const PAGE_PAD_X = 32;
export const PAGE_PAD_TOP = 20;

const mainContentStyle = {
  width: "100%",
  padding: `${PAGE_PAD_TOP}px ${PAGE_PAD_X}px 48px`,
  boxSizing: "border-box",
};

export default Layout;
