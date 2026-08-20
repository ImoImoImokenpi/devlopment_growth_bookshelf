// 設計書6.1の3ペイン構成。
//   左（サブ）  : 発見と対話
//   中央（メイン）: 本棚ビジュアライズ（背表紙・ドラッグ&ドロップ配置）
//   右（サブ）  : 本詳細
//
// 本棚は段を追加しても縮んでいかないよう、画面幅に対する固定割合にする
// （はみ出た分は本棚側の縦スクロールで見る）。割合そのものは「棚の調整」の
// 「本棚サイズの調整」からユーザーが変えられる（shelfWidthPct）。
//
// 右の本詳細は本を選んでいる（focusIsbn がある）ときだけ画面の30%で開き、
// 閉じている間は幅0に収納される。左の発見と対話は特定の本に紐づかない
// 常設の相棒機能なので初期状態で開いているが、圧迫感が出るときのために
// ユーザーがいつでも収納・再表示できる（isDialogueOpen）。
import SpineShelfView from "../components/SpineShelfView";
import CompanionPanel from "../components/companion/CompanionPanel";
import DiscoveryDialoguePanel from "../components/companion/DiscoveryDialoguePanel";
import QuestionCardLayer from "../components/QuestionCardLayer";
import {
  ShelfWorkspaceProvider,
  useShelfWorkspace,
} from "../context/ShelfWorkspaceContext";

const NAVBAR_SPACE = 66; // 上部に固定表示されているNavbarの逃げ
const PANEL_WIDTH_PCT = 30;   // 本詳細が開いているときの画面幅に対する割合
const DIALOGUE_WIDTH_PCT = 28; // 発見と対話が開いているときの画面幅に対する割合

function HomeWorkspace() {
  const { growth, focusIsbn, shelfWidthPct, isDialogueOpen, setIsDialogueOpen } = useShelfWorkspace();
  const level = growth?.level ?? 0;
  const isPanelOpen = !!focusIsbn;

  return (
    <div style={s.grid}>
      <div style={{ ...s.dialogueWrap, width: isDialogueOpen ? `${DIALOGUE_WIDTH_PCT}%` : 0 }}>
        <DiscoveryDialoguePanel />
      </div>

      {!isDialogueOpen && (
        <button
          style={s.reopenTab}
          onClick={() => setIsDialogueOpen(true)}
          title="発見と対話を開く"
        >
          ›
        </button>
      )}

      <main style={{ ...s.shelfPane, flexBasis: `${shelfWidthPct}%` }}>
        {/* 育成インジケータ（6.4）：数値ではなく、棚を照らす光の強さで伝える */}
        <div
          style={{
            ...s.ambientLight,
            opacity: 0.12 + level * 0.55,
          }}
        />
        <SpineShelfView />
      </main>

      <div style={{ ...s.panelWrap, width: isPanelOpen ? `${PANEL_WIDTH_PCT}%` : 0 }}>
        <CompanionPanel />
      </div>

      {/* 本棚に重ねる質問カード */}
      <QuestionCardLayer />
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
  grid: {
    display: "flex",
    justifyContent: "center",
    height: "100vh",
    paddingTop: NAVBAR_SPACE,
    boxSizing: "border-box",
    background: "#f7f3ea",
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
  reopenTab: {
    alignSelf: "center",
    flexShrink: 0,
    width: 20, height: 56,
    marginRight: -4,
    borderRadius: "0 10px 10px 0",
    border: "1px solid #ede8da", borderLeft: "none",
    background: "#fdfcf8", color: "#9a8b76",
    fontSize: 14, lineHeight: 1, cursor: "pointer",
    boxShadow: "2px 0 8px rgba(0,0,0,0.06)",
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
