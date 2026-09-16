// グルーピング機能。新UI/旧UIで機能を揃えるための共通コンポーネント。
import { useEffect, useState, useCallback } from "react";
import { uiabGet, uiabPost, uiabDelete } from "../../utils/uiabIdentity";

export default function UiabGroupingPanel({ period, selectedIsbns, onCleared }) {
  const [groups, setGroups] = useState([]);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    uiabGet(`/uiab/${period}/groups`).then(setGroups).catch(err => console.error(err));
  }, [period]);

  useEffect(() => { load(); }, [load]);

  const createGroup = async () => {
    const text = label.trim();
    if (!text || selectedIsbns.length === 0) return;
    setBusy(true);
    try {
      await uiabPost(`/uiab/${period}/groups`, { label: text, isbns: selectedIsbns });
      setLabel("");
      onCleared?.();
      load();
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  };

  const removeGroup = async (groupId) => {
    try {
      await uiabDelete(`/uiab/${period}/groups/${groupId}`);
      load();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div style={s.wrap}>
      <div style={s.heading}>グループ</div>

      {selectedIsbns.length > 0 && (
        <div style={s.createRow}>
          <input
            style={s.input}
            value={label}
            onChange={e => setLabel(e.target.value)}
            placeholder={`選択中の${selectedIsbns.length}冊をグループに`}
            onKeyDown={e => e.key === "Enter" && createGroup()}
          />
          <button style={s.createBtn} onClick={createGroup} disabled={busy || !label.trim()}>作成</button>
        </div>
      )}

      {groups.length === 0 ? (
        <div style={s.empty}>まだグループはありません</div>
      ) : (
        <div style={s.list}>
          {groups.map(g => (
            <div key={g.group_id} style={s.groupRow}>
              <div>
                <div style={s.groupLabel}>{g.label}</div>
                <div style={s.groupMembers}>{g.members.map(m => m.title || m.isbn).join(" / ")}</div>
              </div>
              <button style={s.deleteBtn} onClick={() => removeGroup(g.group_id)}>✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: { display: "flex", flexDirection: "column", gap: 8 },
  heading: { fontSize: 10.5, fontWeight: 700, color: "#c9a84c", textTransform: "uppercase", letterSpacing: "0.05em" },
  createRow: { display: "flex", gap: 6 },
  input: { flex: 1, padding: "7px 9px", borderRadius: 8, border: "1px solid #d0c4a8", fontSize: 12, outline: "none" },
  createBtn: {
    padding: "7px 12px", background: "#c9a84c", color: "#fff", border: "none",
    borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: "pointer",
  },
  empty: { fontSize: 11.5, color: "#bbb" },
  list: { display: "flex", flexDirection: "column", gap: 6 },
  groupRow: {
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    padding: "7px 10px", borderRadius: 8, border: "1px solid #ede8da", background: "#fff", gap: 8,
  },
  groupLabel: { fontSize: 12, fontWeight: 700, color: "#2a1f0e" },
  groupMembers: { fontSize: 10.5, color: "#9a8b76", marginTop: 2 },
  deleteBtn: { border: "none", background: "none", color: "#bbb", cursor: "pointer", fontSize: 11 },
};
