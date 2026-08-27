// 全ページ共通の見出し。タイトルの書体・サイズ・色、説明文、右側の
// コントロール欄の並びをここに集約する。ページごとの余白・最大幅・背景色
// といった「殻」は各ページ側の責務のままにして、ここでは見出しの
// タイポグラフィとレイアウトだけを統一する。
export default function PageHeader({ title, sub, right }) {
  return (
    <div style={s.wrap}>
      <div style={s.top}>
        <div style={s.title}>{title}</div>
        {right && <div style={s.right}>{right}</div>}
      </div>
      {sub && <p style={s.sub}>{sub}</p>}
    </div>
  );
}

const s = {
  wrap: { marginBottom: 16 },
  top: {
    display: "flex", alignItems: "flex-start", justifyContent: "space-between",
    gap: 12, flexWrap: "wrap",
  },
  title: { fontSize: 20, fontWeight: 700, color: "#222" },
  right: { display: "flex", alignItems: "center", gap: 14 },
  sub: { fontSize: 13, color: "#777", margin: "6px 0 0", lineHeight: 1.6 },
};
