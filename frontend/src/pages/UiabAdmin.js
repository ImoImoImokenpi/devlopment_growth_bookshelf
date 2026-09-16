// 新UI vs 旧UI比較実験の管理画面(研究者向け)。既存のExperimentAdminと同じく
// 認証は設けず、単一ページで完結させる。
import { useEffect, useState } from "react";
import { API_ORIGIN } from "../utils/uiabIdentity";

const API = `${API_ORIGIN}/uiab`;

export default function UiabAdmin() {
  const [participants, setParticipants] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/admin/participants`)
      .then(res => res.json())
      .then(data => setParticipants(data.participants || []))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  const newCount = participants.filter(p => p.ui_variant === "new").length;
  const oldCount = participants.filter(p => p.ui_variant === "old").length;

  return (
    <div style={s.page}>
      <h1 style={s.title}>新旧UI比較実験: 管理</h1>
      <p style={s.sub}>
        参加者は <code>/Uiab</code> から研究者発行のIDでアクセスします(このアプリのナビゲーションには意図的に出していません)。
      </p>

      <section style={s.section}>
        <h2 style={s.h2}>参加者・群割り当て</h2>
        {loading ? (
          <div style={s.hint}>読み込み中…</div>
        ) : (
          <>
            <div style={s.summary}>合計{participants.length}名(新UI {newCount} / 旧UI {oldCount})</div>
            <div style={s.table}>
              {participants.map(p => (
                <div key={p.participant_id} style={s.row}>
                  <span style={s.pid}>{p.participant_id}</span>
                  <span style={{ ...s.variantTag, ...(p.ui_variant === "new" ? s.variantNew : s.variantOld) }}>
                    {p.ui_variant}
                  </span>
                  <span style={s.createdAt}>{p.created_at}</span>
                </div>
              ))}
              {participants.length === 0 && <div style={s.hint}>まだ誰もアクセスしていません</div>}
            </div>
          </>
        )}
      </section>

      <section style={s.section}>
        <h2 style={s.h2}>エクスポート</h2>
        <div style={s.exportRow}>
          <a style={s.exportLink} href={`${API}/admin/export.json`} target="_blank" rel="noreferrer">
            全データ(JSON)
          </a>
          <a style={s.exportLink} href={`${API}/admin/export/placements.csv`}>配置(CSV)</a>
          <a style={s.exportLink} href={`${API}/admin/export/self-reports.csv`}>自己申告(CSV)</a>
          <a style={s.exportLink} href={`${API}/admin/export/observer-guesses.csv`}>観察者評価(CSV)</a>
          <a style={s.exportLink} href={`${API}/admin/export/events.csv`}>操作ログ(CSV)</a>
        </div>
      </section>
    </div>
  );
}

const s = {
  page: { padding: "90px 28px 60px", minHeight: "100vh", background: "#fdfcf8", maxWidth: 900, margin: "0 auto" },
  title: { fontSize: 22, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", marginBottom: 6 },
  sub: { fontSize: 12.5, color: "#8a7960", marginBottom: 30, lineHeight: 1.6 },
  section: { marginBottom: 36 },
  h2: { fontSize: 14, fontWeight: 700, color: "#c9a84c", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 },
  hint: { fontSize: 12.5, color: "#9a8b76" },
  summary: { fontSize: 12.5, color: "#4a3728", marginBottom: 10 },
  table: { display: "flex", flexDirection: "column", gap: 4 },
  row: {
    display: "flex", alignItems: "center", gap: 12, padding: "8px 12px",
    borderRadius: 8, border: "1px solid #ede8da", background: "#fff", fontSize: 12.5,
  },
  pid: { fontFamily: "monospace", fontWeight: 700, color: "#2a1f0e", width: 100 },
  variantTag: { padding: "2px 10px", borderRadius: 999, fontSize: 11, fontWeight: 700 },
  variantNew: { background: "#eef6ff", color: "#2f6fb0" },
  variantOld: { background: "#fdf0da", color: "#a67c2e" },
  createdAt: { color: "#bbb", fontSize: 11, marginLeft: "auto" },
  exportRow: { display: "flex", flexWrap: "wrap", gap: 10 },
  exportLink: {
    padding: "9px 16px", borderRadius: 10, border: "1px solid #c9a84c", color: "#c9a84c",
    fontSize: 12.5, fontWeight: 700, textDecoration: "none",
  },
};
