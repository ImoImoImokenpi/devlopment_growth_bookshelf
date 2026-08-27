// 「他の参加者の本棚を観察する」画面の対話ペイン。
//
// DialoguePanel.js（自分の棚についての対話）を土台にした簡略版。
// forced-whisper・要約からの意味づけ書き戻しループは持たない
// （相手の蔵書には一切書き込まない、対話ログの保存のみ）。
// 根拠は自分と相手、双方の知識グラフの構造的な違い
// （バックエンドの /knowledge_graph/compare/{otherId} 系エンドポイント）。
import { useCallback, useEffect, useRef, useState } from "react";

const API = "http://localhost:8000";

const NDC_LABELS = {
  "0": "総記", "1": "哲学", "2": "歴史・地理", "3": "社会科学",
  "4": "自然科学", "5": "技術", "6": "産業", "7": "芸術", "8": "言語", "9": "文学",
};

function topNdcLabel(overview) {
  const rows = overview?.ndc_distribution || [];
  if (!rows[0]) return "―";
  const name = NDC_LABELS[rows[0].ndc_l1] || rows[0].ndc_l1 || "不明";
  return `${name}（${rows[0].book_count}冊）`;
}

export default function ComparisonDialoguePanel({ otherId }) {
  const [history, setHistory] = useState([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);
  const bottomRef = useRef(null);
  const openedForRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setHistory([]);
    setStats(null);
    setError(null);
    setIsHistoryLoading(true);

    fetch(`${API}/knowledge_graph/compare/${otherId}`)
      .then(res => (res.ok ? res.json() : null))
      .then(json => { if (!cancelled) setStats(json); })
      .catch(err => console.error("比較統計の取得に失敗しました", err));

    (async () => {
      try {
        const res = await fetch(`${API}/knowledge_graph/compare/${otherId}/chat-history`);
        const json = res.ok ? await res.json() : null;
        const loaded = (json?.messages || []).map(m => ({
          role: m.role, text: m.text, relatedIsbns: m.related_isbns || [], at: m.created_at,
        }));
        if (cancelled) return;
        setHistory(loaded);
        setIsHistoryLoading(false);

        // 初回（履歴が空）だけ、統計を根拠にした開口一言を取りに行く
        if (loaded.length === 0 && openedForRef.current !== otherId) {
          openedForRef.current = otherId;
          setIsLoading(true);
          const openRes = await fetch(`${API}/knowledge_graph/compare/${otherId}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ history: [], message: null }),
          });
          const openData = await openRes.json().catch(() => null);
          if (!cancelled && openRes.ok && openData) {
            setHistory([{
              role: "ai", text: openData.reply,
              relatedIsbns: openData.related_isbns || [], at: new Date().toISOString(),
            }]);
          }
          if (!cancelled) setIsLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("比較対話の取得に失敗しました", err);
          setIsHistoryLoading(false);
          setIsLoading(false);
        }
      }
    })();

    return () => { cancelled = true; };
  }, [otherId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [history, isLoading]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    const prior = history;
    setHistory(h => [...h, { role: "user", text, at: new Date().toISOString() }]);
    setInput("");
    setError(null);
    setIsLoading(true);
    try {
      const res = await fetch(`${API}/knowledge_graph/compare/${otherId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          history: prior.map(({ role, text }) => ({ role, text })),
          message: text,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || "対話に失敗しました");
      setHistory(h => [...h, {
        role: "ai", text: data.reply, relatedIsbns: data.related_isbns || [], at: new Date().toISOString(),
      }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, history, otherId]);

  const clearHistory = useCallback(async () => {
    setHistory([]);
    try {
      await fetch(`${API}/knowledge_graph/compare/${otherId}/chat-history`, { method: "DELETE" });
    } catch (err) {
      console.error("比較対話履歴の削除に失敗しました", err);
    }
  }, [otherId]);

  return (
    <div style={s.wrap}>
      <div style={s.head}>
        <span style={s.headTitle}>本棚の違いを話す</span>
        {history.length > 0 && (
          <button style={s.clearBtn} onClick={clearHistory}>会話を消す</button>
        )}
      </div>

      {stats && (
        <div style={s.statsCard}>
          <div style={s.statsRow}>
            <span style={s.statsLabel}>あなた</span>
            <span style={s.statsValue}>
              {stats.me.overview.total_books}冊 ／ よく読むジャンル: {topNdcLabel(stats.me.overview)}
            </span>
          </div>
          <div style={s.statsRow}>
            <span style={s.statsLabel}>{otherId}</span>
            <span style={s.statsValue}>
              {stats.other.overview.total_books}冊 ／ よく読むジャンル: {topNdcLabel(stats.other.overview)}
            </span>
          </div>
        </div>
      )}

      <div style={s.stream}>
        {isHistoryLoading && <div style={s.systemNote}>読み込んでいます…</div>}

        {history.map((m, i) => (
          <div key={i} style={s.msgUnit}>
            {m.role === "user" ? (
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
          placeholder="気になった違いを聞いてみましょう…"
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
  wrap: {
    display: "flex", flexDirection: "column",
    width: "100%", height: "100%",
    background: "#fdfcf8", borderRight: "1px solid #ede8da",
    overflow: "hidden",
  },
  head: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "12px 14px 8px", flexShrink: 0,
  },
  headTitle: { fontSize: 12.5, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif" },
  clearBtn: {
    background: "transparent", border: "none", color: "#9a8b76",
    fontSize: 10.5, cursor: "pointer", padding: "2px 4px",
  },
  statsCard: {
    margin: "0 14px 8px", padding: "8px 10px", borderRadius: 8,
    background: "#fffdf5", border: "1px solid #ede8da",
    display: "flex", flexDirection: "column", gap: 4, flexShrink: 0,
  },
  statsRow: { display: "flex", gap: 8, fontSize: 11, alignItems: "baseline" },
  statsLabel: { fontWeight: 700, color: "#8a5a1f", minWidth: 44 },
  statsValue: { color: "#4a3728" },
  stream: {
    flex: 1, overflowY: "auto", padding: "4px 14px 12px",
    display: "flex", flexDirection: "column", gap: 10, minHeight: 0,
  },
  systemNote: { fontSize: 11.5, color: "#9a8b76", textAlign: "center", padding: "8px 0" },
  msgUnit: { display: "flex", flexDirection: "column", gap: 10 },
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
    flexShrink: 0, display: "flex", gap: 8, padding: "10px 12px",
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
