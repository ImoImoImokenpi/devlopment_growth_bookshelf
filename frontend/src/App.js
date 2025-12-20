import React, { useState, useEffect } from "react";
import axios from "axios";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import { MyHandProvider } from "./context/MyHandContext";
import { MyBookshelfProvider } from "./context/MyBookshelfContext";

import Home from "./pages/Home";
import Search from "./pages/Search";
import KnowledgeGraph from "./pages/KnowledgeGraph";
import Navbar from "./components/Navbar";

function App() {
  return (
    <MyHandProvider>
      <MyBookshelfProvider>
        <Router>
          <Navbar/>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/Search" element={<Search />} />
            <Route path="/KnowledgeGraph" element={<KnowledgeGraph />} />
          </Routes>
        </Router>
      </MyBookshelfProvider>
    </MyHandProvider>
  );
}

export default App;
