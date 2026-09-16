// 自分らしさを表現できたかの評定(時期ごと) + ビッグファイブ簡易尺度(1回のみ)。
// 項目文言は仮のもの。確定させる際はここと backend/graph/uiab_experiment/bigfive.py
// の BIGFIVE_ITEM_KEYS を揃えて差し替える。
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { uiabGet, uiabPost, getUiabId } from "../../utils/uiabIdentity";

const PERIOD_LABEL = { period1: "時期1(数年前)", period2: "時期2(現在)" };

const BIGFIVE_ITEMS = [
  { key: "extraversion_1", label: "自分は活発で外向的だと思う" },
  { key: "extraversion_2_r", label: "自分は控えめで無口だと思う" },
  { key: "agreeableness_1_r", label: "自分は他人に対して批判的だと思う" },
  { key: "agreeableness_2", label: "自分は思いやりがあり温かいと思う" },
  { key: "conscientiousness_1", label: "自分はしっかりしていて、自己管理ができると思う" },
  { key: "conscientiousness_2_r", label: "自分はだらしないところがあると思う" },
  { key: "neuroticism_1", label: "自分は心配性で動揺しやすいと思う" },
  { key: "neuroticism_2_r", label: "自分は冷静で情緒が安定していると思う" },
  { key: "openness_1", label: "自分は新しい経験に対して開放的だと思う" },
  { key: "openness_2_r", label: "自分は発想が平凡だと思う" },
];

export default function UiabSelfReport() {
  const { period } = useParams();
  const navigate = useNavigate();
  const [needsBigFive, setNeedsBigFive] = useState(false);
  const [score, setScore] = useState(null);
  const [bigfive, setBigfive] = useState({});
  const [loaded, setLoaded] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!getUiabId()) { navigate("/Uiab"); return; }
    uiabGet("/uiab/status").then(status => {
      setNeedsBigFive(!status.bigfive_answered);
      setLoaded(true);
    }).catch(err => console.error(err));
  }, [navigate]);

  const canSubmit = score != null && (!needsBigFive || Object.keys(bigfive).length === BIGFIVE_ITEMS.length);

  const submit = async () => {
    setSubmitting(true);
    try {
      await uiabPost(`/uiab/${period}/self-expression`, { score });
      if (needsBigFive) {
        await uiabPost("/uiab/bigfive", { answers: bigfive });
      }
      navigate("/Uiab");
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (!loaded) return <div style={s.loading}>読み込み中…</div>;

  return (
    <div style={s.page}>
      <div style={s.card}>
        <h1 style={s.title}>{PERIOD_LABEL[period] || period}についての質問</h1>

        <div style={s.block}>
          <div style={s.question}>今作った本棚で、自分らしさを表現できたと感じますか?</div>
          <div style={s.scaleRow}>
            {[1, 2, 3, 4, 5, 6, 7].map(n => (
              <button
                key={n}
                style={{ ...s.scaleBtn, ...(score === n ? s.scaleBtnActive : {}) }}
                onClick={() => setScore(n)}
              >
                {n}
              </button>
            ))}
          </div>
          <div style={s.scaleLabels}>
            <span>まったくそう思わない</span>
            <span>とてもそう思う</span>
          </div>
        </div>

        {needsBigFive && (
          <div style={s.block}>
            <div style={s.subheading}>現在のあなたの性格について(最初の1回だけお聞きします)</div>
            {BIGFIVE_ITEMS.map(item => (
              <div key={item.key} style={s.bfRow}>
                <div style={s.bfQuestion}>{item.label}</div>
                <div style={s.scaleRow}>
                  {[1, 2, 3, 4, 5, 6, 7].map(n => (
                    <button
                      key={n}
                      style={{ ...s.scaleBtnSmall, ...(bigfive[item.key] === n ? s.scaleBtnActive : {}) }}
                      onClick={() => setBigfive(prev => ({ ...prev, [item.key]: n }))}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        <button style={s.submitBtn} onClick={submit} disabled={!canSubmit || submitting}>
          {submitting ? "送信中…" : "送信する"}
        </button>
      </div>
    </div>
  );
}

const s = {
  page: { minHeight: "100vh", background: "#f7f3ea", padding: "60px 24px", display: "flex", justifyContent: "center" },
  loading: { padding: 60, textAlign: "center", color: "#9a8b76", fontSize: 13 },
  card: { width: "min(560px, 100%)", background: "#fff", borderRadius: 16, padding: "28px 30px", boxShadow: "0 8px 30px rgba(0,0,0,0.08)" },
  title: { fontSize: 17, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", marginBottom: 20 },
  block: { marginBottom: 24 },
  question: { fontSize: 13.5, fontWeight: 600, color: "#2a1f0e", marginBottom: 10, lineHeight: 1.6 },
  subheading: { fontSize: 12, fontWeight: 700, color: "#c9a84c", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 14 },
  bfRow: { marginBottom: 14 },
  bfQuestion: { fontSize: 12.5, color: "#2a1f0e", marginBottom: 6, lineHeight: 1.5 },
  scaleRow: { display: "flex", gap: 6 },
  scaleBtn: {
    width: 36, height: 36, borderRadius: "50%", border: "1px solid #e5ded0",
    background: "#fff", color: "#8a7960", fontSize: 13, fontWeight: 700, cursor: "pointer",
  },
  scaleBtnSmall: {
    width: 28, height: 28, borderRadius: "50%", border: "1px solid #e5ded0",
    background: "#fff", color: "#8a7960", fontSize: 11, fontWeight: 700, cursor: "pointer",
  },
  scaleBtnActive: { background: "#c9a84c", color: "#fff", borderColor: "#c9a84c" },
  scaleLabels: { display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "#bbb", marginTop: 4 },
  submitBtn: {
    width: "100%", padding: 13, background: "#c9a84c", color: "#fff", border: "none",
    borderRadius: 10, fontSize: 14, fontWeight: 700, cursor: "pointer",
  },
};
