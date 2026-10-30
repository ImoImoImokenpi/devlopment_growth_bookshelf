// 全ページ共通の見出し。タイトルの書体・サイズ・色、説明文、右側の
// コントロール欄の並びをここに集約する。ページごとの余白・最大幅・背景色
// といった「殻」は各ページ側の責務のままにして、ここでは見出しの
// タイポグラフィとレイアウトだけを統一する。
//
// 左にタイトルと説明文、右にコントロールを並べる。右側の高さに関係なく
// タイトル・説明文の位置が変わらないよう、右側は左のブロックに対して縦中央にそろえる。
export default function PageHeader({ title, sub, right }) {
  return (
    <div style={s.wrap}>
      <div style={s.text}>
        <div style={s.title}>{title}</div>
        {sub && <p style={s.sub}>{sub}</p>}
      </div>
      {right && <div style={s.right}>{right}</div>}
    </div>
  );
}

const s = {
  wrap: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    gap: 16, flexWrap: "wrap", marginBottom: 16,
  },
  text: { minWidth: 0 },
  title: { fontSize: 22, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", letterSpacing: "0.04em" },
  right: { display: "flex", alignItems: "center", gap: 14 },
  sub: { fontSize: 12.5, color: "#9a8b76", margin: "4px 0 0", lineHeight: 1.6 },
};
