// 本棚との対話パネル（育つ本棚の右ペイン）。
//
// 並べ替えを終えて「本棚と話す」を押すと開く。開いたら、待ち中の並べ替えを
// すぐ保存してから /dialogue/start を呼び、知識グラフを読んだLLMが
// 今回の並べ替えについて問いかけるところから会話が始まる。
//
// 会話の途中では意味づけを出さない。LLMが会話を締めくくったとき
// （または持ち主が途中で「対話を終える」を押したとき）に、対話全体から
// まとめた意味づけがそのまま知識グラフ(Concept)に書き込まれ、本棚が育つ。
// 反映するかは持ち主に聞かない（育てるかを持ち主が選ぶのではなく、勝手に育つ）。
//
// おすすめの本は、知識グラフの育ち具合に合わせて自動で足す（/recommend/auto）。本と意味づけの
// つながりが一定数増えるごとに、締めくくりのあとで1冊だけ。意味づけごとの「＋ おすすめの本を加える」は手動。
// 会話の中で「本を5冊入れて」のように頼まれたときも、LLMが知識グラフ（意味づけ・内容テーマ・
// 本棚の本）から1冊ごとの根拠を決め（/recommend/request/plan）、1冊ずつ置く（/recommend/request/item）。
// 意味づけと知識グラフでつながったノードのキーワードで外部検索し、LLMが選んだ1冊を
// 理由と置き場所つきで本棚に置く（/recommend/concept/{concept_id}）。
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
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
  const { myBookshelf, fetchBookshelf, removeBook } = useContext(MyBookshelfContext);
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
  // LLMが会話を締めくくったら true。入力欄の代わりに終了の操作を出す
  const [done, setDone] = useState(false);
  // この対話で本棚に加わった意味づけ（締めくくりのたびに足していく）。
  // [{ proposal_id, concept_id, meaning, isbns, reason }]
  const [grown, setGrown] = useState([]);
  // 直近の締めくくりで加わった件数（下の帯に出す）
  const [lastGrownCount, setLastGrownCount] = useState(0);
  const [llmMode, setLlmMode] = useState(null); // "off" | "mock" | "live"
  // おすすめで置く1冊ごとの状態。キーは意味づけの proposal_id か、お願いの計画の key。
  // { [key]: { status: "waiting" | "loading" | "done" | "removed" | "error", data, error } }
  const [recs, setRecs] = useState({});
  // 会話の中で頼まれた本のお願い。
  // { [requestId]: { wish, count, status: "planning" | "placing" | "done" | "error", plans: [...], error } }
  const [requests, setRequests] = useState({});
  // 締めくくりのあとの自動のおすすめ（知識グラフの育ち具合に合わせて、足すかどうかをサーバーが決める）
  // { status: "loading" | "added" | "waiting" | "no_basis" | "not_found" | "error", progress, ... }
  const [auto, setAuto] = useState(null);
  const listRef = useRef(null);
  const startedRef = useRef(false);

  const titleByIsbn = useMemo(() => {
    const map = {};
    (myBookshelf?.shelves || []).forEach(s => (s.books || []).forEach(b => { map[b.isbn] = b.title; }));
    return map;
  }, [myBookshelf]);

  const hasUserMessage = messages.some(m => m.role === "user");

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
      // 対話が始まると「前回の対話より後に加わった本」の印は消えるので、本棚を取り直す
      fetchBookshelf();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [flushLayoutSync, setHighlightIsbns, dialogueSessionIdRef, fetchBookshelf]);

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

  // 新しい発言や、加わった意味づけ・おすすめが出たら一番下へ
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, grown.length, recs, requests]);

  // おすすめの本を1冊探して置く（意味づけから・お願いから共通）
  const placeBook = useCallback(async (key, path, body) => {
    setRecs(prev => ({ ...prev, [key]: { status: "loading" } }));
    try {
      await flushLayoutSync();
      const data = await postJson(path, body);
      await fetchBookshelf();
      setHighlightIsbns([data.book.isbn]);
      refreshGrowth();
      setRecs(prev => ({ ...prev, [key]: { status: "done", data } }));
    } catch (err) {
      setRecs(prev => ({ ...prev, [key]: { status: "error", error: err.message } }));
    }
  }, [flushLayoutSync, fetchBookshelf, setHighlightIsbns, refreshGrowth]);

  // 意味づけからおすすめの本を探し、LLMが決めた場所に置く
  const recommend = useCallback(async (it) => {
    if (!it.concept_id) return;
    await placeBook(it.proposal_id, `/recommend/concept/${it.concept_id}`);
  }, [placeBook]);

  // 知識グラフが十分に育っていれば、おすすめを1冊足す（足すかどうか・根拠はサーバーが決める）
  const autoRecommend = useCallback(async (conceptIds) => {
    setAuto({ status: "loading" });
    try {
      await flushLayoutSync();
      const data = await postJson("/recommend/auto", { concept_ids: conceptIds });
      if (data.status === "added") {
        await fetchBookshelf();
        setHighlightIsbns([data.recommendation.book.isbn]);
        refreshGrowth();
        setRecs(prev => ({ ...prev, auto: { status: "done", data: data.recommendation } }));
      }
      setAuto(data);
    } catch (err) {
      setAuto({ status: "error", error: err.message });
    }
  }, [flushLayoutSync, fetchBookshelf, setHighlightIsbns, refreshGrowth]);

  // 計画の1冊ぶんを置く
  const placePlannedBook = useCallback((request, plan) => placeBook(plan.key, "/recommend/request/item", {
    basis_kind: plan.basis_kind, basis_key: plan.basis_key, keywords: plan.keywords, aim: plan.aim,
    wish: request.wish, dialogue_session_id: request.sessionId,
  }), [placeBook]);

  // 「本を入れて」と頼まれたとき: 知識グラフから1冊ごとの根拠を決めて、1冊ずつ置く
  const runBookRequest = async ({ count, wish }) => {
    const id = `req-${Date.now()}`;
    const base = { wish, count, sessionId };
    setMessages(prev => [...prev, { role: "request", requestId: id }]);
    setRequests(prev => ({ ...prev, [id]: { ...base, status: "planning", plans: [] } }));
    let plans;
    try {
      await flushLayoutSync();
      const data = await postJson("/recommend/request/plan", { count, wish, dialogue_session_id: sessionId });
      plans = data.plans.map((p, i) => ({ ...p, key: `${id}-${i}` }));
    } catch (err) {
      setRequests(prev => ({ ...prev, [id]: { ...base, status: "error", plans: [], error: err.message } }));
      return;
    }
    setRequests(prev => ({ ...prev, [id]: { ...base, status: "placing", plans } }));
    setRecs(prev => ({ ...prev, ...Object.fromEntries(plans.map(p => [p.key, { status: "waiting" }])) }));
    // 並行すると置き場所がぶつかるため1冊ずつ
    for (const plan of plans) await placePlannedBook(base, plan);
    setRequests(prev => ({ ...prev, [id]: { ...prev[id], status: "done" } }));
  };

  // LLMの返事を画面に反映する（返事・締めくくりで共通）。
  // 締めくくりの意味づけはサーバー側ですでに本棚に加わっているので、見せるだけ
  const applyResponse = async (data) => {
    setMessages(prev => [...prev, { role: "assistant", text: data.message }]);
    setHighlightIsbns(data.focus_isbns || []);
    setDone(!!data.done);
    if (!data.done) {
      if (data.book_request?.count > 0) runBookRequest(data.book_request);
      return;
    }
    const items = (data.proposals || []).filter(p => p.concept_id);
    setLastGrownCount(items.length);
    if (items.length === 0) return;
    setGrown(prev => [...prev, ...items]);
    setAcceptedCount(c => c + items.length);
    refreshGrowth();
    // おすすめは意味づけ1つごとには足さない。知識グラフの育ち具合に合わせて、足すときだけ1冊足す
    autoRecommend(items.map(it => it.concept_id));
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

  // おすすめで置いた本を本棚から外す
  const removeRecommended = async (key) => {
    const rec = recs[key];
    if (!rec?.data) return;
    try {
      await flushLayoutSync();
      await removeBook(rec.data.layout_id);
      await postJson(`/recommend/${rec.data.recommendation_id}/removed`);
      await fetchBookshelf();
      setHighlightIsbns([]);
      setRecs(prev => ({ ...prev, [key]: { ...rec, status: "removed" } }));
    } catch (err) {
      setRecs(prev => ({ ...prev, [key]: { ...rec, error: err.message } }));
    }
  };

  // 締めくくりのあとも話を続けられる。次の締めくくりでは、まだ加わっていない意味づけだけが加わる
  const continueTalking = () => {
    setConceptHighlight(null);
    setDone(false);
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
        <button style={s.endBtn} onClick={onHeaderEnd} disabled={busy}>終える</button>
      </div>

      <div ref={listRef} style={s.list}>
        {messages.map((m, i) => (m.role === "request" ? (
          <RequestBlock
            key={i}
            request={requests[m.requestId]}
            recs={recs}
            onRetry={(plan) => placePlannedBook(requests[m.requestId], plan)}
            onRemove={removeRecommended}
          />
        ) : (
          <div key={i} style={m.role === "user" ? s.rowUser : s.rowAssistant}>
            <div style={m.role === "user" ? s.bubbleUser : s.bubbleAssistant}>{m.text}</div>
          </div>
        )))}

        {grown.length > 0 && (
          <GrownBlock
            items={grown}
            titleByIsbn={titleByIsbn}
            onHover={(isbns) => setConceptHighlight(isbns ? { color: HIGHLIGHT_COLOR, isbns } : null)}
            recs={recs}
            onRecommend={recommend}
            onRemoveRecommended={removeRecommended}
          />
        )}

        {auto && (
          <AutoRecommendBlock auto={auto} rec={recs.auto} onRemove={() => removeRecommended("auto")} />
        )}

        {busy && <div style={s.thinking}>考え中…</div>}
        {error && (
          <div style={s.error}>
            {error}
            {!sessionId && <button style={s.retryBtn} onClick={start}>もう一度</button>}
          </div>
        )}
      </div>

      {done ? (
        <div style={s.bottomBar}>
          <div style={s.bottomText}>
            {lastGrownCount > 0
              ? `✓ 意味づけが${lastGrownCount}件、本棚に加わりました`
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

// 締めくくりで本棚に加わった意味づけと、そこから置いたおすすめの本
function GrownBlock({ items, titleByIsbn, onHover, recs, onRecommend, onRemoveRecommended }) {
  return (
    <div style={s.review}>
      <div style={s.reviewTitle}>本棚に加わった意味づけ</div>
      {items.map(it => (
        <div
          key={it.proposal_id}
          style={s.item}
          onMouseEnter={() => onHover(it.isbns)}
          onMouseLeave={() => onHover(null)}
        >
          <div style={s.itemHead}>
            <span style={s.itemMark}>✓</span>
            <span style={s.itemNameText}>{it.meaning}</span>
          </div>
          <div style={s.chips}>
            {it.isbns.map(isbn => (
              <span key={isbn} style={s.chip}>{titleByIsbn[isbn] || isbn}</span>
            ))}
          </div>
          <RecommendBox
            rec={recs[it.proposal_id]}
            onRecommend={() => onRecommend(it)}
            onRemove={() => onRemoveRecommended(it.proposal_id)}
          />
        </div>
      ))}
    </div>
  );
}

// 会話の中で頼まれた本のお願いと、1冊ごとの根拠・結果
function RequestBlock({ request, recs, onRetry, onRemove }) {
  if (!request) return null;
  const placed = request.plans.filter(p => recs[p.key]?.status === "done").length;
  return (
    <div style={s.review}>
      <div style={s.reviewTitle}>
        お願い：{request.wish ? `「${request.wish}」` : ""}{request.count}冊
        {request.status === "done" && <span style={s.reqCount}>{placed}冊を加えました</span>}
      </div>
      {request.status === "planning" && <div style={s.recWait}>知識グラフから根拠を選んでいます…</div>}
      {request.status === "error" && <div style={s.recError}>{request.error}</div>}
      {request.plans.map(plan => (
        <div key={plan.key} style={s.item}>
          <div style={s.reqBasis}>根拠: {plan.label}</div>
          {plan.aim && <div style={s.recMeta}>{plan.aim}</div>}
          <RecommendBox
            rec={recs[plan.key]}
            onRecommend={() => onRetry(plan)}
            onRemove={() => onRemove(plan.key)}
            idleLabel="この根拠から探す"
          />
        </div>
      ))}
    </div>
  );
}

// 締めくくりのあとの自動のおすすめ。足したときはその1冊、足さなかったときは育ち具合のひと言だけ出す
function AutoRecommendBlock({ auto, rec, onRemove }) {
  if (auto.status === "loading") return <div style={s.autoNote}>知識グラフの育ち具合を見ています…</div>;
  if (auto.status === "added" && rec) {
    return (
      <div style={s.review}>
        <div style={s.reviewTitle}>知識グラフが育ったので、おすすめを1冊加えました</div>
        <div style={s.item}>
          {auto.recommendation?.basis && <div style={s.reqBasis}>根拠: {auto.recommendation.basis}</div>}
          <RecommendBox rec={rec} onRecommend={() => {}} onRemove={onRemove} />
        </div>
      </div>
    );
  }
  const remaining = auto.progress?.remaining;
  const text = {
    waiting: remaining ? `本と意味づけのつながりが、あと${remaining}つ増えると、おすすめの本が加わります` : null,
    no_basis: `本が${auto.min_books || 2}冊以上つながった意味づけができると、そこからおすすめの本が加わります`,
    not_found: "知識グラフは育っていますが、今回はふさわしい本が見つからなかったので加えませんでした",
    error: `おすすめの本を探せませんでした（${auto.error}）`,
  }[auto.status];
  return text ? <div style={s.autoNote}>{text}</div> : null;
}

// おすすめの1冊の状態（探す前・探し中・置いた結果）
function RecommendBox({ rec, onRecommend, onRemove, idleLabel = "＋ この意味づけからおすすめの本を加える" }) {
  if (!rec || rec.status === "error") {
    return (
      <div style={s.rec}>
        <button style={s.recBtn} onClick={onRecommend}>
          {rec?.error ? "もう一度探す" : idleLabel}
        </button>
        {rec?.error && <div style={s.recError}>{rec.error}</div>}
      </div>
    );
  }
  if (rec.status === "waiting") {
    return <div style={{ ...s.rec, ...s.recWait }}>順番を待っています…</div>;
  }
  if (rec.status === "loading") {
    return <div style={{ ...s.rec, ...s.recWait }}>本を探しています…</div>;
  }
  const { book, reason, placement } = rec.data;
  const removed = rec.status === "removed";
  return (
    <div style={{ ...s.rec, ...s.recCard, ...(removed ? s.itemOff : {}) }}>
      <div style={s.recLabel}>{removed ? "本棚から外しました" : "おすすめを本棚に加えました"}</div>
      <div style={s.recTitle}>『{book.title}』</div>
      {book.authors.length > 0 && <div style={s.recMeta}>{book.authors.join("、")}</div>}
      {reason && <div style={s.recReason}>{reason}</div>}
      <div style={s.recMeta}>
        置き場所: {placement.text}{placement.reason ? `。${placement.reason}` : ""}
      </div>
      {!removed && (
        <button style={s.recRemove} onClick={onRemove}>本棚から外す</button>
      )}
      {rec.error && <div style={s.recError}>{rec.error}</div>}
    </div>
  );
}

const s = {
  autoNote: {
    margin: "6px 4px 2px", padding: "8px 12px", borderRadius: 10,
    background: "#f7f3e8", color: "#8a7a5a", fontSize: 12, lineHeight: 1.6,
  },
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

  // 本棚に加わった意味づけ
  review: {
    margin: "4px 0 14px", padding: "16px 16px 6px", borderRadius: 14,
    background: "#fdf8ea", border: `1.5px solid ${ACCENT}`,
  },
  reviewTitle: { fontFamily: "serif", fontSize: 16, fontWeight: 700, color: "#2a1f0e", marginBottom: 12 },
  item: {
    padding: "10px 12px", borderRadius: 10, marginBottom: 10,
    background: "#fff", border: "1px solid #ede3c6", transition: "opacity 0.15s",
  },
  itemOff: { opacity: 0.5 },
  itemHead: { display: "flex", alignItems: "center", gap: 8 },
  itemMark: { width: 18, flexShrink: 0, textAlign: "center", color: "#2e7d32", fontWeight: 700 },
  itemNameText: { flex: 1, minWidth: 0, fontSize: 15, fontWeight: 700, color: "#2a1f0e" },
  chips: { display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8, paddingLeft: 26 },
  chip: {
    maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
    padding: "3px 10px", borderRadius: 999, border: "1px solid #e0d2a8",
    background: "#fffdf6", color: "#5a4a2e", fontSize: 12.5,
  },

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
  // おすすめ
  rec: { marginTop: 10, paddingLeft: 26 },
  recBtn: {
    padding: "5px 12px", borderRadius: 999, border: `1px dashed ${ACCENT}`,
    background: "#fffdf6", color: "#8a7030", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
  },
  recWait: { fontSize: 13, color: "#9a8b76" },
  recCard: {
    marginLeft: 26, paddingLeft: 12, paddingTop: 8, paddingBottom: 8, paddingRight: 10,
    borderLeft: `3px solid ${ACCENT}`, background: "#fffdf6", borderRadius: 6,
  },
  recLabel: { fontSize: 11.5, fontWeight: 700, color: "#8a7030", marginBottom: 2 },
  recTitle: { fontSize: 14, fontWeight: 700, color: "#2a1f0e", lineHeight: 1.5 },
  recReason: { fontSize: 13, color: "#3d3020", lineHeight: 1.7, marginTop: 4 },
  recMeta: { fontSize: 12, color: "#9a8b76", lineHeight: 1.6, marginTop: 2 },
  recRemove: {
    marginTop: 6, padding: "3px 10px", borderRadius: 999, border: "1px solid #e0d8c0",
    background: "#fff", color: "#6b5a3e", fontSize: 12, cursor: "pointer",
  },
  reqBasis: { fontSize: 13.5, fontWeight: 700, color: "#2a1f0e" },
  reqCount: { marginLeft: 8, fontSize: 12, fontWeight: 600, color: "#2e7d32", fontFamily: "inherit" },
  recError: { fontSize: 12, color: "#b3261e", marginTop: 4, lineHeight: 1.6 },
  linkBtn: {
    padding: "9px 4px", border: "none", background: "none",
    color: "#8a7030", fontSize: 14, fontWeight: 600, cursor: "pointer", textDecoration: "underline",
  },
};
