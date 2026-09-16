// フェーズ2 (a) 優先度質問。単一選択のみを扱う小さなモーダル。
//
// (b) 区切り確認は、モーダル内に別画面を再現するのをやめ、実際の本棚
// （SpineShelfView）に「区切り確認モード」を追加して直接タップさせる方式に
// 変更した（Home.js / SpineShelfView.js 側を参照）。このモーダルは
// (a) に回答したら閉じ、呼び出し側（IntentCheckEntry）がそのまま
// 本棚を区切り確認モードに切り替える。
//
// 重要: このモーダルは PlacementProfile など「配置から推定した暗黙の優先度」
// を一切取得・表示しない。アンカリング防止のため、意図的にそれらのAPIへは
// 触れないこと自体を設計上のガードにしている。
import { useCallback, useEffect, useState } from "react";

const API = "http://localhost:8000";

const PRIORITY_ORDER = ["height", "genre", "color", "author", "interest", "none"];

export default function IntentCheckModal({ open, onClose, onAnswered }) {
  const [choices, setChoices] = useState({});
  const [selectedChoice, setSelectedChoice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoaded(false);
    setSelectedChoice(null);
    fetch(`${API}/intent-survey/priority`)
      .then(res => res.json())
      .then(data => setChoices(data.choices || {}))
      .finally(() => setLoaded(true));
  }, [open]);

  const submitPriority = useCallback(async () => {
    if (!selectedChoice) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/intent-survey/priority`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choice: selectedChoice }),
      });
      if (res.ok) {
        onAnswered?.(selectedChoice);
        onClose();
      }
    } finally {
      setBusy(false);
    }
  }, [selectedChoice, onAnswered, onClose]);

  if (!open) return null;

  return (
    <div style={s.overlay}>
      <div style={s.modal}>
        {!loaded ? (
          <div style={s.status}>読み込み中…</div>
        ) : (
          <>
            <h3 style={s.title}>本棚を並べるとき、一番意識したのは何ですか?</h3>
            <p style={s.hint}>1つだけ選んでください</p>
            <div style={s.optionList}>
              {PRIORITY_ORDER.map(key => (
                <button
                  key={key}
                  style={{ ...s.option, ...(selectedChoice === key ? s.optionActive : {}) }}
                  onClick={() => setSelectedChoice(key)}
                >
                  {choices[key] || key}
                </button>
              ))}
            </div>
            <div style={s.footer}>
              <button style={s.linkBtn} onClick={onClose}>あとで答える</button>
              <button
                style={{ ...s.primaryBtn, ...(!selectedChoice || busy ? s.btnDisabled : {}) }}
                onClick={submitPriority}
                disabled={!selectedChoice || busy}
              >
                回答する
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const s = {
  overlay: {
    position: "fixed", inset: 0, background: "rgba(30,24,12,0.45)",
    display: "flex", justifyContent: "center", alignItems: "center", zIndex: 6000,
  },
  modal: {
    background: "#fffdf7", borderRadius: 16, padding: "26px 28px",
    width: "min(420px, 90vw)", boxShadow: "0 20px 50px rgba(0,0,0,0.25)",
    border: "1px solid #ede8da",
  },
  status: { fontSize: 13, color: "#9a8b76", textAlign: "center", padding: "20px 0" },
  title: { fontSize: 15, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", lineHeight: 1.5, marginBottom: 6 },
  hint: { fontSize: 12, color: "#9a8b76", marginBottom: 16 },
  optionList: { display: "flex", flexDirection: "column", gap: 8 },
  option: {
    textAlign: "left", padding: "10px 14px", borderRadius: 10,
    border: "1px solid #e5ded0", background: "#fff", color: "#2a1f0e",
    fontSize: 13, cursor: "pointer", transition: "all 0.15s",
  },
  optionActive: { borderColor: "#c9a84c", background: "#fdf6e3", fontWeight: 700 },
  footer: { display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20 },
  linkBtn: { background: "none", border: "none", color: "#9a8b76", fontSize: 12, cursor: "pointer", textDecoration: "underline" },
  primaryBtn: {
    padding: "9px 20px", background: "#c9a84c", color: "#fff",
    border: "none", borderRadius: 10, fontSize: 13, fontWeight: 700, cursor: "pointer",
  },
  btnDisabled: { opacity: 0.5, cursor: "not-allowed" },
};
