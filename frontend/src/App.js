import React, { useState, useEffect } from "react";
import axios from "axios";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import { MyHandProvider } from "./context/MyHandContext";
import { MyBookshelfProvider } from "./context/MyBookshelfContext";

import Home from "./pages/Home";
import Gallery from "./pages/Gallery";
import Register from "./pages/Register";
import Search from "./pages/Search";
import KnowledgeGraph from "./pages/KnowledgeGraph";
import Layout from "./components/Layout";

function App() {
  return (
    <MyHandProvider>
      <MyBookshelfProvider>
        <Router>
          <Layout>
            <Routes>
              <Route path="/" element={<Home />} />
              {/* <Route path="/Search" element={<Search />} /> */}
              <Route path="/Gallery" element={<Gallery />} />
              <Route path="/Register" element={<Register />} />
              <Route path="/KnowledgeGraph" element={<KnowledgeGraph />} />
            </Routes>
          </Layout>
        </Router>
      </MyBookshelfProvider>
    </MyHandProvider>
  );
}

export default App;
