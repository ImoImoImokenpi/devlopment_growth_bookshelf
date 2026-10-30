// 育つ本棚の見出し列に置く「棚の設定」ボタン。押すと下にメニューが開く。
// （以前は画面右下に固定したFABだったが、本棚から離れて浮いて見えたため見出し列へ移した）
//
// 以前はここに段の増減・本棚サイズの調整だけがあったが、背表紙⇄グリッドの
// 表示切り替え専用のトグルバーを画面上に別途置くと本棚と重なって邪魔になる
// ため、この設定ボタンの中に「表示」セクションとしてまとめて入れた。
import { useContext, useState } from "react";
import { MyBookshelfContext } from "../context/MyBookshelfContext";
import { useShelfWorkspace } from "../context/ShelfWorkspaceContext";
import ViewModeToggle from "./ViewModeToggle";
import ShelfSizeAdjuster from "./ShelfSizeAdjuster";

export default function ShelfSettingsMenu({ viewMode, onViewModeChange }) {
  const { addShelfRow, removeShelfRow } = useContext(MyBookshelfContext);
  const { shelfWidthPct, setShelfWidthPct } = useShelfWorkspace();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div style={s.wrap}>
      <button
        style={{ ...s.fab, ...(isOpen ? s.fabOpen : {}) }}
        onClick={() => setIsOpen(v => !v)}
        title="棚の設定"
        aria-label="棚の設定"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>
          <line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>
          <line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>
          <line x1="1" y1="14" x2="7" y2="14"/>
          <line x1="9" y1="8" x2="15" y2="8"/>
          <line x1="17" y1="16" x2="23" y2="16"/>
        </svg>
      </button>

      {isOpen && <div style={s.backdrop} onClick={() => setIsOpen(false)} />}
      {isOpen && (
        <div style={s.floatingPanel}>
          <div style={s.panelSectionTitle}>表示</div>
          <ViewModeToggle mode={viewMode} onChange={onViewModeChange} />

          <div style={s.panelDivider} />

          <div style={s.panelSectionTitle}>段の増減</div>
          <button
            onClick={addShelfRow}
            style={s.panelBtn}
            onMouseEnter={e => e.currentTarget.style.background = "#f5f0e8"}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            段を追加
          </button>
          <button
            onClick={removeShelfRow}
            style={{ ...s.panelBtn, color: "#c9506a" }}
            onMouseEnter={e => e.currentTarget.style.background = "#fff0f2"}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            段を削除
          </button>

          <div style={s.panelDivider} />

          <div style={s.panelSectionTitle}>本棚サイズの調整</div>
          <ShelfSizeAdjuster value={shelfWidthPct} onChange={setShelfWidthPct} />
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: { position: "relative" },
  fab: {
    width: "40px", height: "40px", borderRadius: "50%",
    border: "1px solid #e0d8c0", backgroundColor: "#fff", color: "#6b5a3e",
    display: "flex", justifyContent: "center", alignItems: "center",
    cursor: "pointer", transition: "background 0.15s, color 0.15s",
  },
  fabOpen: { backgroundColor: "#f5efdd", color: "#8a7030" },
  backdrop: { position: "fixed", inset: 0, zIndex: 999 },
  floatingPanel: {
    position: "absolute", top: "48px", right: 0,
    backgroundColor: "#fdfcf8",
    border: "1px solid #ede8da",
    padding: "14px 16px",
    borderRadius: "14px",
    boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
    display: "flex", flexDirection: "column",
    gap: 6,
    minWidth: "200px",
    zIndex: 1000,
  },
  panelSectionTitle: {
    fontSize: "10px", fontWeight: "700", color: "#c9a84c",
    letterSpacing: "0.1em", textTransform: "uppercase",
    marginBottom: "4px",
  },
  panelDivider: {
    height: "1px", background: "#ede8da", margin: "10px 0",
  },
  panelBtn: {
    display: "flex", alignItems: "center", gap: "8px",
    padding: "8px 10px", borderRadius: "8px",
    border: "none", background: "transparent",
    color: "#4a3728", fontSize: "13px", fontWeight: "600",
    cursor: "pointer", textAlign: "left", width: "100%",
    transition: "background 0.15s",
  },
};
