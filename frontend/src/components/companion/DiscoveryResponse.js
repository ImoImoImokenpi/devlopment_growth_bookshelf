// 発見への応答UI（設計書6.2の一次応答 + 7.3のフィードバック収集）。
//
// 2段階構成にする:
//   1段目: はい / ちがう / 一部ちがう  ← 押すだけで終われる軽さを保つ
//   2段目: 納得度・驚き度、必要なら訂正の一言
//
// 2段目を必須にすると答えるのが億劫になって回答率が落ちるので、
// 1段目を押した時点で記録は済ませ、2段目は任意の上乗せにする。
import { useState } from "react";

const SCORES = [1, 2, 3, 4, 5];

export default function DiscoveryResponse({ discovery, onAnswer, onTalkMore, compact = false }) {
  const answered = discovery.status !== "pending";
  const [showScores, setShowScores] = useState(false);
  const [agreement, setAgreement] = useState(discovery.agreement_score ?? null);
  const [surprise, setSurprise] = useState(discovery.surprise_score ?? null);
  const [comment, setComment] = useState("");
  const [isEditingComment, setIsEditingComment] = useState(false);

  const answer = (status) => {
    if (status === "modified") {
      // ここではまだ送信しない。送信して status が "pending" から外れると、
      // 親側の「未回答一覧」からこのカード自体が消えてコメント欄も一緒に
      // 消えてしまうため（左パネルの吹き出し・棚のバッジカード共通の問題）。
      // 実際の送信はコメントを確定したとき（下のEnterハンドラ）に行う。
      setIsEditingComment(true);
      return;
    }
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
      comment: comment || null,
    });
  };

  return (
    <div style={s.wrap}>
      {!answered && (
        <div style={s.btnRow}>
          <button style={{ ...s.btn, ...s.btnYes }} onClick={() => answer("confirmed")}>はい</button>
          <button style={s.btn} onClick={() => answer("rejected")}>ちがう</button>
          <button style={s.btn} onClick={() => answer("modified")}>一部ちがう</button>
          {onTalkMore && (
            <button style={s.talkBtn} onClick={onTalkMore}>もっと話す</button>
          )}
        </div>
      )}

      {answered && (
        <div style={s.answeredRow}>
          <span style={s.answeredLabel}>
            {discovery.status === "confirmed" && "そうだと答えました"}
            {discovery.status === "rejected" && "ちがうと答えました"}
            {discovery.status === "modified" && "一部ちがうと答えました"}
          </span>
          {!compact && !showScores && (
            <button style={s.linkBtn} onClick={() => setShowScores(true)}>感想を足す</button>
          )}
          {onTalkMore && (
            <button style={s.linkBtn} onClick={onTalkMore}>もっと話す</button>
          )}
        </div>
      )}

      {isEditingComment && (
        <div style={s.commentRow}>
          <input
            autoFocus
            style={s.commentInput}
            value={comment}
            onChange={e => setComment(e.target.value)}
            placeholder="どこがちがいましたか？"
            onKeyDown={e => {
              if (e.key === "Enter") {
                onAnswer(discovery.discovery_id, "modified", {
                  agreement_score: agreement,
                  surprise_score: surprise,
                  comment: comment || null,
                });
                setIsEditingComment(false);
                setShowScores(true);
              }
            }}
          />
        </div>
      )}

      {showScores && !compact && (
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
    padding: "5px 12px", fontSize: 11.5, fontWeight: 600,
    color: "#4a3728", background: "#fff",
    border: "1px solid #e0d5b8", borderRadius: 999, cursor: "pointer",
  },
  btnYes: { color: "#fff", background: "#c9a84c", borderColor: "#c9a84c" },
  talkBtn: {
    marginLeft: "auto", padding: "5px 10px", fontSize: 11,
    color: "#ff9d3d", background: "transparent",
    border: "none", cursor: "pointer", textDecoration: "underline",
  },
  answeredRow: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" },
  answeredLabel: { fontSize: 11, color: "#9a8b76" },
  linkBtn: {
    background: "transparent", border: "none", color: "#ff9d3d",
    fontSize: 11, cursor: "pointer", padding: 0, textDecoration: "underline",
  },
  commentRow: { display: "flex" },
  commentInput: {
    flex: 1, padding: "6px 10px", fontSize: 11.5,
    border: "1px solid #e5ded0", borderRadius: 8,
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
