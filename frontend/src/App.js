import React, { useState, useEffect } from "react";
import axios from "axios";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import { MyHandProvider } from "./context/MyHandContext";
import { MyBookshelfProvider } from "./context/MyBookshelfContext";

import Home from "./pages/Home";
import Gallery from "./pages/Gallery";
import Register from "./pages/Register";
import MyStyleAnalysis from "./pages/MyStyleAnalysis";
import StyleProjectionHistory from "./pages/StyleProjectionHistory";
import ExperimentAdmin from "./pages/ExperimentAdmin";
import BrowseLayout from "./pages/BrowseLayout";
import ParticipantGrid from "./pages/ParticipantGrid";
import ExploreShelf from "./pages/ExploreShelf";
import InterestSurvey from "./pages/InterestSurvey";
import UiabAdmin from "./pages/UiabAdmin";
import Layout from "./components/Layout";

import UiabEntry from "./pages/uiab/UiabEntry";
import UiabBuild from "./pages/uiab/UiabBuild";
import UiabSelfReport from "./pages/uiab/UiabSelfReport";
import UiabObserve from "./pages/uiab/UiabObserve";
import UiabDone from "./pages/uiab/UiabDone";

// 新旧UI比較実験(/Uiab/*)は「投影のズレ」研究の参加者導線(Navbar等)とは
// 完全に切り離し、独自のURLを直接配布する運用にする。そのためLayout（Navbar）の
// 外側に置いている。研究者向けの管理画面(UiabAdmin)だけは既存のExperimentAdminと
// 同じ扱いでLayoutの内側(Navbarからアクセス可能)にする。
function MainStudyRoutes() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/MyStyleAnalysis" element={<MyStyleAnalysis />} />
        <Route path="/Gallery" element={<Gallery />} />
        <Route path="/Register" element={<Register />} />
        <Route path="/StyleProjection" element={<StyleProjectionHistory />} />
        <Route path="/ExperimentAdmin" element={<ExperimentAdmin />} />
        <Route path="/UiabAdmin" element={<UiabAdmin />} />
        <Route path="/InterestSurvey" element={<InterestSurvey />} />
        <Route path="/Browse" element={<BrowseLayout />}>
          <Route index element={<ParticipantGrid />} />
          <Route path=":participantId" element={<ExploreShelf />} />
        </Route>
      </Routes>
    </Layout>
  );
}

function App() {
  return (
    <MyHandProvider>
      <MyBookshelfProvider>
        <Router>
          <Routes>
            <Route path="/Uiab" element={<UiabEntry />} />
            <Route path="/Uiab/Build/:period" element={<UiabBuild />} />
            <Route path="/Uiab/SelfReport/:period" element={<UiabSelfReport />} />
            <Route path="/Uiab/Observe" element={<UiabObserve />} />
            <Route path="/Uiab/Done" element={<UiabDone />} />
            <Route path="/*" element={<MainStudyRoutes />} />
          </Routes>
        </Router>
      </MyBookshelfProvider>
    </MyHandProvider>
  );
}

export default App;
