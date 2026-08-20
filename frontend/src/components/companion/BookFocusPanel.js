// 右ペイン「本詳細」の中身（設計書4章① 1冊単位の感想）。
//
// 本棚で1冊タップすると、その本がハイライトされ、ここに詳細が表示される。
// 内容は上から: 書誌情報 → 意味づけ → 感想の入力
//
// 意味づけにカーソルを合わせると、その意味づけでつながっている本が
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

  // 感想と意味づけは周辺グラフに含まれないので、ここで取る
  useEffect(() => {
    if (!focusIsbn) return;
    let cancelled = false;
    setIsSaved(false);
    setError(null);
    setImpression("");

    fetch(`${API}/knowledge_graph/book/${focusIsbn}/basic`)
      .then(res => (res.ok ? res.json() : null))
      .then(basic => { if (!cancelled) setImpression(basic?.impression || ""); })
      .catch(err => { if (!cancelled) setError("読み込みに失敗しました"); console.error(err); });

    return () => { cancelled = true; };
  }, [focusIsbn]);

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

          <div style={s.sectionTitle}>意味づけ</div>
          {concepts.length === 0 ? (
            <div style={s.emptyHint}>まだ意味づけされていません</div>
          ) : (
            <div style={s.conceptList}>
              {concepts.map((c, i) => (
                <div
                  key={i}
                  style={{ ...s.conceptItem, borderLeftColor: conceptColor(i) }}
                  // この意味づけでつながっている本を、意味づけ固有の色で棚に映す。
                  // 中心の本も含めて、ひとつのまとまりとして見えるようにする。
                  onMouseEnter={() => setConceptHighlight({
                    color: conceptColor(i),
                    isbns: [focusIsbn, ...(c.related_isbns || [])],
                  })}
                  onMouseLeave={() => setConceptHighlight(null)}
                  title="この意味づけでつながっている本が、本棚で同じ色に光ります"
                >
                  <span style={{ ...s.conceptDot, backgroundColor: conceptColor(i) }} />
                  <span>{c.text}</span>
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
};
