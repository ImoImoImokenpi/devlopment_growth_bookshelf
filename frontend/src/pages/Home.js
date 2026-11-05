// アプリのメイン画面「育つ本棚」(/)。上部のナビバー(Layout)の下に全面表示する。
//
// 画面構成:
//   見出し列 : タイトル・冊数（左）、棚の設定と「対話する」（右）
//   本文     : 本棚の作業スペース（左・背表紙をドラッグで並べ替える）
//              ＋ 右パネル（本を選ぶと本の詳細、「対話する」を押すと対話）
//
// 「対話する」は見出し列の右端に置き、押すとその真下の右パネルが対話に切り替わる。
// ボタンと開くパネルの位置をそろえ、どこに何が出たのか迷わないようにする。
//
// 本棚の幅は「棚の設定 → 本棚サイズの調整」(shelfWidthPct) で画面幅に対する割合を
// 変えられる。作業スペースより大きくはならず、はみ出た高さは作業スペース内で縦スクロールする。
//
// グルーピング（左のグループパネル・ModeToggle）はいったん画面から外している。
// 部品（components/grouping, ModeToggle）とSpineShelfView側の処理は残してある。
//
// 本棚の型は SHELF_VIEW で切り替える。今はグリッドの本棚（GridShelfView）だけを出し、
// 背表紙の本棚（SpineShelfView）と棚の設定メニューは画面から外している（コードは残してある）。
// 背表紙に戻すときは、ここを "spine" にし、backend/utils/shelf_geometry.py の
// SHELF_MODE も "spine" にする。
import { useState } from "react";
import SpineShelfView from "../components/SpineShelfView";
import GridShelfView from "../components/GridShelfView";
import OwnBookGrid from "../components/OwnBookGrid";
import ShelfSettingsMenu from "../components/ShelfSettingsMenu";
import PageHeader from "../components/PageHeader";
import { PAGE_PAD_X, PAGE_PAD_TOP } from "../components/Layout";
import CompanionPanel from "../components/companion/CompanionPanel";
import ShelfSwitcher from "../components/shelves/ShelfSwitcher";
import { ShelvesProvider, useShelves } from "../context/ShelvesContext";
import DialoguePanel from "../components/dialogue/DialoguePanel";
import {
  ShelfWorkspaceProvider,
  useShelfWorkspace,
} from "../context/ShelfWorkspaceContext";

const SHELF_VIEW = "grid"; // "grid" | "spine"

const SIDE_PANEL_W = 380;      // 本の詳細パネルの幅(px)
const DIALOGUE_PANEL_W = 460;  // 対話パネルの幅(px)

function HomeWorkspace() {
  const { focusIsbn, setFocusIsbn, shelfWidthPct, growth } = useShelfWorkspace();
  const { activeShelf } = useShelves();
  const [isDialogueOpen, setIsDialogueOpen] = useState(false);
  // 背表紙⇄グリッドの切り替えは「棚の設定」の中にある。デフォルトは背表紙表示。
  const [viewMode, setViewMode] = useState("spine");

  const isDetailOpen = !isDialogueOpen && !!focusIsbn;
  const panelWidth = isDialogueOpen ? DIALOGUE_PANEL_W : isDetailOpen ? SIDE_PANEL_W : 0;

  const openDialogue = () => {
    setFocusIsbn(null);
    setIsDialogueOpen(true);
  };

  return (
    <div style={s.page}>
      <style>{`
        .shelf-stage { scrollbar-width: thin; scrollbar-color: #d8ccb0 transparent; }
        .shelf-stage::-webkit-scrollbar { width: 8px; height: 8px; }
        .shelf-stage::-webkit-scrollbar-button { display: none; }
        .shelf-stage::-webkit-scrollbar-thumb { background: #d8ccb0; border-radius: 4px; }
        .talk-btn:hover:not(:disabled) { background: #b8963a !important; }
      `}</style>

      <div style={s.header}>
        <PageHeader
          title="育つ本棚"
          sub={[activeShelf?.name, growth?.books != null ? `${growth.books}冊` : null, "本棚と対話しよう！"].filter(Boolean).join(" ・ ")}
          right={
            <div style={s.actions}>
              <ShelfSwitcher />
              {SHELF_VIEW === "spine" && (
                <ShelfSettingsMenu viewMode={viewMode} onViewModeChange={setViewMode} />
              )}
              <button
                className="talk-btn"
                style={{ ...s.talkBtn, ...(isDialogueOpen ? s.talkBtnActive : {}) }}
                onClick={openDialogue}
                disabled={isDialogueOpen}
                title="本棚と対話する"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                {isDialogueOpen ? "対話中" : "対話する"}
              </button>
            </div>
          }
        />
      </div>

      <div style={s.body}>
        {/* 作業スペース。本棚と右パネル（本の詳細・対話）を1つのまとまりとして中央に置き、
            パネルが本棚のすぐ横に開くようにする。本棚は自分の列の中で縦スクロールする。 */}
        <div style={s.stage}>
          {SHELF_VIEW === "grid" ? (
            <div className="shelf-stage" style={s.gridCol}>
              <GridShelfView />
            </div>
          ) : viewMode === "spine" ? (
            <div
              className="shelf-stage"
              style={{ ...s.shelfCol, width: `min(${shelfWidthPct}vw, 100%)` }}
            >
              <div style={s.shelfWrap}>
                <SpineShelfView />
              </div>
            </div>
          ) : (
            <div className="shelf-stage" style={s.gridCol}>
              <OwnBookGrid />
            </div>
          )}

          <aside
            style={{
              ...s.side,
              width: panelWidth,
              marginLeft: panelWidth ? 24 : 0,
              borderWidth: panelWidth ? 1 : 0,
            }}
          >
            <div style={{ ...s.sideInner, width: panelWidth || SIDE_PANEL_W }}>
              {isDialogueOpen
                ? <DialoguePanel onClose={() => setIsDialogueOpen(false)} />
                : <CompanionPanel />}
            </div>
          </aside>
        </div>
      </div>

    </div>
  );
}

export default function Home() {
  return (
    <ShelvesProvider>
      <ShelfWorkspaceProvider>
        <HomeWorkspace />
      </ShelfWorkspaceProvider>
    </ShelvesProvider>
  );
}

const s = {
  page: {
    flex: 1, minHeight: 0, display: "flex", flexDirection: "column",
    background: "#fdfcf8",
  },
  header: { flexShrink: 0, padding: `${PAGE_PAD_TOP}px ${PAGE_PAD_X}px 0` },
  actions: { display: "flex", alignItems: "center", gap: 10 },
  talkBtn: {
    display: "inline-flex", alignItems: "center", gap: 8,
    height: 40, padding: "0 20px", borderRadius: 999, border: "none",
    background: "#c9a84c", color: "#fff", fontSize: 13.5, fontWeight: 700,
    cursor: "pointer", fontFamily: "inherit",
    boxShadow: "0 2px 8px rgba(160,120,30,0.25)", transition: "background 0.15s",
  },
  talkBtnActive: {
    background: "#f5efdd", color: "#8a7030", boxShadow: "none", cursor: "default",
  },
  body: {
    flex: 1, minHeight: 0, display: "flex",
    padding: `0 ${PAGE_PAD_X}px 24px`,
  },
  stage: {
    flex: 1, minWidth: 0, minHeight: 0,
    borderRadius: 16, background: "#f3eee2",
    display: "flex", justifyContent: "center",
    padding: "24px",
    boxSizing: "border-box", overflow: "hidden",
  },
  // 本棚の列。影が切れないよう、列の内側に少し余白を持たせる
  shelfCol: {
    flex: "0 1 auto", minWidth: 0, height: "100%",
    overflowY: "auto", overflowX: "hidden",
    display: "flex", flexDirection: "column",
    padding: "4px 12px 28px",
  },
  shelfWrap: {
    flexShrink: 0, margin: "auto 0",
    // filter だと本棚内の固定表示（範囲選択の枠・モーダル）の基準がずれるので box-shadow にする
    boxShadow: "0 14px 30px rgba(60,40,10,0.22)",
  },
  gridCol: { flex: 1, minWidth: 0, height: "100%", overflowY: "auto", boxSizing: "border-box" },
  side: {
    flexShrink: 0, height: "100%", overflow: "hidden",
    borderRadius: 16, borderStyle: "solid", borderColor: "#ede8da", background: "#fff",
    boxShadow: "0 8px 24px rgba(60,40,10,0.08)",
    boxSizing: "border-box",
    transition: "width 240ms ease, margin-left 240ms ease",
  },
  sideInner: { height: "100%" },
};
