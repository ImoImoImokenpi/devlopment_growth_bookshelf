// 左ペイン「発見と対話」の中身（設計書5章の発見エンジン ＋ 6.1の対話パネル）。
//
// 発見そのもの（未回答・回答済みとも）は上の DiscoveryList にまとまっていて、
// はい／いいえ／さらに話す の一次回答もそこで完結する。ここは「さらに話す」で
// 引き継がれた話題と、それ以外の自由な雑談だけが流れる純粋な対話ストリーム。
import { useCallback, useEffect, useRef, useState } from "react";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";

const API = "http://localhost:8000";

// 履歴に日付の区切りを入れるための単位（ローカル日付のYYYY-MM-DD）
function dayKey(iso) {
  const d = iso ? new Date(iso) : new Date();
  if (Number.isNaN(d.getTime())) return null;
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function formatDayLabel(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (dayKey(iso) === dayKey(today.toISOString())) return "今日";
  if (dayKey(iso) === dayKey(yesterday.toISOString())) return "昨日";
  return d.toLocaleDateString("ja-JP", { month: "long", day: "numeric", weekday: "short" });
}

export default function DialoguePanel() {
  const {
    setHighlightIsbns, chatSeed, setChatSeed, refreshGrowth,
    pendingDiscoveries: pending,
    isAnalyzing, setIsChatBusy, bumpConceptsVersion,
    isDialogueOpen,
  } = useShelfWorkspace();

  const [history, setHistory] = useState([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  // 「終わる」を押した直後：直前の区切り以降の会話から意味づけを提案できないか
  // AIに振り返らせている間 / 提案をユーザーに確認してもらっている間の状態。
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [pendingSummary, setPendingSummary] = useState(null); // { summary, relatedIsbns } | null
  const bottomRef = useRef(null);
  const forcedCheckedRef = useRef(false);
  const didInitialScrollRef = useRef(false);

  // 返信待ち・振り返り中・確認待ちのどれかの間は、発見一覧側の「さらに話す」を
  // 封じる（2つの会話が同じストリームに同時に流れ込んで順序が乱れるのを防ぐ）。
  useEffect(() => {
    setIsChatBusy(isLoading || isSummarizing || !!pendingSummary);
  }, [isLoading, isSummarizing, pendingSummary, setIsChatBusy]);

  // スクロールするのは右ペイン全体なので、末尾を見える位置まで送る。
  // 過去の対話を読み込んだ直後は、いきなりスクロールアニメーションが
  // 走ると目がちらつくので最初の一回だけ即座に飛ぶ。
  useEffect(() => {
    if (history.length === 0) return;
    const behavior = didInitialScrollRef.current ? "smooth" : "auto";
    didInitialScrollRef.current = true;
    bottomRef.current?.scrollIntoView({ behavior, block: "nearest" });
  }, [history, isLoading]);

  // 対話が根拠にした本を、本棚側のハイライトに伝える。
  // パネルが閉じている（isDialogueOpen=false）間は、見えていないパネルの
  // 会話内容で棚だけが光り続けるのを避けるため、ハイライトを出さない。
  useEffect(() => {
    if (!isDialogueOpen) { setHighlightIsbns([]); return; }
    const lastAi = [...history].reverse().find(m => m.role === "ai");
    setHighlightIsbns(lastAi?.relatedIsbns || []);
  }, [history, isDialogueOpen, setHighlightIsbns]);

  const ask = useCallback(async (priorHistory, message) => {
    const res = await fetch(`${API}/knowledge_graph/book-chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        history: priorHistory.map(({ role, text }) => ({ role, text })),
        message,
      }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(data?.detail || "対話に失敗しました");
    return { text: data.reply, relatedIsbns: data.related_isbns || [] };
  }, []);

  // 開いた直後に一度だけ：①過去の対話履歴を読み込み、②本棚側からの
  // 強制的な語りかけがないか確認する（②は①の後）。
  // 履歴はReact stateだけで持っていた頃はリロードで消えていたが、
  // 被験者ごとにバックエンド側へ永続化したものを読み直すようにした
  // （participant.js の通り、機器を複数被験者で共有する研究運用のため
  // localStorageではなくバックエンド側に持たせている）。
  useEffect(() => {
    if (forcedCheckedRef.current) return;
    forcedCheckedRef.current = true;

    (async () => {
      try {
        const res = await fetch(`${API}/knowledge_graph/chat-history`);
        const json = res.ok ? await res.json() : null;
        const loaded = (json?.messages || []).map(m => ({
          role: m.role,
          text: m.text,
          relatedIsbns: m.related_isbns || [],
          at: m.created_at,
        }));
        setHistory(loaded);
      } catch (err) {
        console.error("対話履歴を取得できませんでした", err);
      } finally {
        setIsHistoryLoading(false);
      }

      try {
        const res = await fetch(`${API}/knowledge_graph/forced-whisper`);
        const json = res.ok ? await res.json() : null;
        if (!json?.forced) return;
        setHistory(h => [...h, {
          role: "ai", text: json.reply, relatedIsbns: json.related_isbns || [], at: new Date().toISOString(),
        }]);
      } catch (err) {
        console.error("本棚からの語りかけを取得できませんでした", err);
      }
    })();
  }, []);

  // 発見一覧の「さらに話す」から会話へ引き継ぐ（設計書6.2の2段階目）
  useEffect(() => {
    if (!chatSeed) return;
    const text = chatSeed.question;
    const relatedIsbns = chatSeed.isbns || [];
    setHistory(h => [...h, { role: "ai", text, relatedIsbns, at: new Date().toISOString() }]);
    setChatSeed(null);
    fetch(`${API}/knowledge_graph/chat-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "ai", text, related_isbns: relatedIsbns }),
    }).catch(err => console.error("対話履歴の保存に失敗しました", err));
  }, [chatSeed, setChatSeed]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    const prior = history;
    setHistory(h => [...h, { role: "user", text, at: new Date().toISOString() }]);
    setInput("");
    setError(null);
    setIsLoading(true);
    try {
      const reply = await ask(prior, text);
      setHistory(h => [...h, { role: "ai", ...reply, at: new Date().toISOString() }]);
      refreshGrowth();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, history, ask, refreshGrowth]);

  const hasAnything = history.length > 0;

  // 区切り線そのものの挿入（要約を書き戻す/書き戻さないが決まった後、必ず最後に呼ぶ）
  const insertDivider = useCallback(() => {
    const at = new Date().toISOString();
    setHistory(h => [...h, { role: "divider", text: "話題を終えました", at }]);
    setHighlightIsbns([]);
    fetch(`${API}/knowledge_graph/chat-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "divider", text: "話題を終えました", related_isbns: [] }),
    }).catch(err => console.error("対話履歴の保存に失敗しました", err));
  }, [setHighlightIsbns]);

  // 「対話の終わりが分からない」問題への対応：話し終えたら自分で
  // 区切りを打てるようにする。ただし区切るだけで終わらせず、直前の区切り
  // 以降のやり取りをAIに振り返らせ、意味づけとして知識グラフに残せそうなら
  // 確認を挟む（発見と同じく、AIの仮説→ユーザーの確認、の順を守る）。
  const endTopic = useCallback(async () => {
    if (isLoading || isSummarizing || pendingSummary || history.length === 0) return;
    const lastDividerIndex = history.reduce((acc, m, i) => (m.role === "divider" ? i : acc), -1);
    const segment = history.slice(lastDividerIndex + 1);
    if (segment.length === 0) return; // 前回の区切りから何も話していない

    setIsSummarizing(true);
    try {
      const res = await fetch(`${API}/knowledge_graph/chat-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ history: segment.map(({ role, text }) => ({ role, text })) }),
      });
      const data = await res.json().catch(() => null);
      // 関連本は、その区間でAIが言及したISBNをそのまま束ねる
      // （LLMに改めて選ばせず、既に検証済みの情報だけを使う）。どの本のことか
      // 特定できない要約は書き戻しようがないので、確認自体を出さない。
      const relatedIsbns = [...new Set(segment.flatMap(m => m.relatedIsbns || []))];
      if (res.ok && data?.summarizable && relatedIsbns.length > 0) {
        setPendingSummary({ summary: data.summary, relatedIsbns });
        return; // 区切り線はユーザーの確認後にまとめて打つ
      }
    } catch (err) {
      console.error("会話の振り返りに失敗しました", err);
    } finally {
      setIsSummarizing(false);
    }
    insertDivider();
  }, [isLoading, isSummarizing, pendingSummary, history, insertDivider]);

  const resolveSummary = useCallback(async (accept) => {
    const summary = pendingSummary;
    setPendingSummary(null);
    if (accept && summary && summary.relatedIsbns.length > 0) {
      try {
        const res = await fetch(`${API}/knowledge_graph/chat-summary/confirm`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ summary: summary.summary, related_isbns: summary.relatedIsbns }),
        });
        if (!res.ok) throw new Error(await res.text());
        bumpConceptsVersion();
      } catch (err) {
        console.error("意味づけの記録に失敗しました", err);
      }
    }
    insertDivider();
  }, [pendingSummary, insertDivider, bumpConceptsVersion]);

  const clearHistory = useCallback(async () => {
    // 消した後に取り消せないので、うっかり押しても被害が小さいよう
    // バックエンドへの削除は先に投げつつ画面は即座に空にする
    // （応答を待たせるとボタンの手応えが鈍るため）。
    setHistory([]);
    try {
      await fetch(`${API}/knowledge_graph/chat-history`, { method: "DELETE" });
    } catch (err) {
      console.error("対話履歴の削除に失敗しました", err);
    }
  }, []);

  return (
    <div style={s.wrap}>
      {history.length > 0 && (
        <div style={s.head}>
          <button style={s.clearBtn} onClick={clearHistory}>会話を消す</button>
        </div>
      )}

      <div style={s.stream}>
        {!hasAnything && !isAnalyzing && !isHistoryLoading && (
          <div style={s.placeholder}>
            <p style={s.placeholderText}>
              {pending.length > 0
                ? "上の「発見」に新しい気づきがたまっています。見てみましょう。"
                : "気になったことがあれば、話しかけてみよう！"}
            </p>
          </div>
        )}

        {isAnalyzing && <div style={s.systemNote}>棚を読んでいます…</div>}

        {/* ── 発見をめぐる会話。過去の対話を思い返せるよう、日付が変わる
            ところに区切りを挟んで連続したストリームとして流す ── */}
        {history.map((m, i) => {
          const showDivider = i === 0 || dayKey(m.at) !== dayKey(history[i - 1].at);
          return (
            <div key={i} style={s.msgUnit}>
              {showDivider && m.at && (
                <div style={s.dayDivider}>
                  <span style={s.dayDividerLabel}>{formatDayLabel(m.at)}</span>
                </div>
              )}
              {m.role === "divider" ? (
                <div style={s.topicEnd}>
                  <span style={s.topicEndLine} />
                  <span style={s.topicEndLabel}>話題を終えました</span>
                  <span style={s.topicEndLine} />
                </div>
              ) : m.role === "user" ? (
                <div style={s.bubbleUser}>{m.text}</div>
              ) : (
                <div style={s.bubbleAi}>
                  <div>{m.text}</div>
                  {(m.relatedIsbns || []).length > 0 && (
                    <div style={s.coverRow}>
                      {m.relatedIsbns.map(isbn => (
                        <img
                          key={isbn}
                          src={`${API}/register/cover/${isbn}`}
                          alt=""
                          style={s.cover}
                          onError={e => { e.target.style.display = "none"; }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {isLoading && <div style={s.bubbleAi}>考え中…</div>}
        {isSummarizing && <div style={s.systemNote}>ここまでの話を振り返っています…</div>}

        {pendingSummary && (
          <div style={s.summaryCard}>
            <div style={s.summaryLabel}>この話から、こんな意味づけを本棚に残しますか？</div>
            <div style={s.summaryText}>「{pendingSummary.summary}」</div>
            <div style={s.summaryBtnRow}>
              <button style={{ ...s.summaryBtn, ...s.summaryBtnYes }} onClick={() => resolveSummary(true)}>
                はい、残す
              </button>
              <button style={s.summaryBtn} onClick={() => resolveSummary(false)}>いいえ</button>
            </div>
          </div>
        )}

        {error && <div style={s.error}>{error}</div>}
        <div ref={bottomRef} />
      </div>

      <div style={s.inputRow}>
        <input
          style={s.input}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          placeholder="気になったことを書いてみましょう…"
          disabled={isLoading || isSummarizing || !!pendingSummary}
        />
        <button
          style={s.endBtn}
          onClick={endTopic}
          disabled={isLoading || isSummarizing || !!pendingSummary || history.length === 0}
          title="ここまでの話題に区切りを付けます"
        >
          終わる
        </button>
        <button
          style={s.sendBtn}
          onClick={send}
          disabled={isLoading || isSummarizing || !!pendingSummary || !input.trim()}
        >
          送る
        </button>
      </div>
    </div>
  );
}

const s = {
  // 内側にスクロールを持たない。右ペイン全体が1つのスクロールになっている。
  wrap: { flex: 1, display: "flex", flexDirection: "column" },
  head: {
    display: "flex", justifyContent: "flex-end", alignItems: "center",
    padding: "10px 14px 8px",
  },
  clearBtn: {
    background: "transparent", border: "none", color: "#9a8b76",
    fontSize: 10.5, cursor: "pointer", padding: "2px 4px",
  },
  stream: {
    flex: 1, padding: "4px 14px 12px",
    display: "flex", flexDirection: "column", gap: 10,
    minHeight: 150,
  },
  placeholder: { margin: "auto 0", textAlign: "center", padding: "16px 8px" },
  placeholderText: { fontSize: 12, color: "#9a8b76", lineHeight: 1.9 },
  systemNote: { fontSize: 11.5, color: "#9a8b76", textAlign: "center", padding: "8px 0" },

  msgUnit: { display: "flex", flexDirection: "column", gap: 10 },
  dayDivider: {
    display: "flex", justifyContent: "center", margin: "6px 0 2px",
  },
  dayDividerLabel: {
    fontSize: 10, fontWeight: 700, color: "#a89a84", background: "#f3efe3",
    borderRadius: 999, padding: "3px 12px", letterSpacing: "0.03em",
  },
  // 「終わる」で挿入する話題の区切り。日付区切りとは別物と分かるよう、
  // ピル型ではなく水平線+ラベルの、より控えめな見た目にする。
  topicEnd: {
    display: "flex", alignItems: "center", gap: 8,
    margin: "4px 0", opacity: 0.8,
  },
  topicEndLine: { flex: 1, height: 1, background: "#e5ded0" },
  topicEndLabel: {
    fontSize: 10, color: "#b3a692", whiteSpace: "nowrap",
  },
  bubbleUser: {
    alignSelf: "flex-end", maxWidth: "88%", padding: "8px 12px",
    borderRadius: "14px 14px 2px 14px", background: "#ff9d3d",
    color: "#fff", fontSize: 12.5, lineHeight: 1.65, whiteSpace: "pre-wrap",
  },
  bubbleAi: {
    alignSelf: "flex-start", maxWidth: "92%", padding: "8px 12px",
    borderRadius: "14px 14px 14px 2px", background: "#fff",
    color: "#2a1f0e", fontSize: 12.5, lineHeight: 1.65, whiteSpace: "pre-wrap",
    border: "1px solid #ede8da",
  },
  coverRow: {
    display: "flex", gap: 5, overflowX: "auto",
    paddingTop: 6, marginTop: 2, borderTop: "1px solid #f0ece1",
  },
  cover: {
    width: 28, height: 40, objectFit: "cover", borderRadius: 3,
    background: "#eee", flexShrink: 0,
  },
  // 「終わる」で振り返った結果の確認カード。発見一覧の行と同じ
  // ゴールドのアクセント言語で、知識グラフへの書き戻しという意味の重さを揃える。
  summaryCard: {
    alignSelf: "stretch", display: "flex", flexDirection: "column", gap: 8,
    borderRadius: 10, borderLeft: "3px solid #c9a84c", background: "#fffdf5",
    padding: "10px 12px 10px 10px",
  },
  summaryLabel: { fontSize: 11, color: "#8a7a63" },
  summaryText: { fontSize: 12.5, fontWeight: 600, color: "#2a1f0e", lineHeight: 1.6 },
  summaryBtnRow: { display: "flex", gap: 6 },
  summaryBtn: {
    padding: "6px 14px", fontSize: 11.5, fontWeight: 600,
    color: "#4a3728", background: "#fff",
    border: "1.5px solid #e0d5b8", borderRadius: 999, cursor: "pointer",
  },
  summaryBtnYes: { color: "#fff", background: "#c9a84c", borderColor: "#c9a84c" },
  error: {
    alignSelf: "center", fontSize: 11.5, color: "#c9506a",
    padding: "8px 12px", borderRadius: 10, background: "#fff0f2",
  },
  inputRow: {
    position: "sticky", bottom: 0, zIndex: 2,
    display: "flex", gap: 8, padding: "10px 12px",
    borderTop: "1px solid #ede8da", background: "#fdfcf8",
  },
  input: {
    flex: 1, minWidth: 0, padding: "8px 10px", borderRadius: 8,
    border: "1px solid #e5ded0", fontSize: 12.5,
  },
  endBtn: {
    padding: "8px 12px", background: "#fff", color: "#8a7a63",
    border: "1.5px solid #e0d5b8", borderRadius: 10, cursor: "pointer",
    fontSize: 12.5, fontWeight: 600, flexShrink: 0,
  },
  sendBtn: {
    padding: "8px 14px", background: "#ff9d3d", color: "#fff",
    border: "none", borderRadius: 10, cursor: "pointer",
    fontSize: 12.5, fontWeight: 600, flexShrink: 0,
  },
};
