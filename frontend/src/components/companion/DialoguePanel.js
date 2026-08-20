// 左ペイン「発見と対話」の中身（設計書5章の発見エンジン ＋ 6.1の対話パネル）。
//
// 発見はカードとして別置きにせず、棚が自分から話しかけてきたAIの発言として
// チャットの流れにそのまま乗せる。発見を見ることと、それについて話すことを
// 分けてしまうと、対話が発見から切り離されてしまうため。
// はい／ちがう／一部ちがうの返答ボタンはバブルの下に添えて構造化データは
// そのまま記録しつつ、何もなくてもユーザーは自由に文章を打って話しかけられる。
import { useCallback, useEffect, useRef, useState } from "react";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";
import DiscoveryResponse from "./DiscoveryResponse";

const API = "http://localhost:8000";

const TYPE_LABEL = {
  commonality: "共通点",
  contradiction: "食い違い",
  implicit_pattern: "並べ方の癖",
  structural: "全体の構造",
};

export default function DialoguePanel() {
  const {
    setHighlightIsbns, chatSeed, setChatSeed, refreshGrowth,
    pendingDiscoveries: pending, answeredDiscoveries: answered, answerDiscovery,
    activeDiscoveryId, setActiveDiscoveryId,
    isAnalyzing,
  } = useShelfWorkspace();

  const [history, setHistory] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);
  const forcedCheckedRef = useRef(false);

  // スクロールするのは右ペイン全体なので、末尾を見える位置まで送る
  useEffect(() => {
    if (history.length === 0) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [history, isLoading]);

  // 対話が根拠にした本を、本棚側のハイライトに伝える
  useEffect(() => {
    const lastAi = [...history].reverse().find(m => m.role === "ai");
    setHighlightIsbns(lastAi?.relatedIsbns || []);
  }, [history, setHighlightIsbns]);

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

  // 本棚側からの語りかけ。開いた直後に一度だけ確認する。
  useEffect(() => {
    if (forcedCheckedRef.current) return;
    forcedCheckedRef.current = true;
    fetch(`${API}/knowledge_graph/forced-whisper`)
      .then(res => (res.ok ? res.json() : null))
      .then(json => {
        if (!json?.forced) return;
        setHistory(h => (h.length ? h : [{
          role: "ai", text: json.reply, relatedIsbns: json.related_isbns || [],
        }]));
      })
      .catch(err => console.error("本棚からの語りかけを取得できませんでした", err));
  }, []);

  // 発見カードの「もっと話す」から会話へ引き継ぐ（設計書6.2の2段階目）
  useEffect(() => {
    if (!chatSeed) return;
    setHistory(h => [...h, { role: "ai", text: chatSeed.question, relatedIsbns: chatSeed.isbns || [] }]);
    setChatSeed(null);
  }, [chatSeed, setChatSeed]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    const prior = history;
    setHistory(h => [...h, { role: "user", text }]);
    setInput("");
    setError(null);
    setIsLoading(true);
    try {
      const reply = await ask(prior, text);
      setHistory(h => [...h, { role: "ai", ...reply }]);
      refreshGrowth();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, history, ask, refreshGrowth]);

  const focusDiscovery = useCallback((d) => {
    // 同じカードをもう一度押したら選択を外す
    setActiveDiscoveryId(prev => (prev === d.discovery_id ? null : d.discovery_id));
    setHighlightIsbns(d.related_book_ids || []);
  }, [setActiveDiscoveryId, setHighlightIsbns]);

  const hasAnything = pending.length > 0 || history.length > 0;

  return (
    <div style={s.wrap}>
      {history.length > 0 && (
        <div style={s.head}>
          <button style={s.clearBtn} onClick={() => setHistory([])}>会話を消す</button>
        </div>
      )}

      <div style={s.stream}>
        {!hasAnything && !isAnalyzing && (
          <div style={s.placeholder}>
            <p style={s.placeholderText}>
              棚が自分で気づいたことを探しています。見つかると本棚に「！」の印が付きます。
              気になったことがあれば、いつでも自分から話しかけてかまいません。
            </p>
          </div>
        )}

        {isAnalyzing && <div style={s.systemNote}>棚を読んでいます…</div>}

        {/* ── 棚からの発見。カードではなく、棚が自分から話しかけてきた
            AIの発言として流す。返答ボタンだけバブルの下に添える ── */}
        {pending.map(d => {
          const isActive = d.discovery_id === activeDiscoveryId;
          return (
            <div key={d.discovery_id} style={s.findingGroup}>
              <div
                style={{ ...s.bubbleAi, ...s.findingBubble, ...(isActive ? s.findingBubbleActive : {}) }}
                onClick={() => focusDiscovery(d)}
                onMouseEnter={() => setHighlightIsbns(d.related_book_ids || [])}
                onMouseLeave={() => setHighlightIsbns([])}
              >
                <div style={s.findingHead}>
                  <span style={s.typeBadge}>{TYPE_LABEL[d.type] || "気づき"}</span>
                  {(d.related_book_ids || []).length > 0 && (
                    <span style={s.evidenceHint}>{d.related_book_ids.length}冊にまたがる話</span>
                  )}
                </div>

                <div style={s.question}>{d.generated_question}</div>
                {d.body && <div style={s.body}>{d.body}</div>}

                {(d.related_book_ids || []).length > 0 && (
                  <div style={s.coverRow}>
                    {d.related_book_ids.slice(0, 8).map(isbn => (
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

              {/* ボタン操作でバブルの選択が切り替わらないよう、伝播を止める */}
              <div style={s.findingActions} onClick={e => e.stopPropagation()}>
                <DiscoveryResponse
                  discovery={d}
                  onAnswer={answerDiscovery}
                  onTalkMore={() => setChatSeed({
                    question: d.generated_question,
                    isbns: d.related_book_ids || [],
                  })}
                />
              </div>
            </div>
          );
        })}

        {/* 答え終わった発見は一行だけ残す（何に答えたかの記録） */}
        {answered.slice(0, 6).map(d => (
          <div key={d.discovery_id} style={s.answeredLine}>
            <span style={s.answeredMark}>
              {d.status === "confirmed" ? "◎" : d.status === "rejected" ? "×" : "△"}
            </span>
            <span style={s.answeredText}>{d.generated_question}</span>
          </div>
        ))}

        {/* ── 発見をめぐる会話 ── */}
        {history.map((m, i) => (
          m.role === "user" ? (
            <div key={i} style={s.bubbleUser}>{m.text}</div>
          ) : (
            <div key={i} style={s.bubbleAi}>
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
          )
        ))}

        {isLoading && <div style={s.bubbleAi}>考え中…</div>}
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
          disabled={isLoading}
        />
        <button style={s.sendBtn} onClick={send} disabled={isLoading || !input.trim()}>
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

  // 発見バブル＋返答ボタンをひとまとまりにして、AIの発言として左寄せに流す
  findingGroup: {
    alignSelf: "flex-start", maxWidth: "92%",
    display: "flex", flexDirection: "column", gap: 6,
  },
  findingBubble: {
    display: "flex", flexDirection: "column", gap: 8, cursor: "pointer",
    borderLeft: "3px solid #e0d5b8",
    maxWidth: "100%", // 幅は外側の findingGroup（92%）に任せる
  },
  findingBubbleActive: {
    borderLeftColor: "#c9a84c", background: "#fffdf5",
    boxShadow: "0 2px 12px rgba(201,168,76,0.18)",
  },
  findingActions: { paddingLeft: 4 },
  findingHead: { display: "flex", alignItems: "center", gap: 8 },
  typeBadge: {
    fontSize: 9, fontWeight: 700, color: "#c9a84c",
    border: "1px solid #e8dcb8", borderRadius: 999, padding: "1px 7px",
    letterSpacing: "0.04em", whiteSpace: "nowrap",
  },
  evidenceHint: { fontSize: 9.5, color: "#b3a692", marginLeft: "auto" },
  question: { fontSize: 12.5, fontWeight: 600, color: "#2a1f0e", lineHeight: 1.6 },
  body: { fontSize: 11, color: "#6b5c47", lineHeight: 1.7 },

  answeredLine: {
    display: "flex", gap: 7, alignItems: "baseline",
    fontSize: 10.5, color: "#b3a692", lineHeight: 1.5, padding: "0 2px",
  },
  answeredMark: { color: "#c9a84c", flexShrink: 0 },
  answeredText: {
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
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
  sendBtn: {
    padding: "8px 14px", background: "#ff9d3d", color: "#fff",
    border: "none", borderRadius: 10, cursor: "pointer",
    fontSize: 12.5, fontWeight: 600, flexShrink: 0,
  },
};
