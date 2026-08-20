// 左ペイン「発見と対話」（設計書5章の発見エンジン ＋ 6.1の対話パネル）。
//
// 本詳細（右）と違い、特定の本を選んでいなくても常に使える相棒機能。
// 本棚を挟んで右の「本詳細」と対称に配置する（Home.js参照）。
//
// 育成インジケータ → 発見と対話のストリーム、という並びは以前の右ペイン版から
// 引き継いでいる（俯瞰モードとまとめて確認は廃止。発見はすべて対話ストリーム
// の中にAIの発言として流れるので、別画面でまとめて処理する必要がなくなった）。
//
// 「棚を読む」ボタンは廃止した。未回答の発見が尽きるたびに
// ShelfWorkspaceContext が勝手に棚を読み直す（自動分析）。押さなくても、
// 棚を眺めているだけで新しい気づきが本棚上の「！」マークとして湧いてくる
// （QuestionCardLayer参照）。
import GrowthIndicator from "./GrowthIndicator";
import DialoguePanel from "./DialoguePanel";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";

export default function DiscoveryDialoguePanel() {
  const { setIsDialogueOpen } = useShelfWorkspace();

  return (
    <aside style={s.panel}>
      <div style={s.head}>
        <span style={s.headTitle}>発見と対話</span>
        <button
          style={s.collapseBtn}
          onClick={() => setIsDialogueOpen(false)}
          title="発見と対話を収納する"
        >
          ‹
        </button>
      </div>

      <GrowthIndicator />

      <DialoguePanel />
    </aside>
  );
}

const s = {
  // 右の本詳細パネルと同じく、ここ1箇所だけがスクロールする。
  panel: {
    display: "flex", flexDirection: "column",
    width: "100%",
    background: "#fdfcf8", borderRight: "1px solid #ede8da",
    height: "100%", overflowY: "auto", overflowX: "hidden",
  },
  head: {
    position: "sticky", top: 0, zIndex: 3,
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "10px 12px", borderBottom: "1px solid #ede8da",
    background: "#fdfcf8", flexShrink: 0,
  },
  headTitle: {
    fontSize: 12, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif",
  },
  collapseBtn: {
    width: 22, height: 22, borderRadius: "50%", border: "none",
    background: "#ede8da", color: "#4a3728", cursor: "pointer",
    fontSize: 13, lineHeight: 1,
  },
};
