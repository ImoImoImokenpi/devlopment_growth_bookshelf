// 右ペイン「本詳細」の中身（設計書4章① 1冊単位の感想）。通常モード専用。
//
// 本棚で1冊タップすると、その本がハイライトされ、ここに詳細が表示される。
// 内容は上から: 書誌情報 → 所属グループ → 感想の入力
//
// 「所属グループ」は読み取り専用（編集・削除はグルーピングモードの左パネルで行う）。
// 実体は意味づけ(Concept)なので、ホバーするとその意味づけでつながっている本が
// 本棚側で同じ色に光る（setConceptHighlight）。
import { useCallback, useEffect, useState } from "react";
import { conceptColor } from "../../utils/graphConfig";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";

const API = "http://localhost:8000";

export default function BookFocusPanel() {
  const {
    focusIsbn, setFocusIsbn,
    focusDetail, isFocusLoading,
    setConceptHighlight,
    refreshGrowth,
    conceptsVersion,
  } = useShelfWorkspace();

  const [concepts, setConcepts] = useState([]);
  const [impression, setImpression] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [error, setError] = useState(null);

  // 所持日数に応じた「褪せ」表現の元になる日付
  const [possessedSince, setPossessedSince] = useState(null);
  const [editingPossessedSince, setEditingPossessedSince] = useState(false);
  const [possessedSinceDraft, setPossessedSinceDraft] = useState("");
  const [savingPossessedSince, setSavingPossessedSince] = useState(false);

  // フェーズ1: 属性タグ基盤（高さ・色・ジャンルタグ）
  const [attrs, setAttrs] = useState(null);
  const [heightDraft, setHeightDraft] = useState("");
  const [editingHeight, setEditingHeight] = useState(false);
  const [newTag, setNewTag] = useState("");
  const [attrBusy, setAttrBusy] = useState(false);

  const fetchAttrs = useCallback(() => {
    if (!focusIsbn) return;
    fetch(`${API}/register/${focusIsbn}`)
      .then(res => (res.ok ? res.json() : null))
      .then(data => { if (data) setAttrs(data); })
      .catch(err => console.error(err));
  }, [focusIsbn]);

  useEffect(() => {
    setAttrs(null);
    setEditingHeight(false);
    setNewTag("");
    fetchAttrs();
  }, [fetchAttrs]);

  const saveHeight = useCallback(async () => {
    const mm = parseInt(heightDraft, 10);
    if (!mm || mm <= 0) return;
    setAttrBusy(true);
    try {
      const res = await fetch(`${API}/register/${focusIsbn}/height`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ height_mm: mm }),
      });
      if (res.ok) { setEditingHeight(false); fetchAttrs(); }
    } finally {
      setAttrBusy(false);
    }
  }, [focusIsbn, heightDraft, fetchAttrs]);

  const saveColor = useCallback(async (hex) => {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    setAttrBusy(true);
    try {
      const res = await fetch(`${API}/register/${focusIsbn}/color`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spine_color: `${r},${g},${b}` }),
      });
      if (res.ok) fetchAttrs();
    } finally {
      setAttrBusy(false);
    }
  }, [focusIsbn, fetchAttrs]);

  const addTag = useCallback(async () => {
    const tag = newTag.trim();
    if (!tag) return;
    setAttrBusy(true);
    try {
      const res = await fetch(`${API}/register/${focusIsbn}/genre-tags`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag }),
      });
      if (res.ok) { setNewTag(""); fetchAttrs(); }
    } finally {
      setAttrBusy(false);
    }
  }, [focusIsbn, newTag, fetchAttrs]);

  const removeTag = useCallback(async (tag) => {
    setAttrBusy(true);
    try {
      const res = await fetch(`${API}/register/${focusIsbn}/genre-tags/${encodeURIComponent(tag)}`, {
        method: "DELETE",
      });
      if (res.ok) fetchAttrs();
    } finally {
      setAttrBusy(false);
    }
  }, [focusIsbn, fetchAttrs]);

  // 感想と意味づけは周辺グラフに含まれないので、ここで取る
  useEffect(() => {
    if (!focusIsbn) return;
    let cancelled = false;
    setIsSaved(false);
    setError(null);
    setImpression("");

    fetch(`${API}/knowledge_graph/book/${focusIsbn}/basic`)
      .then(res => (res.ok ? res.json() : null))
      .then(basic => {
        if (cancelled) return;
        setImpression(basic?.impression || "");
        setPossessedSince(basic?.possessed_since || null);
      })
      .catch(err => { if (!cancelled) setError("読み込みに失敗しました"); console.error(err); });

    return () => { cancelled = true; };
  }, [focusIsbn]);

  const savePossessedSince = useCallback(async () => {
    if (!possessedSinceDraft) return;
    setSavingPossessedSince(true);
    try {
      const res = await fetch(`${API}/knowledge_graph/book/${focusIsbn}/possessed-since`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ possessed_since: possessedSinceDraft }),
      });
      if (res.ok) {
        setPossessedSince(possessedSinceDraft);
        setEditingPossessedSince(false);
      }
    } finally {
      setSavingPossessedSince(false);
    }
  }, [focusIsbn, possessedSinceDraft]);

  const possessedDurationLabel = (() => {
    if (!possessedSince) return null;
    const days = Math.floor((Date.now() - new Date(possessedSince).getTime()) / 86_400_000);
    if (days < 30) return `${days}日`;
    if (days < 365) return `${Math.floor(days / 30)}ヶ月`;
    const years = Math.floor(days / 365);
    const months = Math.floor((days % 365) / 30);
    return months > 0 ? `${years}年${months}ヶ月` : `${years}年`;
  })();

  // 意味づけ一覧は別出しにする。発見への「はい」「一部ちがう」で知識グラフに
  // 書き戻されたとき（conceptsVersion）も、入力中の感想を消さずに取り直せるようにするため。
  useEffect(() => {
    if (!focusIsbn) return;
    let cancelled = false;
    setConcepts([]);

    fetch(`${API}/knowledge_graph/book/${focusIsbn}/concepts`)
      .then(res => (res.ok ? res.json() : { concepts: [] }))
      .then(conceptData => { if (!cancelled) setConcepts(conceptData.concepts || []); })
      .catch(err => { if (!cancelled) setError("読み込みに失敗しました"); console.error(err); });

    return () => { cancelled = true; };
  }, [focusIsbn, conceptsVersion]);

  // パネルを閉じたら本棚側の強調も消す
  useEffect(() => () => setConceptHighlight(null), [setConceptHighlight]);

  // 別の本に切り替えたときも、前の本の意味づけの色が残らないようにする
  useEffect(() => { setConceptHighlight(null); }, [focusIsbn, setConceptHighlight]);

  const save = useCallback(async () => {
    setIsSaving(true);
    setIsSaved(false);
    try {
      const res = await fetch(`${API}/knowledge_graph/book/${focusIsbn}/impression`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: impression.trim() }),
      });
      if (!res.ok) throw new Error("保存に失敗しました");
      setIsSaved(true);
      refreshGrowth();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSaving(false);
    }
  }, [focusIsbn, impression, refreshGrowth]);

  if (!focusIsbn) {
    return (
      <div style={s.wrap}>
        <div style={s.status}>本棚で1冊タップすると、ここに詳細が表示されます</div>
      </div>
    );
  }

  const book = focusDetail?.book;

  return (
    <div style={s.wrap}>
      <div style={s.head}>
        <span style={s.title}>{book?.title || "本詳細"}</span>
        <button style={s.closeBtn} onClick={() => setFocusIsbn(null)}>✕</button>
      </div>

      {isFocusLoading && !book && <div style={s.status}>読み込み中…</div>}
      {error && <div style={s.statusError}>{error}</div>}

      {book && (
        <div style={s.body}>
          <div style={s.bookHeader}>
            {(book.cover || book.spine_image) && (
              <img
                src={book.cover || `${API}/register/cover/${book.isbn}`}
                alt=""
                style={s.cover}
                onError={e => {
                  if (!e.target.dataset.fallback) {
                    e.target.dataset.fallback = "1";
                    e.target.src = `${API}/register/cover/${book.isbn}`;
                  }
                }}
              />
            )}
            <div style={{ minWidth: 0 }}>
              {book.authors && <div style={s.meta}>{book.authors}</div>}
              {book.publisher && (
                <div style={s.meta}>
                  {book.publisher}{book.published_year ? `（${book.published_year}）` : ""}
                </div>
              )}
            </div>
          </div>

          <div style={s.possessedRow}>
            <span style={s.possessedLabel}>所持期間</span>
            {editingPossessedSince ? (
              <>
                <input
                  type="date"
                  style={s.possessedInput}
                  value={possessedSinceDraft}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={e => setPossessedSinceDraft(e.target.value)}
                  autoFocus
                />
                <button style={s.attrSmallBtn} onClick={savePossessedSince} disabled={savingPossessedSince}>保存</button>
                <button style={s.attrSmallBtnGhost} onClick={() => setEditingPossessedSince(false)}>取消</button>
              </>
            ) : (
              <>
                <span style={s.possessedValue}>
                  {possessedDurationLabel ? `${possessedDurationLabel}所持` : "未設定"}
                </span>
                <button
                  style={s.attrLinkBtn}
                  onClick={() => {
                    setPossessedSinceDraft(possessedSince || new Date().toISOString().slice(0, 10));
                    setEditingPossessedSince(true);
                  }}
                >
                  編集
                </button>
              </>
            )}
          </div>

          <div style={s.sectionTitle}>属性</div>
          <div style={s.attrBlock}>
            {/* 高さ */}
            <div style={s.attrRow}>
              <span style={s.attrLabel}>高さ</span>
              {editingHeight ? (
                <div style={s.attrEditRow}>
                  <input
                    style={s.attrInput}
                    type="number"
                    autoFocus
                    value={heightDraft}
                    onChange={e => setHeightDraft(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && saveHeight()}
                  />
                  <span style={s.attrUnit}>mm</span>
                  <button style={s.attrSmallBtn} onClick={saveHeight} disabled={attrBusy}>保存</button>
                  <button style={s.attrSmallBtnGhost} onClick={() => setEditingHeight(false)}>取消</button>
                </div>
              ) : (
                <div style={s.attrEditRow}>
                  <span style={s.attrValue}>
                    {attrs?.height_mm ? `${attrs.height_mm} mm` : "未設定"}
                  </span>
                  {attrs && (
                    <span style={s.sourceTag}>
                      {attrs.height_source === "manual" ? "手動" : "自動"}
                    </span>
                  )}
                  <button
                    style={s.attrLinkBtn}
                    onClick={() => { setHeightDraft(String(attrs?.height_mm || "")); setEditingHeight(true); }}
                  >
                    編集
                  </button>
                </div>
              )}
            </div>

            {/* 色 */}
            <div style={s.attrRow}>
              <span style={s.attrLabel}>色</span>
              <div style={s.attrEditRow}>
                <span
                  style={{
                    ...s.colorSwatch,
                    backgroundColor: attrs?.spine_color ? `rgb(${attrs.spine_color})` : "#eee",
                  }}
                />
                {attrs && (
                  <span style={s.sourceTag}>
                    {attrs.spine_color_source === "manual" ? "手動" : "自動抽出"}
                  </span>
                )}
                <label style={s.attrLinkBtn}>
                  補正
                  <input
                    type="color"
                    style={{ width: 0, height: 0, opacity: 0, position: "absolute" }}
                    onChange={e => saveColor(e.target.value)}
                  />
                </label>
              </div>
            </div>

            {/* ジャンルタグ */}
            <div style={s.attrRow}>
              <span style={s.attrLabel}>ジャンル</span>
              <div style={s.tagWrap}>
                {(attrs?.genre_tags || []).map(g => (
                  <span
                    key={g.tag}
                    style={{ ...s.tagChip, ...(g.origin === "manual" ? s.tagChipManual : s.tagChipAuto) }}
                  >
                    {g.tag}
                    <button style={s.tagRemoveBtn} onClick={() => removeTag(g.tag)} title="削除">✕</button>
                  </span>
                ))}
                <input
                  style={s.tagInput}
                  placeholder="+ 追加"
                  value={newTag}
                  onChange={e => setNewTag(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && addTag()}
                />
              </div>
            </div>
          </div>

          <div style={s.sectionTitle}>感想</div>
          <textarea
            style={s.textarea}
            value={impression}
            onChange={e => { setImpression(e.target.value); setIsSaved(false); }}
            placeholder="読んで感じたことを書き留めよう…"
          />
          <div style={s.saveRow}>
            {isSaved && <span style={s.savedHint}>保存しました</span>}
            <button style={s.saveBtn} onClick={save} disabled={isSaving}>
              {isSaving ? "保存中…" : "保存"}
            </button>
          </div>

          <div style={s.sectionTitle}>所属グループ</div>
          {concepts.length === 0 ? (
            <div style={s.emptyHint}>まだどのグループにも入っていません</div>
          ) : (
            <div style={s.conceptList}>
              {concepts.map((c, i) => (
                <div
                  key={c.edge_id ?? i}
                  style={{ ...s.conceptItem, borderLeftColor: conceptColor(i) }}
                  // このグループでつながっている本を、グループ固有の色で棚に映す。
                  // 中心の本も含めて、ひとつのまとまりとして見えるようにする。
                  onMouseEnter={() => setConceptHighlight({
                    color: conceptColor(i),
                    isbns: [focusIsbn, ...(c.related_isbns || [])],
                  })}
                  onMouseLeave={() => setConceptHighlight(null)}
                  title="このグループに属する本が、本棚で同じ色に光ります"
                >
                  <span style={{ ...s.conceptDot, backgroundColor: conceptColor(i) }} />
                  <span style={s.conceptText}>{c.text}</span>
                </div>
              ))}
            </div>
          )}

        </div>
      )}
    </div>
  );
}

const s = {
  // 高さを制限せず、内側にもスクロールを作らない。
  // 右ペイン全体が1つのスクロールになっている（CompanionPanel を参照）。
  wrap: {
    borderBottom: "1px solid #ede8da",
    background: "#fffdf7",
    flexShrink: 0,
  },
  head: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "10px 12px 8px", gap: 8,
  },
  title: {
    fontSize: 12.5, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif",
    lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  closeBtn: {
    width: 20, height: 20, borderRadius: "50%", border: "none",
    background: "#ede8da", color: "#4a3728", cursor: "pointer",
    fontSize: 11, lineHeight: 1, flexShrink: 0,
  },
  body: { padding: "0 12px 12px" },
  status: { fontSize: 12, color: "#9a8b76", textAlign: "center", padding: "20px 10px" },
  statusError: { fontSize: 12, color: "#c9506a", textAlign: "center", padding: "12px 10px" },
  bookHeader: { display: "flex", gap: 10, marginBottom: 4 },
  cover: {
    width: 44, height: 62, objectFit: "cover", borderRadius: 4,
    background: "#eee", flexShrink: 0, boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
  },
  meta: { fontSize: 11, color: "#6b5c47", marginBottom: 2, lineHeight: 1.45 },
  sectionTitle: {
    fontSize: 10, fontWeight: 700, color: "#c9a84c",
    textTransform: "uppercase", letterSpacing: "0.06em",
    marginTop: 12, marginBottom: 6,
  },
  emptyHint: { fontSize: 11.5, color: "#c4b8a2" },
  conceptList: { display: "flex", flexDirection: "column", gap: 5 },
  conceptItem: {
    display: "flex", gap: 8, alignItems: "flex-start",
    fontSize: 11.5, color: "#2a1f0e", lineHeight: 1.55,
    padding: "6px 9px", borderRadius: 8, cursor: "default",
    background: "#fff", border: "1px solid #ede8da",
    borderLeftWidth: 3, borderLeftStyle: "solid",
  },
  conceptDot: { width: 7, height: 7, borderRadius: "50%", flexShrink: 0, marginTop: 4 },
  conceptText: { flex: 1 },
  textarea: {
    width: "100%", minHeight: 70, padding: 9,
    borderRadius: 8, border: "1px solid #e5ded0",
    fontSize: 12, lineHeight: 1.65, fontFamily: "inherit",
    resize: "vertical", boxSizing: "border-box",
  },
  saveRow: {
    display: "flex", justifyContent: "flex-end", alignItems: "center",
    gap: 10, marginTop: 7,
  },
  savedHint: { fontSize: 10.5, color: "#7ab893" },
  saveBtn: {
    padding: "5px 14px", background: "#c9a84c", color: "#fff",
    border: "none", borderRadius: 9, cursor: "pointer",
    fontSize: 11.5, fontWeight: 700,
  },
  attrBlock: { display: "flex", flexDirection: "column", gap: 8 },
  attrRow: { display: "flex", flexDirection: "column", gap: 3 },
  attrLabel: { fontSize: 10.5, color: "#9a8b76", fontWeight: 600 },
  attrEditRow: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" },
  attrValue: { fontSize: 12, color: "#2a1f0e" },
  attrInput: {
    width: 64, padding: "3px 6px", borderRadius: 6,
    border: "1px solid #e5ded0", fontSize: 12,
  },
  attrUnit: { fontSize: 11, color: "#9a8b76" },
  possessedRow: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 },
  possessedLabel: { fontSize: 10.5, color: "#9a8b76", fontWeight: 600 },
  possessedValue: { fontSize: 12, color: "#2a1f0e" },
  possessedInput: {
    padding: "3px 6px", borderRadius: 6, border: "1px solid #e5ded0", fontSize: 12,
  },
  sourceTag: {
    fontSize: 9.5, color: "#9a8b76", background: "#f2ede0",
    borderRadius: 6, padding: "1px 6px",
  },
  attrLinkBtn: {
    position: "relative", fontSize: 11, color: "#c9a84c", background: "none",
    border: "none", cursor: "pointer", padding: 0, textDecoration: "underline",
  },
  attrSmallBtn: {
    padding: "3px 10px", background: "#c9a84c", color: "#fff",
    border: "none", borderRadius: 6, cursor: "pointer", fontSize: 11,
  },
  attrSmallBtnGhost: {
    padding: "3px 10px", background: "none", color: "#9a8b76",
    border: "1px solid #e5ded0", borderRadius: 6, cursor: "pointer", fontSize: 11,
  },
  colorSwatch: {
    width: 18, height: 18, borderRadius: 4,
    border: "1px solid rgba(0,0,0,0.12)", flexShrink: 0,
  },
  tagWrap: { display: "flex", flexWrap: "wrap", gap: 5, alignItems: "center" },
  tagChip: {
    display: "inline-flex", alignItems: "center", gap: 4,
    fontSize: 11, borderRadius: 12, padding: "3px 8px 3px 9px",
    border: "1px solid transparent",
  },
  tagChipAuto: { background: "#f2ede0", color: "#6b5c47" },
  tagChipManual: { background: "#fdf0da", color: "#a67c2e", borderColor: "#eddcb5" },
  tagRemoveBtn: {
    border: "none", background: "none", cursor: "pointer",
    fontSize: 9, color: "inherit", opacity: 0.6, padding: 0, lineHeight: 1,
  },
  tagInput: {
    fontSize: 11, border: "1px dashed #e5ded0", borderRadius: 10,
    padding: "3px 8px", width: 70, outline: "none",
  },
};
