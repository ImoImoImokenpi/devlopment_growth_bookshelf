// 本棚との対話パネル（育つ本棚の右ペイン）。
//
// 並べ替えを終えて「本棚と話す」を押すと開く。開いたら、待ち中の並べ替えを
// すぐ保存してから /dialogue/start を呼び、知識グラフを読んだLLMが
// 今回の並べ替えについて問いかけるところから会話が始まる。
//
// 会話の途中では意味づけの候補を出さない。LLMが会話を締めくくったとき
// （または持ち主が途中で「対話を終える」を押したとき）に、対話全体から
// まとめた意味づけを「本棚に反映しますか？」と1か所でまとめて確認する。
// 持ち主が選んだものだけが知識グラフ(Concept)に書き込まれ、本棚が育つ。
import { forwardRef, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { MyBookshelfContext } from "../../context/MyBookshelfContext";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";

const API = "http://localhost:8000";
const ACCENT = "#c9a84c";
const HIGHLIGHT_COLOR = "#e0587a";

async function postJson(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `エラーが発生しました (${res.status})`);
  return data;
}

export default function DialoguePanel({ onClose }) {
  const { myBookshelf } = useContext(MyBookshelfContext);
  const {
    flushLayoutSync, setHighlightIsbns, setConceptHighlight,
    refreshGrowth, dialogueSessionIdRef,
  } = useShelfWorkspace();

  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]); // { role: "assistant" | "user", text }
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [acceptedCount, setAcceptedCount] = useState(0);
  // LLMが会話を締めくくったら true。入力欄の代わりに確認・終了の操作を出す
  const [done, setDone] = useState(false);
  // 締めくくりでまとめた意味づけの確認。
  // { items: [{ proposal_id, meaning, isbns, reason, selected, draftMeaning, draftIsbns }],
  //   status: "pending" | "saving" | "applied" | "skipped", appliedCount }
  const [review, setReview] = useState(null);
  const [llmMode, setLlmMode] = useState(null); // "off" | "mock" | "live"
  const listRef = useRef(null);
  const reviewRef = useRef(null);
  const startedRef = useRef(false);

  const titleByIsbn = useMemo(() => {
    const map = {};
    (myBookshelf?.shelves || []).forEach(s => (s.books || []).forEach(b => { map[b.isbn] = b.title; }));
    return map;
  }, [myBookshelf]);

  const hasUserMessage = messages.some(m => m.role === "user");
  const reviewPending = review && (review.status === "pending" || review.status === "saving");

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await flushLayoutSync();
      const data = await postJson("/dialogue/start");
      setSessionId(data.session_id);
      // ここから先の並べ替えは「対話の中の移動」として記録される
      dialogueSessionIdRef.current = data.session_id;
      setMessages([{ role: "assistant", text: data.message }]);
      setHighlightIsbns(data.focus_isbns || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [flushLayoutSync, setHighlightIsbns, dialogueSessionIdRef]);

  // モック・停止中は本番と見分けられるよう、タイトルの横に印を出す
  useEffect(() => {
    fetch(`${API}/dialogue/mode`)
      .then(res => (res.ok ? res.json() : null))
      .then(data => setLlmMode(data?.mode || null))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (startedRef.current) return; // StrictModeの二重実行で対話が2つ始まらないようにする
    startedRef.current = true;
    start();
  }, [start]);

  // パネルを閉じたら本棚の強調を消し、以後の並べ替えは対話の外として扱う
  useEffect(() => () => {
    setHighlightIsbns([]);
    setConceptHighlight(null);
    dialogueSessionIdRef.current = null;
  }, [setHighlightIsbns, setConceptHighlight, dialogueSessionIdRef]);

  // 新しい発言が来たら一番下へ。確認が出たときは「本棚に反映しますか？」の見出しが見える位置へ
  useEffect(() => {
    if (review?.status === "pending" && reviewRef.current) {
      reviewRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, review?.status]);

  // LLMの返事を画面に反映する（返事・締めくくりで共通）
  const applyResponse = (data) => {
    setMessages(prev => [...prev, { role: "assistant", text: data.message }]);
    setHighlightIsbns(data.focus_isbns || []);
    setDone(!!data.done);
    if (data.done && (data.proposals || []).length > 0) {
      setReview({
        status: "pending",
        appliedCount: 0,
        items: data.proposals.map(p => ({
          ...p, selected: true, draftMeaning: p.meaning, draftIsbns: p.isbns,
        })),
      });
    } else if (data.done) {
      setReview(null);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || !sessionId || busy) return;
    setInput("");
    setError(null);
    setMessages(prev => [...prev, { role: "user", text }]);
    setBusy(true);
    try {
      await flushLayoutSync();
      applyResponse(await postJson(`/dialogue/${sessionId}/message`, { text }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  // 途中で「対話を終える」を押したとき: すぐ閉じず、LLMに締めくくらせて確認を出す
  const wrapUp = async () => {
    if (!sessionId || busy) return;
    setError(null);
    setBusy(true);
    try {
      await flushLayoutSync();
      applyResponse(await postJson(`/dialogue/${sessionId}/wrap-up`));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const updateItem = (proposalId, patch) => {
    setReview(prev => ({
      ...prev,
      items: prev.items.map(it => (it.proposal_id === proposalId ? { ...it, ...patch } : it)),
    }));
  };

  const selectedItems = (review?.items || []).filter(
    it => it.selected && it.draftMeaning.trim() && it.draftIsbns.length > 0,
  );

  // 選んだものを本棚に反映し、選ばなかったものは「反映しない」として記録する
  const applyReview = async (reflect) => {
    if (!review || review.status !== "pending") return;
    setError(null);
    setConceptHighlight(null);
    setReview(prev => ({ ...prev, status: "saving" }));
    let applied = 0;
    try {
      for (const it of review.items) {
        const chosen = reflect && it.selected && it.draftMeaning.trim() && it.draftIsbns.length > 0;
        if (chosen) {
          await postJson(`/dialogue/${sessionId}/proposals/${it.proposal_id}/accept`, {
            meaning: it.draftMeaning.trim(), isbns: it.draftIsbns,
          });
          applied += 1;
        } else {
          await postJson(`/dialogue/${sessionId}/proposals/${it.proposal_id}/reject`);
        }
      }
      if (applied > 0) {
        setAcceptedCount(c => c + applied);
        refreshGrowth();
      }
      setReview(prev => ({ ...prev, status: applied > 0 ? "applied" : "skipped", appliedCount: applied }));
    } catch (err) {
      setError(err.message);
      setReview(prev => ({ ...prev, status: "pending" }));
    }
  };

  const continueTalking = () => {
    setDone(false);
    setReview(null);
  };

  const finish = async () => {
    // 対話中に動かした本がまだ保存待ちなら、対話の移動として先に保存してから終える
    try { await flushLayoutSync(); } catch (err) { console.error(err); }
    dialogueSessionIdRef.current = null;
    if (sessionId) {
      try { await postJson(`/dialogue/${sessionId}/end`); } catch (err) { console.error(err); }
    }
    onClose();
  };

  // ヘッダーの「対話を終える」: 話した内容があればまず締めくくり、なければそのまま閉じる
  const onHeaderEnd = () => {
    if (sessionId && !done && hasUserMessage) wrapUp();
    else finish();
  };

  const onKeyDown = (e) => {
    // 日本語入力の変換確定のEnterでは送らない
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <aside style={s.panel}>
      <div style={s.header}>
        <div>
          <div style={s.title}>
            本棚と対話
            {llmMode === "mock" && <span style={s.modeBadge}>モック</span>}
            {llmMode === "off" && <span style={{ ...s.modeBadge, ...s.modeBadgeOff }}>停止中</span>}
          </div>
          {acceptedCount > 0 && <div style={s.sub}>意味づけ +{acceptedCount}</div>}
        </div>
        {!reviewPending && (
          <button style={s.endBtn} onClick={onHeaderEnd} disabled={busy}>終える</button>
        )}
      </div>

      <div ref={listRef} style={s.list}>
        {messages.map((m, i) => (
          <div key={i} style={m.role === "user" ? s.rowUser : s.rowAssistant}>
            <div style={m.role === "user" ? s.bubbleUser : s.bubbleAssistant}>{m.text}</div>
          </div>
        ))}

        {review && (
          <ReviewBlock
            ref={reviewRef}
            review={review}
            titleByIsbn={titleByIsbn}
            onChange={updateItem}
            onHover={(isbns) => setConceptHighlight(isbns ? { color: HIGHLIGHT_COLOR, isbns } : null)}
          />
        )}

        {busy && <div style={s.thinking}>考え中…</div>}
        {error && (
          <div style={s.error}>
            {error}
            {!sessionId && <button style={s.retryBtn} onClick={start}>もう一度</button>}
          </div>
        )}
      </div>

      {reviewPending ? (
        <div style={s.bottomBar}>
          <div style={s.bottomActions}>
            <button
              style={s.secondaryBtn}
              onClick={() => applyReview(false)}
              disabled={review.status === "saving"}
            >
              反映しない
            </button>
            <button
              style={{ ...s.primaryBtn, ...((review.status === "saving" || selectedItems.length === 0) ? s.disabled : {}) }}
              onClick={() => applyReview(true)}
              disabled={review.status === "saving" || selectedItems.length === 0}
            >
              {review.status === "saving" ? "反映中…" : `反映する（${selectedItems.length}件）`}
            </button>
          </div>
        </div>
      ) : done ? (
        <div style={s.bottomBar}>
          <div style={s.bottomText}>
            {review?.status === "applied"
              ? `✓ ${review.appliedCount}件を反映しました`
              : review?.status === "skipped"
                ? "反映しませんでした"
                : "おつかれさまでした"}
          </div>
          <div style={s.bottomActions}>
            <button style={s.secondaryBtn} onClick={continueTalking}>もう少し話す</button>
            <button style={s.primaryBtn} onClick={finish}>終える</button>
          </div>
        </div>
      ) : (
        <div style={s.inputRow}>
          <textarea
            style={s.input}
            rows={2}
            value={input}
            placeholder={sessionId ? "メッセージを入力" : ""}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={!sessionId}
          />
          <button
            style={{ ...s.primaryBtn, ...((!input.trim() || busy || !sessionId) ? s.disabled : {}) }}
            onClick={send}
            disabled={!input.trim() || busy || !sessionId}
          >
            送信
          </button>
        </div>
      )}
    </aside>
  );
}

// 締めくくりのメッセージの下に出す「本棚に反映しますか？」の確認
const ReviewBlock = forwardRef(function ReviewBlock({ review, titleByIsbn, onChange, onHover }, ref) {
  const locked = review.status !== "pending";
  const finished = review.status === "applied" || review.status === "skipped";

  return (
    <div ref={ref} style={s.review}>
      <div style={s.reviewTitle}>
        {finished ? "まとめた意味づけ" : "本棚に反映しますか？"}
      </div>

      {review.items.map(it => {
        const result = finished ? (it.selected && review.status === "applied" ? "反映済み" : "反映せず") : null;
        return (
          <div
            key={it.proposal_id}
            style={{ ...s.item, ...(it.selected ? s.itemOn : s.itemOff) }}
            onMouseEnter={() => onHover(it.draftIsbns)}
            onMouseLeave={() => onHover(null)}
          >
            <label style={s.itemHead}>
              <input
                type="checkbox"
                checked={it.selected}
                disabled={locked}
                onChange={e => onChange(it.proposal_id, { selected: e.target.checked })}
                style={s.checkbox}
              />
              <input
                style={s.itemName}
                value={it.draftMeaning}
                maxLength={30}
                disabled={locked}
                onChange={e => onChange(it.proposal_id, { draftMeaning: e.target.value })}
              />
              {result && <span style={result === "反映済み" ? s.badgeOn : s.badgeOff}>{result}</span>}
            </label>
            <div style={s.chips}>
              {it.isbns.map(isbn => {
                const on = it.draftIsbns.includes(isbn);
                return (
                  <button
                    key={isbn}
                    style={{ ...s.chip, ...(on ? {} : s.chipOff) }}
                    disabled={locked}
                    onClick={() => onChange(it.proposal_id, {
                      draftIsbns: on ? it.draftIsbns.filter(x => x !== isbn) : [...it.draftIsbns, isbn],
                    })}
                    title={on ? "この本を外す" : "この本を戻す"}
                  >
                    {titleByIsbn[isbn] || isbn}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
});

const s = {
  panel: {
    display: "flex", flexDirection: "column", width: "100%", height: "100%",
    background: "#fff", boxSizing: "border-box",
  },
  header: {
    flexShrink: 0, display: "flex", alignItems: "flex-start", justifyContent: "space-between",
    gap: 12, padding: "18px 20px 14px", borderBottom: "1px solid #ede8da",
  },
  title: {
    fontFamily: "serif", fontSize: 18, fontWeight: 700, color: "#2a1f0e",
    display: "flex", alignItems: "center", gap: 8,
  },
  modeBadge: {
    fontFamily: "inherit", fontSize: 11.5, fontWeight: 700, padding: "2px 8px",
    borderRadius: 999, background: "#e8f0fb", color: "#3b6fb6",
  },
  modeBadgeOff: { background: "#f2eee6", color: "#9a8b76" },
  sub: { fontSize: 13, color: "#9a8b76", marginTop: 4 },
  endBtn: {
    flexShrink: 0, padding: "5px 12px", borderRadius: 999, border: "1px solid #e0d8c0",
    background: "#fff", color: "#6b5a3e", fontSize: 13, fontWeight: 600, cursor: "pointer",
  },
  list: { flex: 1, minHeight: 0, overflowY: "auto", padding: "18px 18px 8px" },
  rowAssistant: { display: "flex", justifyContent: "flex-start", marginBottom: 12 },
  rowUser: { display: "flex", justifyContent: "flex-end", marginBottom: 12 },
  bubbleAssistant: {
    maxWidth: "88%", padding: "12px 15px", borderRadius: "4px 16px 16px 16px",
    background: "#fff", border: "1px solid #ede8da", color: "#2a1f0e",
    fontSize: 15, lineHeight: 1.8, whiteSpace: "pre-wrap",
  },
  bubbleUser: {
    maxWidth: "88%", padding: "12px 15px", borderRadius: "16px 4px 16px 16px",
    background: ACCENT, color: "#fff", fontSize: 15, lineHeight: 1.8, whiteSpace: "pre-wrap",
  },
  thinking: { fontSize: 13.5, color: "#9a8b76", padding: "4px 2px 10px" },
  error: {
    fontSize: 13, color: "#b3261e", background: "#fdecea", borderRadius: 8,
    padding: "8px 10px", margin: "4px 0 10px", lineHeight: 1.6,
  },
  retryBtn: {
    marginLeft: 8, padding: "2px 10px", borderRadius: 999, border: "1px solid #e8c4c0",
    background: "#fff", color: "#b3261e", fontSize: 11, cursor: "pointer",
  },

  // 本棚に反映しますか？
  review: {
    margin: "4px 0 14px", padding: "16px 16px 6px", borderRadius: 14,
    background: "#fdf8ea", border: `1.5px solid ${ACCENT}`,
  },
  reviewTitle: { fontFamily: "serif", fontSize: 16, fontWeight: 700, color: "#2a1f0e", marginBottom: 12 },
  item: {
    padding: "10px 12px", borderRadius: 10, marginBottom: 10,
    background: "#fff", border: "1px solid #ede3c6", transition: "opacity 0.15s",
  },
  itemOn: {},
  itemOff: { opacity: 0.5 },
  itemHead: { display: "flex", alignItems: "center", gap: 8 },
  checkbox: { width: 18, height: 18, accentColor: ACCENT, flexShrink: 0, cursor: "pointer" },
  itemName: {
    flex: 1, minWidth: 0, padding: "5px 8px", borderRadius: 6,
    border: "1px solid #ede3c6", fontSize: 15, fontWeight: 700, color: "#2a1f0e",
    background: "#fff", fontFamily: "inherit",
  },
  badgeOn: {
    flexShrink: 0, padding: "2px 8px", borderRadius: 999, background: "#eef7ee",
    color: "#2e7d32", fontSize: 12, fontWeight: 700,
  },
  badgeOff: {
    flexShrink: 0, padding: "2px 8px", borderRadius: 999, background: "#f2eee6",
    color: "#9a8b76", fontSize: 12, fontWeight: 700,
  },
  chips: { display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8, paddingLeft: 26 },
  chip: {
    maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
    padding: "3px 10px", borderRadius: 999, border: "1px solid #e0d2a8",
    background: "#fffdf6", color: "#5a4a2e", fontSize: 12.5, cursor: "pointer",
  },
  chipOff: { opacity: 0.4, textDecoration: "line-through" },

  // 下部
  inputRow: {
    flexShrink: 0, display: "flex", gap: 8, alignItems: "flex-end",
    padding: "10px 14px 14px", borderTop: "1px solid #ede8da",
  },
  input: {
    flex: 1, resize: "none", padding: "8px 10px", borderRadius: 10,
    border: "1px solid #e0d8c0", fontSize: 15, lineHeight: 1.6, fontFamily: "inherit",
    background: "#fff", color: "#2a1f0e",
  },
  bottomBar: {
    flexShrink: 0, padding: "14px 18px 16px", borderTop: "1px solid #ede8da",
    background: "#fdfaf1",
  },
  bottomText: { fontSize: 14, color: "#6b5a3e", marginBottom: 10, lineHeight: 1.6 },
  bottomActions: { display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" },
  primaryBtn: {
    padding: "9px 18px", borderRadius: 999, border: "none",
    background: ACCENT, color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer",
  },
  secondaryBtn: {
    padding: "9px 16px", borderRadius: 999, border: "1px solid #e0d8c0",
    background: "#fff", color: "#6b5a3e", fontSize: 14, fontWeight: 600, cursor: "pointer",
  },
  disabled: { opacity: 0.5, cursor: "not-allowed" },
};
