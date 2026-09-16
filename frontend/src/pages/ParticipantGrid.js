// 「みんなの本棚」の一覧（BrowseLayout の子ルート＝インデックス）。
// 見出し・パンくずは親の BrowseLayout が持つので、ここではカード一覧だけを描く。
//
// 実験の試行割り当て（/experiment/assignment/{myId}）があれば、一覧をその
// 割り当て（owner_id・表示順・フェーズ・条件）だけに絞ってバッジ表示する。
// 割り当てが無い参加者（研究者の自由閲覧・デモ用途）は従来通り全員を表示する。
import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { getParticipantId } from "../utils/participant";

const API = "http://localhost:8000";

const PHASE_LABEL = { phase1: "フェーズ1", phase2: "フェーズ2（転移）" };

export default function ParticipantGrid() {
  const { beginCardTransition } = useOutletContext();
  const [participants, setParticipants] = useState([]);
  const [assignments, setAssignments] = useState(null); // null = 未取得, [] = 割り当てなし
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
    Promise.all([
      fetch(`${API}/participants/`).then(res => (res.ok ? res.json() : Promise.reject(new Error("一覧の読み込みに失敗しました")))),
      fetch(`${API}/experiment/assignment/${myId}`).then(res => (res.ok ? res.json() : { assignments: [] })).catch(() => ({ assignments: [] })),
    ])
      .then(([participantsJson, assignmentJson]) => {
        if (cancelled) return;
        setParticipants(participantsJson.participants || []);
        setAssignments(assignmentJson.assignments || []);
      })
      .catch(err => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [myId]);

  const others = participants.filter(p => p.participant_id !== myId);

  // 割り当てがあれば、その順序・内容だけに絞る（無ければ全員表示のまま）。
  const assignmentByOwner = new Map((assignments || []).map(a => [a.owner_id, a]));
  const visible = assignments && assignments.length > 0
    ? assignments
        .map(a => ({ ...others.find(p => p.participant_id === a.owner_id), assignment: a }))
        .filter(p => p.participant_id)
    : others.map(p => ({ ...p, assignment: assignmentByOwner.get(p.participant_id) || null }));

  return (
    <div style={s.scrollArea}>
      {isLoading && <p style={s.status}>読み込み中…</p>}
      {error && <p style={s.statusError}>{error}</p>}

      {!isLoading && !error && (
        <div style={s.grid}>
          {visible.map(p => (
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
              {p.assignment && (
                <div style={s.assignmentRow}>
                  <span style={s.trialBadge}>試行{p.assignment.trial_index + 1}</span>
                  <span style={s.phaseBadge}>{PHASE_LABEL[p.assignment.phase] || p.assignment.phase}</span>
                </div>
              )}
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
  assignmentRow: { display: "flex", gap: 6, flexWrap: "wrap" },
  trialBadge: {
    fontSize: 9.5, fontWeight: 700, color: "#5a4a33", background: "#efe6d0",
    borderRadius: 999, padding: "2px 8px", whiteSpace: "nowrap",
  },
  phaseBadge: {
    fontSize: 9.5, fontWeight: 700, color: "#3a6a52", background: "#e3f3ea",
    borderRadius: 999, padding: "2px 8px", whiteSpace: "nowrap",
  },
  cardId: { fontSize: 15, fontWeight: 700, color: "#2a1f0e" },
  badge: {
    fontSize: 9.5, fontWeight: 700, color: "#8a5a1f", background: "#fdeecb",
    borderRadius: 999, padding: "2px 8px", whiteSpace: "nowrap",
  },
  cardMeta: { fontSize: 12.5, color: "#8a7a63" },
};
