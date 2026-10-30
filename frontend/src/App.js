import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

import { MyHandProvider } from "./context/MyHandContext";
import { MyBookshelfProvider } from "./context/MyBookshelfContext";

import Layout from "./components/Layout";
import Home from "./pages/Home";
import Gallery from "./pages/Gallery";
import Register from "./pages/Register";

// 育つ本棚の3画面。上部のナビバー(Layout)から行き来する。
//   /          育つ本棚（本棚の高さを画面に合わせるため Layout を fill で使う）
//   /Gallery   ギャラリー
//   /Register  本の登録
function App() {
  return (
    <MyHandProvider>
      <MyBookshelfProvider>
        <Router>
          <Routes>
            <Route path="/" element={<Layout fill><Home /></Layout>} />
            <Route path="/Gallery" element={<Layout><Gallery /></Layout>} />
            <Route path="/Register" element={<Layout><Register /></Layout>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </MyBookshelfProvider>
    </MyHandProvider>
  );
}

export default App;
