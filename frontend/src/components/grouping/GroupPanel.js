// 左ペイン「グループ整理」の中身。グルーピングモード専用。
//
// 「グループ」は新規のデータ種別ではなく、既存の意味づけ(Concept)をそのまま使う。
// ここではグループの一覧・ハイライト・リネーム・メンバー削除・削除・統合を扱う。
//
// 棚(SpineShelfView)からのドラッグインを受け取れるよう、各行のルート要素に
// className="group-panel-row" と data-concept-id / data-group-name を付けている
// （SpineShelfView 側が document.querySelectorAll でこのDOMを直接見に行く）。
import { useCallback, useEffect, useState } from "react";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";

const API = "http://localhost:8000";

export default function GroupPanel() {
  const {
    groupsVersion, bumpGroupsVersion,
    conceptHighlights, toggleGroupHighlight, clearGroupHighlight,
    showToast,
  } = useShelfWorkspace();

  const [groups, setGroups] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState("");
  const [dragSourceId, setDragSourceId] = useState(null);
  const [error, setError] = useState(null);

  const fetchGroups = useCallback(() => {
    setIsLoading(true);
    fetch(`${API}/knowledge_graph/groups`)
      .then(res => (res.ok ? res.json() : { groups: [] }))
      .then(data => setGroups(data.groups || []))
      .catch(err => { setError("グループ一覧の取得に失敗しました"); console.error(err); })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => { fetchGroups(); }, [fetchGroups, groupsVersion]);

  const startEdit = useCallback((g) => {
    setEditingId(g.concept_id);
    setEditText(g.text);
  }, []);

  const commitEdit = useCallback(async () => {
    const concept = groups.find(g => g.concept_id === editingId);
    const nextText = editText.trim();
    setEditingId(null);
    if (!concept || !nextText || nextText === concept.text) return;

    const collision = groups.find(g => g.concept_id !== concept.concept_id && g.text === nextText);
    if (collision) {
      const ok = window.confirm(`「${nextText}」という名前のグループは既にあります。統合しますか？`);
      if (!ok) return;
    }

    try {
      const res = await fetch(`${API}/knowledge_graph/groups/${concept.concept_id}/rename`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: nextText }),
      });
      if (!res.ok) throw new Error("名前の変更に失敗しました");
      bumpGroupsVersion();
    } catch (err) {
      setError(err.message);
    }
  }, [editingId, editText, groups, bumpGroupsVersion]);

  const removeMember = useCallback(async (conceptId, isbn) => {
    setGroups(list => list.map(g => g.concept_id === conceptId
      ? { ...g, book_count: g.book_count - 1, members: g.members.filter(m => m.isbn !== isbn) }
      : g));
    try {
      const res = await fetch(`${API}/knowledge_graph/groups/${conceptId}/members/${isbn}`, { method: "DELETE" });
      if (!res.ok) throw new Error("メンバーの削除に失敗しました");
      bumpGroupsVersion();
    } catch (err) {
      setError(err.message);
      fetchGroups();
    }
  }, [bumpGroupsVersion, fetchGroups]);

  const deleteGroup = useCallback(async (g) => {
    if (!window.confirm(`「${g.text}」を削除しますか？所属している${g.book_count}冊からグループが外れます。`)) return;
    try {
      const res = await fetch(`${API}/knowledge_graph/groups/${g.concept_id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("削除に失敗しました");
      const data = await res.json();
      bumpGroupsVersion();
      // グループ自体が無くなるので、本棚に光らせたままのハイライトも一緒に消す
      clearGroupHighlight(g.concept_id);
      showToast({
        message: `「${data.text}」を削除しました`,
        actionLabel: "元に戻す",
        onAction: () => {
          fetch(`${API}/bookshelf/save-concept`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ meaning: data.text, isbns: data.member_isbns }),
          })
            .then(res2 => { if (res2.ok) bumpGroupsVersion(); })
            .catch(err => console.error("元に戻す操作に失敗しました", err));
        },
      });
    } catch (err) {
      setError(err.message);
    }
  }, [bumpGroupsVersion, showToast, clearGroupHighlight]);

  const mergeGroups = useCallback(async (sourceId, targetGroup) => {
    if (sourceId === targetGroup.concept_id) return;
    const sourceGroup = groups.find(g => g.concept_id === sourceId);
    if (!sourceGroup) return;
    if (!window.confirm(`「${sourceGroup.text}」を「${targetGroup.text}」に統合しますか？`)) return;
    try {
      const res = await fetch(`${API}/knowledge_graph/groups/merge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_concept_ids: [sourceId, targetGroup.concept_id],
          target_text: targetGroup.text,
        }),
      });
      if (!res.ok) throw new Error("統合に失敗しました");
      bumpGroupsVersion();
      // 統合元(sourceId)のグループは消えるので、光らせたままのハイライトも消す
      clearGroupHighlight(sourceId);
    } catch (err) {
      setError(err.message);
    }
  }, [groups, bumpGroupsVersion, clearGroupHighlight]);

  return (
    <div style={s.wrap}>
      <div style={s.head}>
        <span style={s.title}>グループ</span>
      </div>

      {error && <div style={s.statusError}>{error}</div>}
      {isLoading && groups.length === 0 && <div style={s.status}>読み込み中…</div>}

      {!isLoading && groups.length === 0 && (
        <div style={s.status}>
          まだグループがありません。本を選んで「グループを作る」から始めましょう。
        </div>
      )}

      <div style={s.list}>
        {groups.map(g => {
          const isHighlighted = conceptHighlights.group?.groupId === g.concept_id;
          const isExpanded = expandedId === g.concept_id;
          return (
            <div
              key={g.concept_id}
              className="group-panel-row"
              data-concept-id={g.concept_id}
              data-group-name={g.text}
              style={{
                ...s.row,
                borderColor: isHighlighted ? (conceptHighlights.group?.color || "#c9a84c") : "#ede8da",
                borderWidth: isHighlighted ? 2 : 1,
              }}
              draggable
              onDragStart={() => setDragSourceId(g.concept_id)}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); if (dragSourceId) mergeGroups(dragSourceId, g); setDragSourceId(null); }}
            >
              <div style={s.rowMain}>
                <button
                  style={s.chevron}
                  onClick={() => setExpandedId(isExpanded ? null : g.concept_id)}
                  title={isExpanded ? "メンバーを閉じる" : "メンバーを表示"}
                >
                  {isExpanded ? "▾" : "▸"}
                </button>

                {editingId === g.concept_id ? (
                  <input
                    autoFocus
                    style={s.editInput}
                    value={editText}
                    onChange={e => setEditText(e.target.value)}
                    onBlur={commitEdit}
                    onKeyDown={e => {
                      if (e.key === "Enter") e.currentTarget.blur();
                      if (e.key === "Escape") setEditingId(null);
                    }}
                  />
                ) : (
                  <span
                    style={s.rowName}
                    onClick={() => toggleGroupHighlight(g.concept_id, g.members.map(m => m.isbn))}
                    onDoubleClick={() => startEdit(g)}
                    title="クリックで本棚をハイライト／ダブルクリックで名前を編集"
                  >
                    {g.text}
                  </span>
                )}

                <span style={s.count}>{g.book_count}冊</span>

                <button style={s.iconBtn} onClick={() => startEdit(g)} title="名前を変更">✎</button>
                <button style={s.iconBtnDanger} onClick={() => deleteGroup(g)} title="グループを削除">✕</button>
              </div>

              {isExpanded && (
                <div style={s.members}>
                  {g.members.map(m => (
                    <div key={m.isbn} style={s.memberChip}>
                      {m.cover && <img src={m.cover} alt="" style={s.memberCover} />}
                      <span style={s.memberTitle}>{m.title}</span>
                      <button
                        style={s.memberRemove}
                        onClick={() => removeMember(g.concept_id, m.isbn)}
                        title="このグループから外す"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const s = {
  wrap: { display: "flex", flexDirection: "column", height: "100%", background: "#fffdf7" },
  head: { padding: "14px 14px 8px" },
  title: { fontSize: 12.5, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif" },
  status: { fontSize: 12, color: "#9a8b76", padding: "10px 14px", lineHeight: 1.6 },
  statusError: { fontSize: 12, color: "#c9506a", padding: "10px 14px" },
  list: { flex: 1, minHeight: 0, overflowY: "auto", padding: "0 10px 14px", display: "flex", flexDirection: "column", gap: 8 },
  row: {
    background: "#fff", border: "1px solid #ede8da", borderRadius: 10,
    padding: "8px 10px", transition: "border-color 0.15s, border-width 0.15s",
  },
  rowMain: { display: "flex", alignItems: "center", gap: 6 },
  chevron: {
    border: "none", background: "transparent", cursor: "pointer",
    color: "#9a8b76", fontSize: 11, padding: 0, width: 14, flexShrink: 0,
  },
  rowName: { flex: 1, fontSize: 12.5, color: "#2a1f0e", cursor: "pointer", lineHeight: 1.4 },
  editInput: {
    flex: 1, fontSize: 12.5, padding: "2px 6px", borderRadius: 6,
    border: "1px solid #c9a84c", fontFamily: "inherit",
  },
  count: { fontSize: 10.5, color: "#9a8b76", flexShrink: 0 },
  iconBtn: {
    flexShrink: 0, width: 20, height: 20, border: "none", borderRadius: "50%",
    background: "transparent", color: "#9a8b76", cursor: "pointer", fontSize: 11,
  },
  iconBtnDanger: {
    flexShrink: 0, width: 20, height: 20, border: "none", borderRadius: "50%",
    background: "transparent", color: "#c4b8a2", cursor: "pointer", fontSize: 10,
  },
  members: { display: "flex", flexDirection: "column", gap: 4, marginTop: 8, paddingLeft: 20 },
  memberChip: {
    display: "flex", alignItems: "center", gap: 6,
    fontSize: 11, color: "#4a3728", padding: "3px 6px",
    background: "#faf7f0", borderRadius: 6,
  },
  memberCover: { width: 18, height: 24, objectFit: "cover", borderRadius: 2, flexShrink: 0 },
  memberTitle: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  memberRemove: {
    flexShrink: 0, border: "none", background: "transparent",
    color: "#c4b8a2", cursor: "pointer", fontSize: 10,
  },
};
