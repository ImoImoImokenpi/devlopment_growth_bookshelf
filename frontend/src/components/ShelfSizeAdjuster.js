// 本棚ペインの幅（画面に対する割合）の調整。My本棚の設定ボタン
// （ShelfSettingsMenu）と、みんなの本棚の個別画面（ExploreShelf）の
// 両方から使う共通パーツ。値の保持自体は呼び出し側に任せる。
export const SHELF_WIDTH_MIN  = 30;
export const SHELF_WIDTH_MAX  = 50;
export const SHELF_WIDTH_STEP = 5;

export default function ShelfSizeAdjuster({ value, onChange }) {
  return (
    <div style={s.sizeRow}>
      <button
        onClick={() => onChange(Math.max(SHELF_WIDTH_MIN, value - SHELF_WIDTH_STEP))}
        style={{ ...s.sizeBtn, ...(value <= SHELF_WIDTH_MIN ? s.sizeBtnDisabled : {}) }}
        disabled={value <= SHELF_WIDTH_MIN}
        title="本棚を小さくする（圧迫感を減らす）"
      >
        －
      </button>
      <span style={s.sizeValue}>{value}%</span>
      <button
        onClick={() => onChange(Math.min(SHELF_WIDTH_MAX, value + SHELF_WIDTH_STEP))}
        style={{ ...s.sizeBtn, ...(value >= SHELF_WIDTH_MAX ? s.sizeBtnDisabled : {}) }}
        disabled={value >= SHELF_WIDTH_MAX}
        title="本棚を大きくする"
      >
        ＋
      </button>
    </div>
  );
}

const s = {
  sizeRow: {
    display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px",
  },
  sizeBtn: {
    width: "28px", height: "28px", borderRadius: "8px",
    border: "1px solid #e0d5b8", background: "#fff",
    color: "#4a3728", fontSize: "15px", fontWeight: "700",
    cursor: "pointer", lineHeight: 1,
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  sizeBtnDisabled: {
    opacity: 0.4, cursor: "not-allowed",
  },
  sizeValue: {
    fontSize: "13px", fontWeight: "700", color: "#2a1f0e",
    minWidth: "36px", textAlign: "center",
  },
};
