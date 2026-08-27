// 発見の一覧（設計書5章の発見エンジンの受け皿）。
//
// 以前は一覧をタップしてから対話（DialoguePanel）に1件だけ引き継ぎ、そこで
// 初めて回答できる2段構成にしていた。だが「一覧をタップ→対話で回答」という
// ワンクッションが冗長という指摘を受け、ここに直接 はい/いいえ/さらに話す の
// 返答UI（DiscoveryResponse）を埋め込み、一覧の中でそのまま回答できるように
// した。「さらに話す」だけは深掘りが必要なので、そのときだけ下の対話ストリーム
// （DialoguePanel）へ話題を引き継ぐ。
//
// 未回答の発見だけを出す。回答済みは（一度は一覧に残す案も試したが）ここでは
// 表示しない。答えた瞬間にこの一覧からすっと消えるだけの、身軽な受け皿にする。
// 関連本は棚の上でハイライト（highlightIsbns）として光る＝現状のコードのまま。
//
// たまりすぎても選ぶのが面倒になるため、表示は最大5件まで。
//
// 「さらに話す」を押した瞬間は、まさに1件と向き合って対話に集中したい
// タイミングなので、残りの未回答分はいったんしまって（件数バッジだけ残す）
// 邪魔をしないようにする。ヘッダーを押せばいつでも出し戻せる。
import { useState } from "react";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";
import DiscoveryResponse from "./DiscoveryResponse";

const MAX_PENDING = 5;

const TYPE_LABEL = {
  commonality: "共通点",
  contradiction: "食い違い",
  implicit_pattern: "並べ方の癖",
  structural: "全体の構造",
};

export default function DiscoveryList() {
  const {
    pendingDiscoveries, answerDiscovery,
    setHighlightIsbns, setChatSeed, isChatBusy,
  } = useShelfWorkspace();
  const [collapsed, setCollapsed] = useState(false);

  const pending = pendingDiscoveries.slice(0, MAX_PENDING);
  if (pending.length === 0) return null;

  return (
    <div style={s.wrap}>
      <button style={s.header} onClick={() => setCollapsed(c => !c)}>
        <span style={s.headerLabel}>発見</span>
        <span style={s.count}>{pending.length}</span>
        <span style={s.reopenHint}>{collapsed ? "タップで表示" : "タップで非表示"}</span>
      </button>

      {!collapsed && (
        <div style={s.list}>
          {pending.map(d => (
            <DiscoveryRow
              key={d.discovery_id}
              discovery={d}
              onAnswer={answerDiscovery}
              onHover={setHighlightIsbns}
              talkDisabled={isChatBusy}
              onTalkMore={() => {
                setChatSeed({ question: d.generated_question, isbns: d.related_book_ids || [] });
                setHighlightIsbns(d.related_book_ids || []);
                // 対話に集中させるため、残りの未回答分はいったんしまう
                setCollapsed(true);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DiscoveryRow({ discovery: d, onAnswer, onHover, onTalkMore, talkDisabled }) {
  return (
    <div
      style={s.row}
      onMouseEnter={() => onHover(d.related_book_ids || [])}
      onMouseLeave={() => onHover([])}
    >
      <div style={s.itemHead}>
        <span style={s.typeBadge}>{TYPE_LABEL[d.type] || "気づき"}</span>
        {(d.related_book_ids || []).length > 0 && (
          <span style={s.evidenceHint}>{d.related_book_ids.length}冊にまたがる話</span>
        )}
      </div>

      <div style={s.question}>{d.generated_question}</div>
      {d.body && <div style={s.body}>{d.body}</div>}

      <DiscoveryResponse discovery={d} onAnswer={onAnswer} onTalkMore={onTalkMore} talkDisabled={talkDisabled} />
    </div>
  );
}

const s = {
  wrap: {
    borderBottom: "1px solid #ede8da", background: "#fdfcf8", flexShrink: 0,
  },
  header: {
    width: "100%", display: "flex", alignItems: "center", gap: 8,
    padding: "10px 14px", background: "transparent", border: "none",
    cursor: "pointer", fontFamily: "inherit",
  },
  headerLabel: {
    fontSize: 13.5, fontWeight: 700, color: "#c9a84c",
    fontFamily: "serif", letterSpacing: "0.03em",
  },
  count: {
    minWidth: 18, height: 18, padding: "0 5px", borderRadius: 999,
    background: "#c9a84c", color: "#fff", fontSize: 10, fontWeight: 800,
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  reopenHint: {
    fontSize: 10, color: "#b3a692", marginLeft: "auto",
  },
  list: {
    display: "flex", flexDirection: "column", gap: 8,
    padding: "6px 10px 12px",
  },
  row: {
    display: "flex", flexDirection: "column", gap: 8,
    borderRadius: 10, borderLeft: "3px solid #c9a84c", background: "#fffdf5",
    padding: "8px 12px 8px 10px",
  },
  itemHead: { display: "flex", alignItems: "center", gap: 8 },
  typeBadge: {
    fontSize: 9, fontWeight: 700, color: "#c9a84c",
    border: "1px solid #e8dcb8", borderRadius: 999, padding: "1px 7px",
    letterSpacing: "0.04em", whiteSpace: "nowrap",
  },
  evidenceHint: { fontSize: 9.5, color: "#b3a692" },
  question: { fontSize: 12, fontWeight: 600, color: "#2a1f0e", lineHeight: 1.55 },
  body: { fontSize: 11, color: "#6b5c47", lineHeight: 1.6 },
};
