// 発見への応答UI（設計書6.2の一次応答 + 7.3のフィードバック収集）。
//
// 三択にする: はい / いいえ / さらに話す ← 押すだけで終われる軽さを保つ
// 以前は「一部ちがう」で訂正コメントを書かせていたが、正誤の判定はYes/Noだけで
// 十分軽くし、深掘りしたいときは「さらに話す」で対話へ流れ込む一本にまとめた
// （別立てだった「もっと話す」ボタンは廃止し、この三択の1つに統合した）。
//
// 「さらに話す」は対話ストリームにAIの発言を差し込むため、対話が別件で
// 返信待ちの間に押されると2つの会話が交錯してしまう。isChatBusy の間は
// 押せなくしておく（呼び出し側が talkDisabled として渡す）。
import { useState } from "react";

const SCORES = [1, 2, 3, 4, 5];

export default function DiscoveryResponse({ discovery, onAnswer, onTalkMore, talkDisabled = false }) {
  const answered = discovery.status !== "pending";
  const [showScores, setShowScores] = useState(false);
  const [agreement, setAgreement] = useState(discovery.agreement_score ?? null);
  const [surprise, setSurprise] = useState(discovery.surprise_score ?? null);

  const answer = (status) => {
    onAnswer(discovery.discovery_id, status, {
      agreement_score: agreement,
      surprise_score: surprise,
    });
    setShowScores(true);
  };

  const saveScores = (nextAgreement, nextSurprise) => {
    onAnswer(discovery.discovery_id, discovery.status === "pending" ? "confirmed" : discovery.status, {
      agreement_score: nextAgreement,
      surprise_score: nextSurprise,
    });
  };

  return (
    <div style={s.wrap}>
      {!answered && (
        <div style={s.btnRow}>
          <button style={{ ...s.btn, ...s.btnYes }} onClick={() => answer("confirmed")}>はい</button>
          <button style={{ ...s.btn, ...s.btnNo }} onClick={() => answer("rejected")}>いいえ</button>
          {onTalkMore && (
            <button
              style={{ ...s.btn, ...s.btnTalk, ...(talkDisabled ? s.btnDisabled : {}) }}
              onClick={onTalkMore}
              disabled={talkDisabled}
              title={talkDisabled ? "対話が返信中です。少し待ってから押してください" : undefined}
            >
              さらに話す
            </button>
          )}
        </div>
      )}

      {answered && (
        <div style={s.answeredRow}>
          <span style={s.answeredLabel}>
            {discovery.status === "confirmed" && "そうだと答えました"}
            {discovery.status === "rejected" && "ちがうと答えました"}
          </span>
          {!showScores && (
            <button style={s.linkBtn} onClick={() => setShowScores(true)}>感想を足す</button>
          )}
        </div>
      )}

      {showScores && (
        <div style={s.scoreBlock}>
          <ScoreRow
            label="納得した"
            value={agreement}
            onChange={v => { setAgreement(v); saveScores(v, surprise); }}
          />
          <ScoreRow
            label="意外だった"
            value={surprise}
            onChange={v => { setSurprise(v); saveScores(agreement, v); }}
          />
        </div>
      )}
    </div>
  );
}

function ScoreRow({ label, value, onChange }) {
  return (
    <div style={s.scoreRow}>
      <span style={s.scoreLabel}>{label}</span>
      <div style={s.dots}>
        {SCORES.map(n => (
          <button
            key={n}
            onClick={() => onChange(n)}
            title={`${n}`}
            style={{
              ...s.dot,
              background: value != null && n <= value ? "#c9a84c" : "transparent",
              borderColor: value != null && n <= value ? "#c9a84c" : "#ddd5c2",
            }}
          />
        ))}
      </div>
    </div>
  );
}

const s = {
  wrap: { display: "flex", flexDirection: "column", gap: 8 },
  btnRow: { display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" },
  btn: {
    padding: "6px 14px", fontSize: 11.5, fontWeight: 600,
    color: "#4a3728", background: "#fff",
    border: "1.5px solid #e0d5b8", borderRadius: 999, cursor: "pointer",
  },
  btnYes: { color: "#fff", background: "#c9a84c", borderColor: "#c9a84c" },
  btnNo: { color: "#8a7a63", borderColor: "#e0d5b8" },
  btnTalk: { color: "#ff9d3d", borderColor: "#ffcfa0" },
  btnDisabled: { color: "#c4b8a2", borderColor: "#e5ded0", cursor: "not-allowed" },
  answeredRow: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" },
  answeredLabel: { fontSize: 11, color: "#9a8b76" },
  linkBtn: {
    background: "transparent", border: "none", color: "#ff9d3d",
    fontSize: 11, cursor: "pointer", padding: 0, textDecoration: "underline",
  },
  scoreBlock: {
    display: "flex", flexDirection: "column", gap: 6,
    paddingTop: 6, borderTop: "1px dashed #ede8da",
  },
  scoreRow: { display: "flex", alignItems: "center", gap: 10 },
  scoreLabel: { fontSize: 10.5, color: "#9a8b76", width: 58, flexShrink: 0 },
  dots: { display: "flex", gap: 4 },
  dot: {
    width: 12, height: 12, borderRadius: "50%",
    border: "1px solid #ddd5c2", cursor: "pointer", padding: 0,
  },
};
