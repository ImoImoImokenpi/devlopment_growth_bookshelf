import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

import { MyHandProvider } from "./context/MyHandContext";
import { MyBookshelfProvider } from "./context/MyBookshelfContext";

import Layout from "./components/Layout";
import Home from "./pages/Home";
import Gallery from "./pages/Gallery";
import Search from "./pages/Search";

// 育つ本棚の3画面。上部のナビバー(Layout)から行き来する。
//   /          育つ本棚（本棚の高さを画面に合わせるため Layout を fill で使う）
//   /Gallery   ギャラリー
//   /Search    本を探す（以前の /Register「本の登録」はここへ移す）
function App() {
  return (
    <MyHandProvider>
      <MyBookshelfProvider>
        <Router>
          <Routes>
            <Route path="/" element={<Layout fill><Home /></Layout>} />
            <Route path="/Gallery" element={<Layout><Gallery /></Layout>} />
            <Route path="/Search" element={<Layout><Search /></Layout>} />
            <Route path="/Register" element={<Navigate to="/Search" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </MyBookshelfProvider>
    </MyHandProvider>
  );
}

export default App;
