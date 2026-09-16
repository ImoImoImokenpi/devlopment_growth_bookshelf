// 設計書6.1の2ペイン構成。
//   メイン: 本棚ビジュアライズ（背表紙・ドラッグ&ドロップ配置）
//   サブ  : 本詳細
//
// 本棚は段を追加しても縮んでいかないよう、画面幅に対する固定割合にする
// （はみ出た分は本棚側の縦スクロールで見る）。割合そのものは「棚の調整」の
// 「本棚サイズの調整」からユーザーが変えられる（shelfWidthPct）。
//
// 右の本詳細は本を選んでいる（focusIsbn がある）ときだけ画面の30%で開き、
// 閉じている間は幅0に収納される。
import { useState } from "react";
import SpineShelfView from "../components/SpineShelfView";
import OwnBookGrid from "../components/OwnBookGrid";
import ShelfSettingsMenu from "../components/ShelfSettingsMenu";
import PageHeader from "../components/PageHeader";
import ModeToggle from "../components/ModeToggle";
import Toast from "../components/Toast";
import CompanionPanel from "../components/companion/CompanionPanel";
import GroupPanel from "../components/grouping/GroupPanel";
import IntentCheckEntry from "../components/intent/IntentCheckEntry";
import {
  ShelfWorkspaceProvider,
  useShelfWorkspace,
} from "../context/ShelfWorkspaceContext";

const NAVBAR_SPACE = 66; // 上部に固定表示されているNavbarの逃げ
const PANEL_WIDTH_PCT = 25;   // 本詳細／グループパネルが開いているときの画面幅に対する割合

function HomeWorkspace() {
  const { mode, setMode, focusIsbn, shelfWidthPct, toast, dismissToast } = useShelfWorkspace();
  const isRightPanelOpen = !!focusIsbn;
  const isGroupingMode = mode === "grouping";
  const isBoundaryMode = mode === "boundary"; // フェーズ2(b): 区切り確認モード

  // 背表紙⇄グリッドの切り替え（以前はNavbar上の別ページ「/GridShelf」だったが、
  // 右下の設定ボタン(ShelfSettingsMenu)の中に統合した）。デフォルトは背表紙表示。
  const [viewMode, setViewMode] = useState("spine");

  return (
    <div style={{ ...s.page, background: (isGroupingMode || isBoundaryMode) ? "#f5efdd" : "#f7f3ea" }}>
      {/* 「みんなの本棚」画面（BrowseLayout）と同じ PageHeader を使い、
          見出しのデザインを全ページで統一する。 */}
      <div style={s.headerRow}>
        <PageHeader
          title="My本棚"
          right={
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <IntentCheckEntry />
              <ModeToggle mode={mode} onChange={setMode} />
            </div>
          }
        />
      </div>

      {isGroupingMode && (
        <div style={s.banner}>グループ整理モード：本を選んでグループを作ったり、左のパネルで整理できます</div>
      )}
      {isBoundaryMode && (
        <div style={s.banner}>
          区切り確認モード：本と本の間をタップして、意識して区切ったところを選んでください
          <button style={s.bannerDoneBtn} onClick={() => setMode("normal")}>完了</button>
        </div>
      )}

      <div style={s.body}>
        <div style={s.grid}>
          <div style={{ ...s.panelWrap, width: isGroupingMode ? `${PANEL_WIDTH_PCT}%` : 0 }}>
            <GroupPanel />
          </div>

          <main style={{ ...s.shelfPane, flexBasis: `${shelfWidthPct}%` }}>
            {viewMode === "spine" ? (
              <SpineShelfView />
            ) : (
              <div style={s.gridWrap}>
                <OwnBookGrid />
              </div>
            )}
            {/* 背表紙⇄グリッドの切り替えは、棚と重ならないよう右下の設定ボタンの中にまとめた */}
            <ShelfSettingsMenu viewMode={viewMode} onViewModeChange={setViewMode} />
          </main>

          <div style={{ ...s.panelWrap, width: isRightPanelOpen ? `${PANEL_WIDTH_PCT}%` : 0 }}>
            <CompanionPanel />
          </div>
        </div>
      </div>

      <Toast toast={toast} onDismiss={dismissToast} />
    </div>
  );
}

export default function Home() {
  return (
    <ShelfWorkspaceProvider>
      <HomeWorkspace />
    </ShelfWorkspaceProvider>
  );
}

const s = {
  page: {
    height: "100vh", paddingTop: NAVBAR_SPACE, boxSizing: "border-box",
    display: "flex", flexDirection: "column",
    overflow: "hidden", transition: "background 200ms ease",
  },
  headerRow: { flexShrink: 0, padding: "20px 28px 12px" },
  banner: {
    flexShrink: 0, textAlign: "center", padding: "6px 12px",
    background: "#c9a84c", color: "#fff", fontSize: 12, fontWeight: 600,
    display: "flex", justifyContent: "center", alignItems: "center", gap: 12,
  },
  bannerDoneBtn: {
    padding: "3px 12px", borderRadius: 999, border: "1px solid rgba(255,255,255,0.7)",
    background: "rgba(255,255,255,0.15)", color: "#fff", fontSize: 11, fontWeight: 700,
    cursor: "pointer",
  },
  body: { flex: 1, minHeight: 0, overflow: "hidden" },
  grid: {
    display: "flex",
    justifyContent: "center",
    height: "100%",
    overflow: "hidden",
  },
  shelfPane: {
    position: "relative",
    flex: "0 0 auto", // flexBasis はインラインで shelfWidthPct に差し替える
    minWidth: 0,
    height: "100%",
    overflow: "auto",
    transition: "flex-basis 240ms ease",
  },
  gridWrap: {
    position: "relative", zIndex: 2, boxSizing: "border-box",
    padding: "24px 28px",
  },
  panelWrap: {
    flex: "0 0 auto",
    height: "100%",
    overflow: "hidden",
    transition: "width 240ms ease",
  },
};
