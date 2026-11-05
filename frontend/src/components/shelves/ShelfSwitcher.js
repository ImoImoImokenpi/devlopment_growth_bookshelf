// 育つ本棚の見出し列に置く「本棚の切り替え」と「本棚の管理」。
//
//   - 今開いている本棚の名前を押すと一覧が開き、別の本棚を開ける
//   - 「＋ 新しい本棚」で名前を付けて本棚をつくり、そのまま開く
//   - 「本棚の管理」で名前の変更・削除ができる（削除できるのは本が1冊もない本棚だけ）
import { useState } from "react";
import { useShelves } from "../../context/ShelvesContext";

export default function ShelfSwitcher() {
  const { shelves, activeShelf, activeScopeId, createShelf, openShelf } = useShelves();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [managing, setManaging] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const close = () => { setOpen(false); setCreating(false); setDraft(""); setError(null); };

  const submitCreate = async (e) => {
    e.preventDefault();
    if (!draft.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const shelf = await createShelf(draft);
      openShelf(shelf.scope_id); // つくった本棚をそのまま開く
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div style={s.wrap}>
      <button style={{ ...s.current, ...(open ? s.currentOpen : {}) }} onClick={() => (open ? close() : setOpen(true))} title="本棚を切り替える">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="3" y1="15" x2="21" y2="15" />
        </svg>
        <span style={s.currentName}>{activeShelf?.name || "本棚"}</span>
        <span style={s.caret}>▾</span>
      </button>

      {open && <div style={s.backdrop} onClick={close} />}
      {open && (
        <div style={s.menu}>
          <div style={s.sectionTitle}>本棚</div>
          {shelves.map(shelf => {
            const active = shelf.scope_id === activeScopeId;
            return (
              <button
                key={shelf.id}
                style={{ ...s.item, ...(active ? s.itemActive : {}) }}
                onClick={() => { if (!active) openShelf(shelf.scope_id); else close(); }}
              >
                <span style={s.check}>{active ? "✓" : ""}</span>
                <span style={s.itemName}>{shelf.name}</span>
                <span style={s.count}>{shelf.book_count}冊</span>
              </button>
            );
          })}

          <div style={s.divider} />
          {creating ? (
            <form onSubmit={submitCreate} style={s.createForm}>
              <input
                autoFocus
                value={draft}
                onChange={e => setDraft(e.target.value)}
                placeholder="本棚の名前（例: 書斎の本棚）"
                maxLength={30}
                style={s.input}
              />
              <div style={s.formRow}>
                <button type="button" style={s.ghostBtn} onClick={() => { setCreating(false); setDraft(""); setError(null); }}>やめる</button>
                <button type="submit" style={{ ...s.primaryBtn, ...(!draft.trim() || busy ? s.btnOff : {}) }} disabled={!draft.trim() || busy}>
                  {busy ? "つくっています…" : "つくって開く"}
                </button>
              </div>
              {error && <div style={s.error}>{error}</div>}
            </form>
          ) : (
            <button style={s.action} onClick={() => setCreating(true)}>＋ 新しい本棚</button>
          )}
          <button style={s.action} onClick={() => { close(); setManaging(true); }}>本棚の管理…</button>
        </div>
      )}

      {managing && <ShelfManager onClose={() => setManaging(false)} />}
    </div>
  );
}

// 本棚の管理（名前の変更・削除・開く）
function ShelfManager({ onClose }) {
  const { shelves, activeScopeId, renameShelf, deleteShelf, openShelf } = useShelves();
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const startEdit = (shelf) => { setEditingId(shelf.id); setDraft(shelf.name); setError(null); };

  const saveName = async (e, shelf) => {
    e.preventDefault();
    if (!draft.trim()) return;
    setBusyId(shelf.id);
    try {
      await renameShelf(shelf.id, draft);
      setEditingId(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (shelf) => {
    const ok = window.confirm(
      `「${shelf.name}」を消します。\n` +
      "この本棚でした対話・意味づけ・おすすめの記録も一緒に消え、元に戻せません。よろしいですか？"
    );
    if (!ok) return;
    setBusyId(shelf.id);
    setError(null);
    try {
      await deleteShelf(shelf.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={e => e.stopPropagation()} role="dialog" aria-label="本棚の管理">
        <div style={s.modalHead}>
          <div style={s.modalTitle}>本棚の管理</div>
          <button style={s.closeBtn} onClick={onClose} aria-label="閉じる">×</button>
        </div>
        <p style={s.note}>
          本棚ごとに、本の並び・意味づけ・対話・おすすめが分かれています。
          本をほかの本棚へ移すには、本を選んで右の「この本について」から移せます。
        </p>

        <div style={s.list}>
          {shelves.map(shelf => {
            const active = shelf.scope_id === activeScopeId;
            const canDelete = !shelf.is_default && shelf.book_count === 0;
            const deleteTip = shelf.is_default
              ? "最初の本棚は消せません"
              : shelf.book_count > 0 ? "本が残っている本棚は消せません。先に本をほかの本棚へ移してください" : "この本棚を消す";
            return (
              <div key={shelf.id} style={{ ...s.row, ...(active ? s.rowActive : {}) }}>
                {editingId === shelf.id ? (
                  <form onSubmit={e => saveName(e, shelf)} style={s.rowForm}>
                    <input autoFocus value={draft} onChange={e => setDraft(e.target.value)} maxLength={30} style={s.input} />
                    <button type="button" style={s.ghostBtn} onClick={() => setEditingId(null)}>やめる</button>
                    <button type="submit" style={{ ...s.primaryBtn, ...(!draft.trim() ? s.btnOff : {}) }} disabled={!draft.trim() || busyId === shelf.id}>保存</button>
                  </form>
                ) : (
                  <>
                    <div style={s.rowMain}>
                      <div style={s.rowName}>
                        {shelf.name}
                        {active && <span style={s.tag}>開いている本棚</span>}
                      </div>
                      <div style={s.rowMeta}>
                        {shelf.book_count}冊
                        {shelf.created_at ? ` ・ ${shelf.created_at.slice(0, 10)}につくった` : ""}
                      </div>
                    </div>
                    <div style={s.rowActions}>
                      {!active && <button style={s.smallBtn} onClick={() => openShelf(shelf.scope_id)}>開く</button>}
                      <button style={s.smallBtn} onClick={() => startEdit(shelf)}>名前を変える</button>
                      <button
                        style={{ ...s.smallBtn, ...s.dangerBtn, ...(!canDelete || busyId === shelf.id ? s.btnOff : {}) }}
                        onClick={() => canDelete && remove(shelf)}
                        disabled={!canDelete || busyId === shelf.id}
                        title={deleteTip}
                      >消す</button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
        {error && <div style={s.error}>{error}</div>}
      </div>
    </div>
  );
}

const s = {
  wrap: { position: "relative" },
  current: {
    display: "inline-flex", alignItems: "center", gap: 8, height: 40, padding: "0 14px",
    borderRadius: 999, border: "1px solid #e0d8c0", background: "#fff", color: "#4a3728",
    fontSize: 13.5, fontWeight: 700, cursor: "pointer", fontFamily: "inherit", maxWidth: 240,
  },
  currentOpen: { background: "#f5efdd", color: "#8a7030" },
  currentName: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  caret: { fontSize: 10, color: "#a08850" },
  backdrop: { position: "fixed", inset: 0, zIndex: 999 },
  menu: {
    position: "absolute", top: 48, right: 0, zIndex: 1000, minWidth: 260,
    background: "#fdfcf8", border: "1px solid #ede8da", borderRadius: 14, padding: "12px",
    boxShadow: "0 8px 32px rgba(0,0,0,0.12)", display: "flex", flexDirection: "column", gap: 2,
  },
  sectionTitle: { fontSize: 10, fontWeight: 700, color: "#c9a84c", letterSpacing: "0.1em", margin: "0 0 4px 6px" },
  item: {
    display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "8px 10px",
    border: "none", borderRadius: 8, background: "transparent", color: "#4a3728",
    fontSize: 13, fontWeight: 600, cursor: "pointer", textAlign: "left", fontFamily: "inherit",
  },
  itemActive: { background: "#f5efdd" },
  check: { width: 14, color: "#8a7030", fontWeight: 700 },
  itemName: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  count: { fontSize: 11.5, color: "#9a8a6a", fontWeight: 500 },
  divider: { height: 1, background: "#ede8da", margin: "8px 0" },
  action: {
    width: "100%", padding: "8px 10px", border: "none", borderRadius: 8, background: "transparent",
    color: "#8a7030", fontSize: 13, fontWeight: 700, cursor: "pointer", textAlign: "left", fontFamily: "inherit",
  },
  createForm: { display: "flex", flexDirection: "column", gap: 8, padding: "4px 4px 6px" },
  formRow: { display: "flex", justifyContent: "flex-end", gap: 6 },
  input: {
    flex: 1, minWidth: 0, padding: "8px 10px", borderRadius: 8, border: "1px solid #e0d8c0",
    fontSize: 13, fontFamily: "inherit", background: "#fff", color: "#4a3728",
  },
  primaryBtn: {
    padding: "7px 14px", borderRadius: 999, border: "none", background: "#c9a84c", color: "#fff",
    fontSize: 12.5, fontWeight: 700, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
  },
  ghostBtn: {
    padding: "7px 12px", borderRadius: 999, border: "1px solid #e0d8c0", background: "#fff", color: "#6b5a3e",
    fontSize: 12.5, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
  },
  btnOff: { opacity: 0.45, cursor: "default" },
  error: { color: "#c9506a", fontSize: 12, marginTop: 8 },
  overlay: {
    position: "fixed", inset: 0, zIndex: 3000, background: "rgba(40,30,15,0.35)",
    display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
  },
  modal: {
    width: "min(560px, 100%)", maxHeight: "80vh", overflowY: "auto", boxSizing: "border-box",
    background: "#fdfcf8", borderRadius: 16, padding: "20px 22px", boxShadow: "0 16px 48px rgba(0,0,0,0.25)",
  },
  modalHead: { display: "flex", alignItems: "center", justifyContent: "space-between" },
  modalTitle: { fontSize: 16, fontWeight: 700, color: "#4a3728" },
  closeBtn: { border: "none", background: "transparent", fontSize: 22, color: "#9a8a6a", cursor: "pointer", lineHeight: 1 },
  note: { fontSize: 12.5, color: "#7a6a4a", lineHeight: 1.6, margin: "8px 0 14px" },
  list: { display: "flex", flexDirection: "column", gap: 8 },
  row: {
    display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
    border: "1px solid #ede8da", borderRadius: 12, background: "#fff", flexWrap: "wrap",
  },
  rowActive: { borderColor: "#d9c48a", background: "#fffaf0" },
  rowMain: { flex: 1, minWidth: 140 },
  rowName: { fontSize: 14, fontWeight: 700, color: "#4a3728", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  rowMeta: { fontSize: 11.5, color: "#9a8a6a", marginTop: 2 },
  tag: { fontSize: 10.5, fontWeight: 700, color: "#8a7030", background: "#f5efdd", borderRadius: 999, padding: "2px 8px" },
  rowActions: { display: "flex", gap: 6, flexWrap: "wrap" },
  rowForm: { display: "flex", gap: 6, width: "100%", alignItems: "center" },
  smallBtn: {
    padding: "6px 12px", borderRadius: 999, border: "1px solid #e0d8c0", background: "#fff", color: "#6b5a3e",
    fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
  },
  dangerBtn: { color: "#c9506a", borderColor: "#f0c8d0" },
};
