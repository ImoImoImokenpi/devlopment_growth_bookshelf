// 左ペイン「発見と対話」（設計書5章の発見エンジン ＋ 6.1の対話パネル）。
//
// 本詳細（右）と違い、特定の本を選んでいなくても常に使える相棒機能。
// 本棚を挟んで右の「本詳細」と対称に配置する（Home.js参照）。
//
// 発見一覧 → 対話のストリーム、という並びは以前の右ペイン版から
// 引き継いでいる（俯瞰モードとまとめて確認は廃止）。
//
// 育成インジケータ（灯りの強さで知識グラフの育ちを伝える演出）は未使用のため削除済み。
// growth自体（ShelfWorkspaceContext）はHome.jsのambientLight演出で使っている。
//
// 未回答・回答済みの発見はどちらもDiscoveryListにまとめて出し、そこで
// 直接 はい/いいえ/さらに話す を押して回答できる（以前は一覧をタップして
// 対話に1件引き継いでから回答する2段構成だったが、ワンクッション減らした）。
// 「さらに話す」を押したときだけ下の対話ストリームへ話題を引き継ぐ。
//
// 「棚を読む」ボタンは廃止した。未回答の発見が尽きるたびに
// ShelfWorkspaceContext が勝手に棚を読み直す（自動分析）。押さなくても、
// 棚を眺めているだけで新しい気づきが発見一覧に湧いてくる。
import DiscoveryList from "./DiscoveryList";
import DialoguePanel from "./DialoguePanel";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";

export default function DiscoveryDialoguePanel() {
  const { setIsDialogueOpen } = useShelfWorkspace();

  return (
    <aside style={s.panel}>
      <div style={s.head}>
        <button
          style={s.collapseBtn}
          onClick={() => setIsDialogueOpen(false)}
          title="棚を見て気づいたことを収納する"
        >
          ‹
        </button>
      </div>

      <DiscoveryList />

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
    display: "flex", alignItems: "center", justifyContent: "flex-end",
    padding: "10px 12px", borderBottom: "1px solid #ede8da",
    background: "#fdfcf8", flexShrink: 0,
  },
  collapseBtn: {
    width: 22, height: 22, borderRadius: "50%", border: "none",
    background: "#ede8da", color: "#4a3728", cursor: "pointer",
    fontSize: 13, lineHeight: 1,
  },
};
