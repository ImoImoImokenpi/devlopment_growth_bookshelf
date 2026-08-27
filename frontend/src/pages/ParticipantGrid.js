// 「みんなの本棚」の一覧（BrowseLayout の子ルート＝インデックス）。
// 見出し・パンくずは親の BrowseLayout が持つので、ここではカード一覧だけを描く。
import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { getParticipantId } from "../utils/participant";

const API = "http://localhost:8000";

export default function ParticipantGrid() {
  const { beginCardTransition } = useOutletContext();
  const [participants, setParticipants] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const myId = getParticipantId();

  // 通常の左クリックだけ「カードが拡大して本棚が現れる」演出付きの遷移にする。
  // 中クリック・Ctrl/Cmd+クリックなどは新しいタブで開く操作なので、
  // 既定のリンク遷移のままにしておく。
  const handleCardClick = (e, participantId) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const rect = e.currentTarget.getBoundingClientRect();
    beginCardTransition(
      { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
      participantId
    );
  };

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/participants/`)
      .then(res => (res.ok ? res.json() : Promise.reject(new Error("一覧の読み込みに失敗しました"))))
      .then(json => { if (!cancelled) setParticipants(json.participants || []); })
      .catch(err => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const others = participants.filter(p => p.participant_id !== myId);

  return (
    <div style={s.scrollArea}>
      {isLoading && <p style={s.status}>読み込み中…</p>}
      {error && <p style={s.statusError}>{error}</p>}

      {!isLoading && !error && (
        <div style={s.grid}>
          {others.map(p => (
            <Link
              key={p.participant_id}
              to={p.participant_id}
              style={s.card}
              onClick={e => handleCardClick(e, p.participant_id)}
              onMouseEnter={e => {
                e.currentTarget.style.transform = "translateY(-2px) scale(1.03)";
                e.currentTarget.style.boxShadow = "0 8px 20px rgba(0,0,0,0.1)";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.transform = "translateY(0) scale(1)";
                e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.04)";
              }}
            >
              <div style={s.cardTop}>
                <span style={s.cardId}>{p.participant_id}</span>
                {p.is_prototype && <span style={s.badge}>プロトタイプ</span>}
              </div>
              <div style={s.cardMeta}>{p.total_books}冊</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

const s = {
  scrollArea: {
    height: "100%", overflowY: "auto", boxSizing: "border-box",
    maxWidth: 820, margin: "0 auto", padding: "0 28px 28px",
  },
  status: { color: "#888", fontSize: 14 },
  statusError: { color: "#c9506a", fontSize: 14 },
  // 参加者20名（自分を除く）を5列×4行で並べる。件数が増えても崩れないよう
  // 5列は固定し、はみ出た分は自然に次の行へ折り返す。
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(5, 1fr)",
    gap: 14,
  },
  card: {
    display: "flex", flexDirection: "column", gap: 6,
    padding: "16px 14px", borderRadius: 10,
    border: "1px solid #e5ded0", background: "#fff",
    textDecoration: "none", color: "inherit",
    boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
    transition: "transform 0.15s, box-shadow 0.15s",
  },
  cardTop: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 },
  cardId: { fontSize: 15, fontWeight: 700, color: "#2a1f0e" },
  badge: {
    fontSize: 9.5, fontWeight: 700, color: "#8a5a1f", background: "#fdeecb",
    borderRadius: 999, padding: "2px 8px", whiteSpace: "nowrap",
  },
  cardMeta: { fontSize: 12.5, color: "#8a7a63" },
};
