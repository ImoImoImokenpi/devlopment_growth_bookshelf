// 通常モード⇄グルーピングモードの切り替え。ViewModeToggle と同じピルの見た目にする。
// ユーザーに見せる文言では「グルーピング」のように具体的な操作が伝わる言葉を使い、
// 内部的な「意味付けモード」という呼び方はここでは出さない。
export default function ModeToggle({ mode, onChange }) {
  return (
    <div style={s.wrap}>
      <button
        style={{ ...s.btn, ...(mode === "normal" ? s.btnActive : {}) }}
        onClick={() => onChange("normal")}
        title="配置と閲覧のみ行えます"
      >
        通常
      </button>
      <button
        style={{ ...s.btn, ...(mode === "grouping" ? s.btnActive : {}) }}
        onClick={() => onChange("grouping")}
        title="本を選んでグループを作ったり整理したりできます"
      >
        グルーピング
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
