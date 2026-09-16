// 新UI vs 旧UI比較実験の入口。
// 60名の参加者・20〜25名の観察者を固定ドロップダウンで管理するのは無理があるため、
// 研究者から配布されたIDを直接入力する形にしている。
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getUiabId, getUiabRole, setUiabIdentity, uiabGet } from "../../utils/uiabIdentity";

export function decideParticipantRoute(status) {
  const p1 = status.period1 || {};
  const p2 = status.period2 || {};
  if (!p1.completed_at) return "/Uiab/Build/period1";
  if (!p1.self_expression_score || !status.bigfive_answered) return "/Uiab/SelfReport/period1";
  if (!p2.completed_at) return "/Uiab/Build/period2";
  if (!p2.self_expression_score) return "/Uiab/SelfReport/period2";
  return "/Uiab/Done";
}

export default function UiabEntry() {
  const navigate = useNavigate();
  const [id, setId] = useState(getUiabId());
  const [role, setRole] = useState(getUiabRole() || "participant");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const start = async () => {
    const trimmed = id.trim();
    if (!trimmed) return setError("IDを入力してください");
    setError(null);
    setBusy(true);
    setUiabIdentity(trimmed, role);
    try {
      if (role === "observer") {
        navigate("/Uiab/Observe");
        return;
      }
      const status = await uiabGet("/uiab/status");
      navigate(decideParticipantRoute(status));
    } catch (err) {
      setError(err.message || "状態の取得に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={s.page}>
      <div style={s.card}>
        <h1 style={s.title}>本棚UI比較実験</h1>
        <p style={s.sub}>研究者から伝えられたIDを入力してください。</p>

        <div style={s.roleRow}>
          <button
            style={{ ...s.roleBtn, ...(role === "participant" ? s.roleBtnActive : {}) }}
            onClick={() => setRole("participant")}
          >
            参加者として
          </button>
          <button
            style={{ ...s.roleBtn, ...(role === "observer" ? s.roleBtnActive : {}) }}
            onClick={() => setRole("observer")}
          >
            観察者として
          </button>
        </div>

        <input
          style={s.input}
          value={id}
          onChange={e => setId(e.target.value)}
          placeholder="例: U01 / O01"
          onKeyDown={e => e.key === "Enter" && start()}
        />
        {error && <div style={s.error}>{error}</div>}
        <button style={s.startBtn} onClick={start} disabled={busy}>
          {busy ? "確認中…" : "はじめる"}
        </button>
      </div>
    </div>
  );
}

const s = {
  page: {
    minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
    background: "#f7f3ea", padding: 24,
  },
  card: {
    width: "min(380px, 100%)", background: "#fff", borderRadius: 16,
    padding: "32px 28px", boxShadow: "0 8px 30px rgba(0,0,0,0.08)",
  },
  title: { fontSize: 18, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", marginBottom: 6 },
  sub: { fontSize: 12.5, color: "#8a7960", marginBottom: 20, lineHeight: 1.6 },
  roleRow: { display: "flex", gap: 8, marginBottom: 14 },
  roleBtn: {
    flex: 1, padding: "9px 0", borderRadius: 10, border: "1px solid #e5ded0",
    background: "#fff", color: "#8a7960", fontSize: 12.5, cursor: "pointer", fontWeight: 600,
  },
  roleBtnActive: { background: "#c9a84c", color: "#fff", borderColor: "#c9a84c" },
  input: {
    width: "100%", padding: "11px 14px", borderRadius: 10, border: "1px solid #d0c4a8",
    fontSize: 14, boxSizing: "border-box", marginBottom: 10, outline: "none",
  },
  error: { fontSize: 12, color: "#c9506a", marginBottom: 10 },
  startBtn: {
    width: "100%", padding: 12, background: "#c9a84c", color: "#fff",
    border: "none", borderRadius: 10, fontSize: 14, fontWeight: 700, cursor: "pointer",
  },
};
