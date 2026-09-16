// グループ削除・統合など、元に戻しにくい操作の直後に出すUndoトースト。
// このコードベースには依存ライブラリを使ったトースト機構が無いので、自前の
// 最小実装にする（ShelfWorkspaceContext の toast state をそのまま表示するだけ）。
import { useEffect } from "react";

const AUTO_DISMISS_MS = 6000;

export default function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(onDismiss, AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  if (!toast) return null;

  return (
    <div style={s.wrap}>
      <span style={s.message}>{toast.message}</span>
      {toast.actionLabel && (
        <button
          style={s.actionBtn}
          onClick={() => { toast.onAction?.(); onDismiss(); }}
        >
          {toast.actionLabel}
        </button>
      )}
      <button style={s.closeBtn} onClick={onDismiss} title="閉じる">✕</button>
    </div>
  );
}

const s = {
  wrap: {
    position: "fixed", bottom: "30px", left: "50%", transform: "translateX(-50%)",
    background: "#2a1f0e", color: "#fff",
    padding: "10px 12px 10px 16px", borderRadius: 12,
    boxShadow: "0 8px 30px rgba(0,0,0,0.25)",
    display: "flex", alignItems: "center", gap: 12,
    zIndex: 3000, fontSize: 12.5,
  },
  message: { whiteSpace: "nowrap" },
  actionBtn: {
    border: "none", background: "#c9a84c", color: "#fff",
    borderRadius: 999, padding: "5px 12px", fontWeight: 700,
    fontSize: 11.5, cursor: "pointer", flexShrink: 0,
  },
  closeBtn: {
    border: "none", background: "transparent", color: "rgba(255,255,255,0.6)",
    cursor: "pointer", fontSize: 11, flexShrink: 0,
  },
};
