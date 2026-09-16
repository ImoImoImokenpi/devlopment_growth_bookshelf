// 観察者評価画面。表示する本棚がどちらの群由来かは画面上に一切出さない
// (バックエンドのレスポンス自体に含まれていないので、出しようがない)。
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uiabGet, uiabPost, getUiabId } from "../../utils/uiabIdentity";
import UiabShelfViewer from "../../components/uiab/UiabShelfViewer";

const GUESS_ITEMS = [
  { key: "extraversion", label: "外向的だと思う" },
  { key: "agreeableness", label: "協調的だと思う" },
  { key: "conscientiousness", label: "しっかり者だと思う" },
  { key: "neuroticism", label: "情緒が不安定だと思う" },
  { key: "openness", label: "新しい物事に対して開放的だと思う" },
];

export default function UiabObserve() {
  const navigate = useNavigate();
  const [trial, setTrial] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scores, setScores] = useState({});
  const [freeText, setFreeText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadNext = useCallback(() => {
    setLoading(true);
    setScores({});
    setFreeText("");
    uiabGet("/uiab/observe/next")
      .then(setTrial)
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!getUiabId()) { navigate("/Uiab"); return; }
    loadNext();
  }, [loadNext, navigate]);

  const canSubmit = GUESS_ITEMS.every(item => scores[item.key] != null);

  const submit = async () => {
    setSubmitting(true);
    try {
      for (const item of GUESS_ITEMS) {
        await uiabPost("/uiab/observe/guess", {
          owner_id: trial.owner_id, owner_period: trial.owner_period,
          item_key: item.key, score: scores[item.key],
        });
      }
      if (freeText.trim()) {
        await uiabPost("/uiab/observe/guess", {
          owner_id: trial.owner_id, owner_period: trial.owner_period,
          item_key: "free_text", text: freeText.trim(),
        });
      }
      loadNext();
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div style={s.loading}>読み込み中…</div>;
  if (!trial || trial.done) {
    return (
      <div style={s.page}>
        <div style={s.card}>
          <h1 style={s.title}>ご協力ありがとうございました</h1>
          <p style={s.text}>割り当てられた評価はすべて完了しました。</p>
        </div>
      </div>
    );
  }

  return (
    <div style={s.page}>
      <div style={s.layout}>
        <div style={s.shelfPane}>
          <UiabShelfViewer shelf={trial.shelf} groups={trial.groups} />
        </div>
        <div style={s.formPane}>
          <h2 style={s.formTitle}>この本棚の持ち主はどんな人だと思いますか?</h2>
          {GUESS_ITEMS.map(item => (
            <div key={item.key} style={s.itemRow}>
              <div style={s.itemLabel}>{item.label}</div>
              <div style={s.scaleRow}>
                {[1, 2, 3, 4, 5, 6, 7].map(n => (
                  <button
                    key={n}
                    style={{ ...s.scaleBtn, ...(scores[item.key] === n ? s.scaleBtnActive : {}) }}
                    onClick={() => setScores(prev => ({ ...prev, [item.key]: n }))}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <textarea
            style={s.freeText}
            value={freeText}
            onChange={e => setFreeText(e.target.value)}
            placeholder="その他、気づいたことがあれば自由に書いてください(任意)"
          />
          <button style={s.submitBtn} onClick={submit} disabled={!canSubmit || submitting}>
            {submitting ? "送信中…" : "送信して次へ"}
          </button>
        </div>
      </div>
    </div>
  );
}

const s = {
  page: { minHeight: "100vh", background: "#f7f3ea", padding: "24px 28px 60px" },
  loading: { padding: 60, textAlign: "center", color: "#9a8b76", fontSize: 13 },
  card: {
    width: "min(420px, 100%)", margin: "60px auto", background: "#fff", borderRadius: 16,
    padding: "32px 28px", textAlign: "center", boxShadow: "0 8px 30px rgba(0,0,0,0.08)",
  },
  title: { fontSize: 17, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", marginBottom: 10 },
  text: { fontSize: 13, color: "#8a7960" },
  layout: { display: "flex", gap: 22, alignItems: "flex-start" },
  shelfPane: { flex: 1, minWidth: 0 },
  formPane: {
    width: 320, flexShrink: 0, background: "#fff", borderRadius: 14, padding: 18,
    border: "1px solid #ede8da", display: "flex", flexDirection: "column", gap: 14,
  },
  formTitle: { fontSize: 14, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", lineHeight: 1.5 },
  itemRow: { display: "flex", flexDirection: "column", gap: 6 },
  itemLabel: { fontSize: 12, color: "#2a1f0e" },
  scaleRow: { display: "flex", gap: 5 },
  scaleBtn: {
    width: 28, height: 28, borderRadius: "50%", border: "1px solid #e5ded0",
    background: "#fff", color: "#8a7960", fontSize: 11, fontWeight: 700, cursor: "pointer",
  },
  scaleBtnActive: { background: "#c9a84c", color: "#fff", borderColor: "#c9a84c" },
  freeText: {
    minHeight: 60, padding: 9, borderRadius: 8, border: "1px solid #e5ded0",
    fontSize: 12, lineHeight: 1.6, fontFamily: "inherit", resize: "vertical",
  },
  submitBtn: {
    padding: 12, background: "#c9a84c", color: "#fff", border: "none",
    borderRadius: 10, fontSize: 13, fontWeight: 700, cursor: "pointer",
  },
};
