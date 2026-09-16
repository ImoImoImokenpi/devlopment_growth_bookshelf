// 実験管理画面（研究者向け、spec 3.5）。
// 設定（試行数・条件配分・対照ペア混入数）・試行割り当ての生成と一覧・
// 対照ペア一覧・進捗確認・GuessRecordのCSV/JSONエクスポートをまとめる。
// 参加者本人向けの画面ではないので、認証等は設けず単一ページで完結させる
// （既存の /StyleProjection ページと同じ、単一ファイル＋内部サブコンポーネント構成）。
import { useEffect, useState } from "react";
import { API_ORIGIN, PARTICIPANT_IDS, PROTOTYPE_PARTICIPANT_ID } from "../utils/participant";

const API = `${API_ORIGIN}/experiment`;

export default function ExperimentAdmin() {
  return (
    <div style={s.scrollArea}>
      <div style={s.header}>
        <h1 style={s.title}>実験管理</h1>
        <p style={s.subtitle}>
          試行数・条件配分・対照ペアの混入数はここから調整できます（コード修正不要）。
          割り当てを生成すると、各参加者の「みんなの本棚」一覧がその割り当てだけに絞られます。
        </p>
      </div>

      <ConfigSection />
      <ContrastivePairsSection />
      <AssignmentSection />
      <ProgressSection />
      <ExportSection />
    </div>
  );
}

// ── 設定 ────────────────────────────────────────────────
function ConfigSection() {
  const [config, setConfig] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    setIsLoading(true);
    setError(null);
    fetch(`${API}/config`)
      .then(res => (res.ok ? res.json() : Promise.reject(new Error("設定の取得に失敗しました"))))
      .then(setConfig)
      .catch(err => setError(err.message))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

  const update = (key, value) => setConfig(c => ({ ...c, [key]: value }));

  const save = async () => {
    setIsSaving(true);
    setMessage(null);
    setError(null);
    try {
      const res = await fetch(`${API}/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phase1_trial_count: Number(config.phase1_trial_count),
          transfer_trial_count: Number(config.transfer_trial_count),
          contrastive_pair_count: Number(config.contrastive_pair_count),
          condition_assignment_mode: config.condition_assignment_mode,
          condition_ratio: Number(config.condition_ratio),
        }),
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) throw new Error(json?.detail || "保存に失敗しました");
      setConfig(json);
      setMessage("設定を保存しました。");
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Section title="実験フロー設定">
      {isLoading && <p style={s.status}>読み込み中…</p>}
      {error && <p style={s.statusError}>{error}</p>}
      {message && <p style={s.statusOk}>{message}</p>}

      {!isLoading && config && (
        <div style={s.configGrid}>
          <Field label="フェーズ1 試行数（4〜6件目安）">
            <input style={s.input} type="number" min={1} value={config.phase1_trial_count}
              onChange={e => update("phase1_trial_count", e.target.value)} />
          </Field>
          <Field label="フェーズ2 転移試行数（1〜2件目安）">
            <input style={s.input} type="number" min={0} value={config.transfer_trial_count}
              onChange={e => update("transfer_trial_count", e.target.value)} />
          </Field>
          <Field label="フェーズ1のうち対照ペアを混ぜる件数">
            <input style={s.input} type="number" min={0} value={config.contrastive_pair_count}
              onChange={e => update("contrastive_pair_count", e.target.value)} />
          </Field>
          <Field label="条件の割り当て単位">
            <select style={s.input} value={config.condition_assignment_mode}
              onChange={e => update("condition_assignment_mode", e.target.value)}>
              <option value="participant">参加者単位で固定</option>
              <option value="trial">試行単位でランダム化</option>
            </select>
          </Field>
          <Field label="実験群(experimental)の割合">
            <input style={s.input} type="number" min={0} max={1} step={0.1} value={config.condition_ratio}
              onChange={e => update("condition_ratio", e.target.value)} />
          </Field>

          <button style={s.saveBtn} onClick={save} disabled={isSaving}>
            {isSaving ? "保存中…" : "保存する"}
          </button>
        </div>
      )}
    </Section>
  );
}

// ── 対照ペア一覧 ──────────────────────────────────────────
function ContrastivePairsSection() {
  const [pairs, setPairs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API}/contrastive-pairs?top_n=10`)
      .then(res => (res.ok ? res.json() : Promise.reject(new Error("対照ペアの取得に失敗しました"))))
      .then(json => setPairs(json.pairs || []))
      .catch(err => setError(err.message))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <Section title="対照ペア（構造指標の距離が大きい順）">
      {isLoading && <p style={s.status}>読み込み中…</p>}
      {error && <p style={s.statusError}>{error}</p>}
      {!isLoading && !error && pairs.length === 0 && (
        <p style={s.status}>StyleProfileを持つ参加者が2人以上いません。</p>
      )}
      {!isLoading && pairs.length > 0 && (
        <table style={s.table}>
          <thead>
            <tr style={s.tr}>
              <th style={s.th}>参加者A</th>
              <th style={s.th}>参加者B</th>
              <th style={s.th}>正規化距離</th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((p, i) => (
              <tr key={i} style={s.tr}>
                <td style={s.td}>{p.participant_a}</td>
                <td style={s.td}>{p.participant_b}</td>
                <td style={s.td}>{p.distance.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

// ── 割り当て生成・一覧 ─────────────────────────────────────
function AssignmentSection() {
  const [assignments, setAssignments] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [force, setForce] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    setIsLoading(true);
    fetch(`${API}/assignment`)
      .then(res => (res.ok ? res.json() : Promise.reject(new Error("割り当ての取得に失敗しました"))))
      .then(json => setAssignments(json.assignments || []))
      .catch(err => setError(err.message))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

  const toggle = (pid) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid); else next.add(pid);
      return next;
    });
  };

  const generate = async () => {
    setIsGenerating(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API}/assignment/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          participant_ids: selected.size > 0 ? Array.from(selected) : null,
          force,
        }),
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) throw new Error(json?.detail || "生成に失敗しました");
      setResult(json);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  const grouped = {};
  for (const a of assignments) {
    (grouped[a.participant_id] ||= []).push(a);
  }

  return (
    <Section title="試行割り当て">
      <div style={s.assignGenRow}>
        <div style={s.participantPicker}>
          {PARTICIPANT_IDS.filter(pid => pid !== PROTOTYPE_PARTICIPANT_ID).map(pid => (
            <button
              key={pid}
              style={{ ...s.pidChip, ...(selected.has(pid) ? s.pidChipSelected : {}) }}
              onClick={() => toggle(pid)}
            >
              {pid}
            </button>
          ))}
        </div>
        <label style={s.forceLabel}>
          <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
          既存データがあっても上書きする(force)
        </label>
        <button style={s.saveBtn} onClick={generate} disabled={isGenerating}>
          {isGenerating ? "生成中…" : selected.size > 0 ? `選択した${selected.size}人を生成` : "全員分を生成"}
        </button>
      </div>

      {error && <p style={s.statusError}>{error}</p>}
      {result && (
        <p style={s.statusOk}>
          生成: {result.generated.join(", ") || "なし"} / スキップ（収集済みデータあり）: {result.skipped.join(", ") || "なし"}
        </p>
      )}

      {isLoading && <p style={s.status}>読み込み中…</p>}
      {!isLoading && Object.keys(grouped).length === 0 && (
        <p style={s.status}>まだ割り当てがありません。上のボタンから生成してください。</p>
      )}
      {!isLoading && Object.keys(grouped).length > 0 && (
        <div style={s.assignmentGrid}>
          {Object.entries(grouped).map(([pid, rows]) => (
            <div key={pid} style={s.assignmentCard}>
              <div style={s.assignmentCardTitle}>{pid}</div>
              {rows.map(r => (
                <div key={r.owner_id} style={s.assignmentRow}>
                  <span style={s.assignmentTrial}>#{r.trial_index + 1}</span>
                  <span>{r.owner_id}</span>
                  <span style={s.assignmentPhase}>{r.phase}</span>
                  <span style={s.assignmentCondition(r.condition)}>{r.condition}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

// ── 進捗 ──────────────────────────────────────────────
function ProgressSection() {
  const [progress, setProgress] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API}/progress`)
      .then(res => (res.ok ? res.json() : Promise.reject(new Error("進捗の取得に失敗しました"))))
      .then(json => setProgress(json.progress || []))
      .catch(err => setError(err.message))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <Section title="進捗">
      {isLoading && <p style={s.status}>読み込み中…</p>}
      {error && <p style={s.statusError}>{error}</p>}
      {!isLoading && !error && progress.length === 0 && <p style={s.status}>まだ割り当てがありません。</p>}
      {!isLoading && progress.length > 0 && (
        <table style={s.table}>
          <thead>
            <tr style={s.tr}>
              <th style={s.th}>参加者</th>
              <th style={s.th}>フェーズ1</th>
              <th style={s.th}>フェーズ2（転移）</th>
            </tr>
          </thead>
          <tbody>
            {progress.map(p => (
              <tr key={p.participant_id} style={s.tr}>
                <td style={s.td}>{p.participant_id}</td>
                <td style={s.td}>{p.phase1_completed} / {p.phase1_total}</td>
                <td style={s.td}>{p.phase2_completed} / {p.phase2_total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

// ── エクスポート ────────────────────────────────────────
function ExportSection() {
  return (
    <Section title="エクスポート">
      <div style={s.exportRow}>
        <a style={s.exportLink} href={`${API}/export.csv`}>GuessRecordをCSVでダウンロード</a>
        <a style={s.exportLink} href={`${API}/export.json`} target="_blank" rel="noreferrer">JSONで開く</a>
      </div>
    </Section>
  );
}

// ── 共通パーツ ──────────────────────────────────────────
function Section({ title, children }) {
  return (
    <div style={s.section}>
      <div style={s.sectionTitle}>{title}</div>
      {children}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label style={s.field}>
      <span style={s.fieldLabel}>{label}</span>
      {children}
    </label>
  );
}

const s = {
  scrollArea: {
    height: "100%", overflowY: "auto", boxSizing: "border-box",
    maxWidth: 980, margin: "0 auto", padding: "0 28px 40px",
  },
  header: { marginBottom: 18, paddingTop: 20 },
  title: { fontSize: 22, fontWeight: 700, color: "#2a1f0e", margin: "0 0 6px" },
  subtitle: { fontSize: 13, color: "#8a7a63", lineHeight: 1.6, margin: 0 },

  status: { color: "#888", fontSize: 13 },
  statusError: { color: "#c9506a", fontSize: 13 },
  statusOk: { color: "#2f7a4f", fontSize: 13 },

  section: {
    marginTop: 22, paddingTop: 18, borderTop: "1px solid #ede8da",
  },
  sectionTitle: { fontSize: 15, fontWeight: 700, color: "#2a1f0e", marginBottom: 10 },

  configGrid: { display: "flex", flexDirection: "column", gap: 10, maxWidth: 420 },
  field: { display: "flex", flexDirection: "column", gap: 4 },
  fieldLabel: { fontSize: 12, color: "#8a7a63" },
  input: {
    border: "1px solid #e5ded0", borderRadius: 8, padding: "6px 10px",
    fontSize: 13, background: "#fff", color: "#2a1f0e",
  },
  saveBtn: {
    alignSelf: "flex-start", border: "1px solid #c9a84c", borderRadius: 999, padding: "7px 16px",
    fontSize: 13, fontWeight: 700, color: "#8a5a1f", background: "#fdeecb", cursor: "pointer",
  },

  table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  tr: { borderBottom: "1px solid #f0ebdd" },
  th: { textAlign: "left", padding: "6px 10px", color: "#8a7a63", fontWeight: 700, fontSize: 11.5 },
  td: { padding: "6px 10px", color: "#2a1f0e" },

  assignGenRow: { display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 },
  participantPicker: { display: "flex", flexWrap: "wrap", gap: 4 },
  pidChip: {
    border: "1px solid #e5ded0", borderRadius: 999, padding: "3px 10px",
    fontSize: 11.5, background: "#fff", color: "#5a4a33", cursor: "pointer",
  },
  pidChipSelected: { background: "#c9a84c", color: "#fff", borderColor: "#c9a84c" },
  forceLabel: { display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "#8a7a63" },

  assignmentGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 },
  assignmentCard: { border: "1px solid #e5ded0", borderRadius: 10, padding: "10px 12px", background: "#fff" },
  assignmentCardTitle: { fontSize: 13, fontWeight: 700, color: "#2a1f0e", marginBottom: 6 },
  assignmentRow: { display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, color: "#5a4a33", padding: "2px 0" },
  assignmentTrial: { color: "#9a8b76", width: 22, flexShrink: 0 },
  assignmentPhase: { marginLeft: "auto", color: "#8a7a63" },
  assignmentCondition: (cond) => ({
    fontSize: 10, fontWeight: 700, borderRadius: 999, padding: "1px 8px",
    color: cond === "experimental" ? "#8a5a1f" : cond === "control" ? "#3a6a52" : "#5a5a8a",
    background: cond === "experimental" ? "#fdeecb" : cond === "control" ? "#e3f3ea" : "#eceafc",
  }),

  exportRow: { display: "flex", gap: 14 },
  exportLink: {
    border: "1px solid #c9a84c", borderRadius: 999, padding: "7px 16px",
    fontSize: 13, fontWeight: 700, color: "#8a5a1f", background: "#fdeecb",
    textDecoration: "none",
  },
};
