// 右ペイン「本の詳細」。本棚で1冊タップすると表示される。
//
// 上から: 表紙・書名・著者 → （おすすめで加わった本なら）おすすめの理由
//        → 出版社 / 年 / 寸法（高さ×ページ数）/ 分類 / ジャンル / 内容 → 感想
// 書誌情報は登録データ（/register/{isbn}）から取る。
// 高さは対話のLLMも使うので、寸法の横の「編集」で直せるようにしている。
import { useCallback, useContext, useEffect, useState } from "react";
import { NDC_L1 } from "../../utils/ndc";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";
import { MyBookshelfContext } from "../../context/MyBookshelfContext";
import { useShelves } from "../../context/ShelvesContext";

const API = "http://localhost:8000";
const DESCRIPTION_PREVIEW_CHARS = 120;

export default function BookFocusPanel() {
  const { focusIsbn, setFocusIsbn, refreshGrowth } = useShelfWorkspace();

  const [book, setBook] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [coverFailed, setCoverFailed] = useState(false);
  const [showFullDescription, setShowFullDescription] = useState(false);

  const [heightDraft, setHeightDraft] = useState("");
  const [editingHeight, setEditingHeight] = useState(false);
  const [newTag, setNewTag] = useState("");
  const [busy, setBusy] = useState(false);

  const [impression, setImpression] = useState("");
  // 意味づけからのおすすめで加わった本なら、その記録（意味づけ・理由・置き場所）
  const [recommendation, setRecommendation] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

  const fetchBook = useCallback(() => {
    if (!focusIsbn) return Promise.resolve();
    return fetch(`${API}/register/${focusIsbn}`)
      .then(res => (res.ok ? res.json() : Promise.reject(new Error("読み込みに失敗しました"))))
      .then(setBook)
      .catch(err => setError(err.message));
  }, [focusIsbn]);

  useEffect(() => {
    if (!focusIsbn) return;
    setBook(null);
    setError(null);
    setCoverFailed(false);
    setShowFullDescription(false);
    setEditingHeight(false);
    setNewTag("");
    setIsSaved(false);
    setImpression("");
    setRecommendation(null);
    setLoading(true);
    fetchBook().finally(() => setLoading(false));

    let cancelled = false;
    fetch(`${API}/knowledge_graph/book/${focusIsbn}/basic`)
      .then(res => (res.ok ? res.json() : null))
      .then(basic => {
        if (cancelled) return;
        setImpression(basic?.impression || "");
        setRecommendation(basic?.recommendation || null);
      })
      .catch(err => console.error(err));
    return () => { cancelled = true; };
  }, [focusIsbn, fetchBook]);

  const saveHeight = useCallback(async () => {
    const mm = parseInt(heightDraft, 10);
    if (!mm || mm <= 0) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/register/${focusIsbn}/height`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ height_mm: mm }),
      });
      if (res.ok) { setEditingHeight(false); await fetchBook(); }
    } finally {
      setBusy(false);
    }
  }, [focusIsbn, heightDraft, fetchBook]);

  const addTag = useCallback(async () => {
    const tag = newTag.trim();
    if (!tag) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/register/${focusIsbn}/genre-tags`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag }),
      });
      if (res.ok) { setNewTag(""); await fetchBook(); }
    } finally {
      setBusy(false);
    }
  }, [focusIsbn, newTag, fetchBook]);

  const removeTag = useCallback(async (tag) => {
    setBusy(true);
    try {
      const res = await fetch(`${API}/register/${focusIsbn}/genre-tags/${encodeURIComponent(tag)}`, {
        method: "DELETE",
      });
      if (res.ok) await fetchBook();
    } finally {
      setBusy(false);
    }
  }, [focusIsbn, fetchBook]);

  const saveImpression = useCallback(async () => {
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

  if (!focusIsbn) return null;

  const ndc = book?.ndc || "";
  const ndcLabel = ndc ? NDC_L1[ndc[0]] : null;
  const description = book?.description || "";
  const longDescription = description.length > DESCRIPTION_PREVIEW_CHARS;
  const coverSrc = book?.cover || `${API}/register/cover/${focusIsbn}`;

  return (
    <div style={s.wrap}>
      <div style={s.head}>
        <button style={s.closeBtn} onClick={() => setFocusIsbn(null)} aria-label="閉じる">✕</button>
      </div>

      {loading && !book && <div style={s.status}>読み込み中…</div>}
      {error && <div style={s.statusError}>{error}</div>}

      {book && (
        <div style={s.body}>
          <div style={s.top}>
            {!coverFailed ? (
              <img
                src={coverSrc}
                alt=""
                style={s.cover}
                onError={e => {
                  if (!e.target.dataset.fallback && book.cover) {
                    e.target.dataset.fallback = "1";
                    e.target.src = `${API}/register/cover/${focusIsbn}`;
                  } else {
                    setCoverFailed(true);
                  }
                }}
              />
            ) : (
              <div style={{ ...s.cover, ...s.coverEmpty }}>表紙なし</div>
            )}
            <div style={s.titleBlock}>
              <div style={s.title}>{book.title || "（書名不明）"}</div>
              {book.authors?.length > 0 && <div style={s.authors}>{book.authors.join("、")}</div>}
            </div>
          </div>

          {recommendation && <RecommendationNote rec={recommendation} />}

          <dl style={s.rows}>
            <Row label="出版社">{book.publisher || "—"}</Row>
            <Row label="年">{book.published_year || "—"}</Row>
            <Row label="寸法">
              {editingHeight ? (
                <span style={s.inline}>
                  <input
                    style={s.heightInput}
                    type="number"
                    autoFocus
                    value={heightDraft}
                    onChange={e => setHeightDraft(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && saveHeight()}
                  />
                  mm
                  <button style={s.smallBtn} onClick={saveHeight} disabled={busy}>保存</button>
                  <button style={s.linkBtn} onClick={() => setEditingHeight(false)}>取消</button>
                </span>
              ) : (
                <span style={s.inline}>
                  {book.height_mm ? `${book.height_mm}mm` : "—"} × {book.pages ? `${book.pages}ページ` : "—"}
                  <button
                    style={s.linkBtn}
                    onClick={() => { setHeightDraft(String(book.height_mm || "")); setEditingHeight(true); }}
                  >
                    編集
                  </button>
                </span>
              )}
            </Row>
            <Row label="分類">{ndc ? `${ndc}${ndcLabel ? `（${ndcLabel}）` : ""}` : "—"}</Row>
            <Row label="ジャンル">
              <span style={s.tags}>
                {(book.genre_tags || []).map(g => (
                  <span key={g.tag} style={s.tag}>
                    {g.tag}
                    <button style={s.tagRemove} onClick={() => removeTag(g.tag)} aria-label={`${g.tag}を外す`}>✕</button>
                  </span>
                ))}
                <input
                  style={s.tagInput}
                  placeholder="+ 追加"
                  value={newTag}
                  onChange={e => setNewTag(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && !e.nativeEvent.isComposing && addTag()}
                />
              </span>
            </Row>
            <Row label="内容">
              {description ? (
                <span>
                  {showFullDescription || !longDescription
                    ? description
                    : `${description.slice(0, DESCRIPTION_PREVIEW_CHARS)}…`}
                  {longDescription && (
                    <button style={s.linkBtn} onClick={() => setShowFullDescription(v => !v)}>
                      {showFullDescription ? "閉じる" : "続き"}
                    </button>
                  )}
                </span>
              ) : "—"}
            </Row>
          </dl>

          <div style={s.sectionTitle}>感想</div>
          <textarea
            style={s.textarea}
            value={impression}
            onChange={e => { setImpression(e.target.value); setIsSaved(false); }}
          />
          <div style={s.saveRow}>
            {isSaved && <span style={s.savedHint}>保存しました</span>}
            <button style={s.saveBtn} onClick={saveImpression} disabled={isSaving}>
              {isSaving ? "保存中…" : "保存"}
            </button>
          </div>

          <MoveToShelf isbn={focusIsbn} title={book.title} onMoved={() => setFocusIsbn(null)} />
        </div>
      )}
    </div>
  );
}

// この本を別の本棚へ移す（本は1冊につきどれか1つの本棚に置く）。
// 移した先の本棚では新しく加わった本として扱い、この本棚の意味づけ・対話はこの本棚に残る。
function MoveToShelf({ isbn, title, onMoved }) {
  const { shelves, activeScopeId, moveBookToShelf } = useShelves();
  const { fetchBookshelf } = useContext(MyBookshelfContext);
  const { flushLayoutSync } = useShelfWorkspace();
  const others = shelves.filter(sh => sh.scope_id !== activeScopeId);
  const [toId, setToId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!others.length) return null;

  const move = async () => {
    const target = others.find(sh => String(sh.id) === String(toId));
    if (!target || busy) return;
    const ok = window.confirm(
      `『${title || "この本"}』を「${target.name}」へ移します。
` +
      "この本棚で付けた意味づけや対話の記録は、この本棚に残ります。よろしいですか？"
    );
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      await flushLayoutSync(); // まだ保存していない並べ替えを先に保存する
      await moveBookToShelf(isbn, target.id);
      await fetchBookshelf();
      onMoved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <>
      <div style={s.sectionTitle}>別の本棚へ移す</div>
      <div style={s.moveRow}>
        <select style={s.moveSelect} value={toId} onChange={e => setToId(e.target.value)}>
          <option value="">移す先の本棚を選ぶ</option>
          {others.map(sh => <option key={sh.id} value={sh.id}>{sh.name}（{sh.book_count}冊）</option>)}
        </select>
        <button style={{ ...s.saveBtn, ...(!toId || busy ? { opacity: 0.5 } : {}) }} onClick={move} disabled={!toId || busy}>
          {busy ? "移しています…" : "移す"}
        </button>
      </div>
      {error && <div style={s.statusError}>{error}</div>}
    </>
  );
}

// おすすめで加わった本の「おすすめされた理由」
function RecommendationNote({ rec }) {
  const place = rec.anchor_title
    ? `『${rec.anchor_title}』の${rec.side === "left" ? "左" : "右"}`
    : null;
  return (
    <div style={s.rec}>
      <div style={s.recHead}>
        <span style={s.recMark}>✦</span>おすすめで加わった本
        {rec.created_at && <span style={s.recDate}>{rec.created_at}</span>}
      </div>
      {rec.trigger === "request" && (
        <div style={s.recPlace}>対話でのお願い{rec.wish ? `「${rec.wish}」` : ""}に応えて</div>
      )}
      <div style={s.recConcept}>{rec.basis}から</div>
      {rec.aim && <div style={s.recPlace}>{rec.aim}</div>}
      {rec.reason && <div style={s.recReason}>{rec.reason}</div>}
      {(place || rec.placement_reason) && (
        <div style={s.recPlace}>
          置き場所: {place || "—"}{rec.placement_reason ? `。${rec.placement_reason}` : ""}
        </div>
      )}
    </div>
  );
}

function Row({ label, children }) {
  return (
    <div style={s.row}>
      <dt style={s.rowLabel}>{label}</dt>
      <dd style={s.rowValue}>{children}</dd>
    </div>
  );
}

const s = {
  // 右ペイン全体が1つのスクロールになっている（CompanionPanel を参照）
  wrap: { background: "#fff", flexShrink: 0 },
  head: { display: "flex", justifyContent: "flex-end", padding: "12px 14px 0" },
  closeBtn: {
    width: 26, height: 26, borderRadius: "50%", border: "none",
    background: "#f2ede0", color: "#4a3728", cursor: "pointer", fontSize: 12, lineHeight: 1,
  },
  body: { padding: "4px 20px 20px" },
  status: { fontSize: 13, color: "#9a8b76", textAlign: "center", padding: "24px 10px" },
  statusError: { fontSize: 13, color: "#c9506a", textAlign: "center", padding: "12px 10px" },

  top: { display: "flex", gap: 16, alignItems: "flex-start", marginBottom: 18 },
  cover: {
    width: 110, height: 156, objectFit: "cover", borderRadius: 6, flexShrink: 0,
    background: "#f2ede0", boxShadow: "0 6px 18px rgba(60,40,10,0.22)",
  },
  coverEmpty: {
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: 12, color: "#b5a88f", boxShadow: "none",
  },
  titleBlock: { minWidth: 0, paddingTop: 2 },
  title: { fontFamily: "serif", fontSize: 17, fontWeight: 700, color: "#2a1f0e", lineHeight: 1.5 },
  authors: { fontSize: 13, color: "#6b5c47", marginTop: 6, lineHeight: 1.6 },

  rec: {
    margin: "0 0 16px", padding: "10px 12px", borderRadius: 8,
    background: "#fbf5e2", border: "1px dashed #b8923a",
  },
  recHead: {
    display: "flex", alignItems: "center", gap: 5,
    fontSize: 12.5, fontWeight: 700, color: "#8a6a24",
  },
  recMark: { fontSize: 11 },
  recDate: { marginLeft: "auto", fontSize: 11.5, fontWeight: 400, color: "#9a8b76" },
  recConcept: { fontSize: 13, fontWeight: 700, color: "#2a1f0e", marginTop: 6 },
  recReason: { fontSize: 13.5, color: "#3d3020", lineHeight: 1.75, marginTop: 4 },
  recPlace: { fontSize: 12, color: "#8a7a62", lineHeight: 1.6, marginTop: 6 },

  rows: { margin: 0 },
  row: {
    display: "grid", gridTemplateColumns: "64px 1fr", gap: 10,
    padding: "9px 0", borderTop: "1px solid #f2ede0",
  },
  rowLabel: { fontSize: 12.5, color: "#9a8b76", fontWeight: 600, paddingTop: 1 },
  rowValue: { margin: 0, fontSize: 13.5, color: "#2a1f0e", lineHeight: 1.7, minWidth: 0 },
  inline: { display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" },
  heightInput: {
    width: 64, padding: "3px 6px", borderRadius: 6, border: "1px solid #e5ded0", fontSize: 13,
  },
  smallBtn: {
    padding: "3px 10px", background: "#c9a84c", color: "#fff",
    border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12,
  },
  linkBtn: {
    marginLeft: 6, fontSize: 12, color: "#b8963a", background: "none",
    border: "none", cursor: "pointer", padding: 0, textDecoration: "underline",
  },
  tags: { display: "flex", flexWrap: "wrap", gap: 5, alignItems: "center" },
  tag: {
    display: "inline-flex", alignItems: "center", gap: 4,
    fontSize: 12.5, borderRadius: 12, padding: "2px 8px 2px 10px",
    background: "#f6f1e4", color: "#6b5c47",
  },
  tagRemove: {
    border: "none", background: "none", cursor: "pointer",
    fontSize: 10, color: "inherit", opacity: 0.6, padding: 0, lineHeight: 1,
  },
  tagInput: {
    fontSize: 12.5, border: "1px dashed #e5ded0", borderRadius: 10,
    padding: "2px 8px", width: 72, outline: "none",
  },

  sectionTitle: { fontSize: 12.5, fontWeight: 600, color: "#9a8b76", margin: "16px 0 6px" },
  textarea: {
    width: "100%", minHeight: 72, padding: 10, borderRadius: 8, border: "1px solid #e5ded0",
    fontSize: 13.5, lineHeight: 1.7, fontFamily: "inherit", resize: "vertical", boxSizing: "border-box",
  },
  moveRow: { display: "flex", gap: 8, alignItems: "center" },
  moveSelect: {
    flex: 1, minWidth: 0, padding: "7px 8px", borderRadius: 8, border: "1px solid #e0d8c0",
    fontSize: 12.5, fontFamily: "inherit", background: "#fff", color: "#4a3728",
  },
  saveRow: { display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, marginTop: 8 },
  savedHint: { fontSize: 12, color: "#7ab893" },
  saveBtn: {
    padding: "6px 16px", background: "#c9a84c", color: "#fff",
    border: "none", borderRadius: 999, cursor: "pointer", fontSize: 13, fontWeight: 700,
  },
};
