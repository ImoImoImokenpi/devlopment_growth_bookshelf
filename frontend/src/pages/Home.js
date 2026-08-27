// 設計書6.1の3ペイン構成。
//   左（サブ）  : 棚を見て気づいたこと（発見と対話）
//   中央（メイン）: 本棚ビジュアライズ（背表紙・ドラッグ&ドロップ配置）
//   右（サブ）  : 本詳細
//
// 本棚は段を追加しても縮んでいかないよう、画面幅に対する固定割合にする
// （はみ出た分は本棚側の縦スクロールで見る）。割合そのものは「棚の調整」の
// 「本棚サイズの調整」からユーザーが変えられる（shelfWidthPct）。
//
// 右の本詳細は本を選んでいる（focusIsbn がある）ときだけ画面の30%で開き、
// 閉じている間は幅0に収納される。左の「棚を見て気づいたこと」は特定の本に
// 紐づかない常設の相棒機能なので初期状態で開いているが、圧迫感が出るときの
// ためにユーザーがいつでも収納・再表示できる（isDialogueOpen）。
import { useState } from "react";
import SpineShelfView from "../components/SpineShelfView";
import OwnBookGrid from "../components/OwnBookGrid";
import ShelfSettingsMenu from "../components/ShelfSettingsMenu";
import PageHeader from "../components/PageHeader";
import CompanionPanel from "../components/companion/CompanionPanel";
import DiscoveryDialoguePanel from "../components/companion/DiscoveryDialoguePanel";
import {
  ShelfWorkspaceProvider,
  useShelfWorkspace,
} from "../context/ShelfWorkspaceContext";

const NAVBAR_SPACE = 66; // 上部に固定表示されているNavbarの逃げ
const PANEL_WIDTH_PCT = 25;   // 本詳細が開いているときの画面幅に対する割合
const DIALOGUE_WIDTH_PCT = 28; // 「棚を見て気づいたこと」が開いているときの画面幅に対する割合

function HomeWorkspace() {
  const {
    growth, focusIsbn, shelfWidthPct,
    isDialogueOpen, setIsDialogueOpen, pendingDiscoveries,
  } = useShelfWorkspace();
  const level = growth?.level ?? 0;
  const isPanelOpen = !!focusIsbn;

  // 背表紙⇄グリッドの切り替え（以前はNavbar上の別ページ「/GridShelf」だったが、
  // 右下の設定ボタン(ShelfSettingsMenu)の中に統合した）。デフォルトは背表紙表示。
  const [viewMode, setViewMode] = useState("spine");

  return (
    <div style={s.page}>
      {/* 「みんなの本棚」画面（BrowseLayout）と同じ PageHeader を使い、
          見出しのデザインを全ページで統一する。 */}
      <div style={s.headerRow}>
        <PageHeader title="My本棚" />
      </div>

      <div style={s.body}>
        <div style={s.grid}>
          <div style={{ ...s.dialogueWrap, width: isDialogueOpen ? `${DIALOGUE_WIDTH_PCT}%` : 0 }}>
            <DiscoveryDialoguePanel />
          </div>

          {!isDialogueOpen && (
            <div style={s.reopenTabWrap}>
              <button
                style={s.reopenTab}
                onClick={() => setIsDialogueOpen(true)}
                title="棚を見て気づいたことを開く"
              >
                ›
              </button>
              {pendingDiscoveries.length > 0 && (
                <span style={s.reopenBadge}>{pendingDiscoveries.length}</span>
              )}
            </div>
          )}

          <main style={{ ...s.shelfPane, flexBasis: `${shelfWidthPct}%` }}>
            {/* 育成インジケータ（6.4）：数値ではなく、棚を照らす光の強さで伝える */}
            <div
              style={{
                ...s.ambientLight,
                opacity: 0.12 + level * 0.55,
              }}
            />
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

          <div style={{ ...s.panelWrap, width: isPanelOpen ? `${PANEL_WIDTH_PCT}%` : 0 }}>
            <CompanionPanel />
          </div>
        </div>
      </div>
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
    background: "#f7f3ea", overflow: "hidden",
  },
  headerRow: { flexShrink: 0, padding: "20px 28px 12px" },
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
  dialogueWrap: {
    flex: "0 0 auto",
    height: "100%",
    overflow: "hidden",
    transition: "width 240ms ease",
  },
  reopenTabWrap: { position: "relative", alignSelf: "center", flexShrink: 0 },
  reopenTab: {
    width: 20, height: 56,
    marginRight: -4,
    borderRadius: "0 10px 10px 0",
    border: "1px solid #ede8da", borderLeft: "none",
    background: "#fdfcf8", color: "#9a8b76",
    fontSize: 14, lineHeight: 1, cursor: "pointer",
    boxShadow: "2px 0 8px rgba(0,0,0,0.06)",
  },
  reopenBadge: {
    position: "absolute", top: -6, left: -6,
    minWidth: 16, height: 16, padding: "0 4px", borderRadius: 999,
    background: "#c9a84c", color: "#fff", fontSize: 9, fontWeight: 800,
    display: "flex", alignItems: "center", justifyContent: "center",
    border: "2px solid #f7f3ea", lineHeight: 1,
  },
  ambientLight: {
    position: "absolute",
    top: 0, left: 0, right: 0, height: 260,
    background:
      "radial-gradient(120% 100% at 50% 0%, rgba(255,236,190,0.9) 0%, rgba(255,236,190,0) 70%)",
    pointerEvents: "none",
    zIndex: 1,
    transition: "opacity 1.6s ease",
  },
};
