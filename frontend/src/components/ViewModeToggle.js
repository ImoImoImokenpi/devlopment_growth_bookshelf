// 背表紙表示⇄グリッド表示の切り替え。My本棚・みんなの本棚どちらの
// 画面でも使う共通パーツ。デフォルトは呼び出し側で "spine" にする。
// 配置（左上に浮かせる／見出し行に並べる等）は呼び出し側に任せるため、
// ここではピル自体の見た目だけを持つ（positionは指定しない）。
export default function ViewModeToggle({ mode, onChange }) {
  return (
    <div style={s.wrap}>
      <button
        style={{ ...s.btn, ...(mode === "spine" ? s.btnActive : {}) }}
        onClick={() => onChange("spine")}
        title="背表紙表示"
      >
        背表紙
      </button>
      <button
        style={{ ...s.btn, ...(mode === "grid" ? s.btnActive : {}) }}
        onClick={() => onChange("grid")}
        title="グリッド表示"
      >
        グリッド
      </button>
    </div>
  );
}

const s = {
  wrap: {
    display: "flex", gap: 2, padding: 3, borderRadius: 999,
    background: "rgba(255,255,255,0.92)", backdropFilter: "blur(6px)",
    WebkitBackdropFilter: "blur(6px)",
    border: "1px solid rgba(0,0,0,0.08)", boxShadow: "0 2px 10px rgba(0,0,0,0.08)",
  },
  btn: {
    padding: "5px 12px", borderRadius: 999, border: "none",
    background: "transparent", color: "#8a7a63", fontSize: 11.5, fontWeight: 600,
    cursor: "pointer", transition: "background 0.15s, color 0.15s",
  },
  btnActive: { background: "#c9a84c", color: "#fff" },
};
