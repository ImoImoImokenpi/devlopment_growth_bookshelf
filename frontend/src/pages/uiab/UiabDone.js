export default function UiabDone() {
  return (
    <div style={s.page}>
      <div style={s.card}>
        <h1 style={s.title}>ご協力ありがとうございました</h1>
        <p style={s.text}>すべての回答が記録されました。このままブラウザを閉じて構いません。</p>
      </div>
    </div>
  );
}

const s = {
  page: { minHeight: "100vh", background: "#f7f3ea", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 },
  card: { width: "min(420px, 100%)", background: "#fff", borderRadius: 16, padding: "36px 30px", textAlign: "center", boxShadow: "0 8px 30px rgba(0,0,0,0.08)" },
  title: { fontSize: 17, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", marginBottom: 10 },
  text: { fontSize: 13, color: "#8a7960", lineHeight: 1.7 },
};
