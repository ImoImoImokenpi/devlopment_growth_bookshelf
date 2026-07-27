import React, { useState, useRef, useEffect, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { NODE_CFG, LINK_CFG, nodeDisplayLabel } from "../utils/graphConfig";

const API = "http://localhost:8000";
const GRAPH_WIDTH = 320;

function AnalysisChatPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [chatHistory, setChatHistory] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const messagesRef = useRef(null);

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [chatHistory, isLoading]);

  const fetchSubgraph = useCallback(async (isbns) => {
    if (!isbns || isbns.length < 2) return { nodes: [], links: [] };
    try {
      const res = await fetch(`${API}/knowledge_graph/subgraph`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isbns }),
      });
      if (!res.ok) return { nodes: [], links: [] };
      return await res.json();
    } catch {
      return { nodes: [], links: [] };
    }
  }, []);

  const fetchReply = useCallback(async (history, message) => {
    const res = await fetch(`${API}/knowledge_graph/analyze-chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        history: history.map(({ role, text }) => ({ role, text })),
        message,
      }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(data?.detail || "対話に失敗しました");
    const relatedIsbns = data.related_isbns || [];
    const subgraph = await fetchSubgraph(relatedIsbns);
    return { text: data.reply, relatedIsbns, subgraph };
  }, [fetchSubgraph]);

  const handleOpen = useCallback(async () => {
    setIsOpen(true);
    if (chatHistory.length > 0) return;
    setError(null);
    setIsLoading(true);
    try {
      const aiMessage = await fetchReply([], null);
      setChatHistory([{ role: "ai", ...aiMessage }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [chatHistory, fetchReply]);

  const handleSend = useCallback(async () => {
    const text = chatInput.trim();
    if (!text || isLoading) return;
    const historyBeforeSend = chatHistory;
    setChatHistory(h => [...h, { role: "user", text }]);
    setChatInput("");
    setError(null);
    setIsLoading(true);
    try {
      const aiMessage = await fetchReply(historyBeforeSend, text);
      setChatHistory(h => [...h, { role: "ai", ...aiMessage }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [chatInput, isLoading, chatHistory, fetchReply]);

  const nodeCanvasObject = useCallback((node, ctx, scale) => {
    const cfg = NODE_CFG[node.type] ?? { color: "#aaa", r: 5 };
    const r = cfg.r ?? 5;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = cfg.color;
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.4)";
    ctx.lineWidth = 0.8;
    ctx.stroke();

    if (scale > 1.4) {
      const label = nodeDisplayLabel(node);
      if (label) {
        const fs = Math.max(5, 9 / scale);
        ctx.font = `${fs}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "rgba(255,255,255,0.85)";
        const t = label.length > 10 ? label.slice(0, 10) + "…" : label;
        ctx.fillText(t, node.x, node.y + r + 2);
      }
    }
  }, []);

  const linkColor = useCallback(link => {
    const base = LINK_CFG[link.type]?.color ?? "#888888";
    return base + "aa";
  }, []);

  return (
    <>
      <div style={s.fab} onClick={handleOpen} title="本棚の分析結果についてAIと対話する">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
        </svg>
      </div>

      {isOpen && (
        <div style={s.overlay} onClick={() => setIsOpen(false)}>
        <div style={s.panel} onClick={e => e.stopPropagation()}>
          <div style={s.header}>
            <span style={s.title}>本棚の分析について対話する</span>
            <button style={s.closeBtn} onClick={() => setIsOpen(false)}>✕</button>
          </div>

          <div ref={messagesRef} style={s.messages}>
            {chatHistory.length === 0 && isLoading && (
              <div style={s.bubbleAi}>考え中...</div>
            )}
            {chatHistory.map((m, i) => {
              if (m.role === "user") {
                return <div key={i} style={s.bubbleUser}>{m.text}</div>;
              }
              const hasCovers = m.relatedIsbns?.length > 0;
              const hasGraph = m.subgraph?.nodes?.length > 1;
              return (
                <div key={i} style={hasCovers || hasGraph ? s.cardAi : s.bubbleAi}>
                  <div>{m.text}</div>

                  {hasCovers && (
                    <div style={s.coverRow}>
                      {m.relatedIsbns.map(isbn => (
                        <img
                          key={isbn}
                          src={`${API}/register/cover/${isbn}`}
                          alt=""
                          style={s.coverImg}
                          onError={e => { e.target.style.display = "none"; }}
                        />
                      ))}
                    </div>
                  )}

                  {hasGraph && (
                    <div style={s.messageGraphBox}>
                      <ForceGraph2D
                        graphData={m.subgraph}
                        width={GRAPH_WIDTH}
                        height={160}
                        nodeId="id"
                        nodeCanvasObject={nodeCanvasObject}
                        nodeCanvasObjectMode={() => "replace"}
                        linkColor={linkColor}
                        linkDirectionalArrowLength={0}
                        linkWidth={1}
                        backgroundColor="#0d1117"
                        cooldownTicks={80}
                        enableZoomPanInteraction={true}
                      />
                    </div>
                  )}
                </div>
              );
            })}
            {chatHistory.length > 0 && isLoading && <div style={s.bubbleAi}>考え中...</div>}
            {error && <div style={s.errorBubble}>{error}</div>}
          </div>

          <div style={s.inputRow}>
            <input
              autoFocus
              style={s.input}
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
              }}
              placeholder="気になったことを聞いてみましょう..."
              disabled={isLoading}
            />
            <button style={s.sendBtn} onClick={handleSend} disabled={isLoading || !chatInput.trim()}>
              送る
            </button>
          </div>
        </div>
        </div>
      )}
    </>
  );
}

const s = {
  fab: {
    position: "fixed", bottom: "30px", left: "30px",
    width: "48px", height: "48px", borderRadius: "50%",
    backgroundColor: "#5b9bd5", color: "#fff",
    display: "flex", justifyContent: "center", alignItems: "center",
    cursor: "pointer",
    boxShadow: "0 4px 16px rgba(91,155,213,0.45)",
    zIndex: 1000,
  },
  overlay: {
    position: "fixed", top: 0, left: 0, width: "100%", height: "100%",
    backgroundColor: "rgba(0,0,0,0.4)",
    display: "flex", justifyContent: "center", alignItems: "center",
    zIndex: 1600,
  },
  panel: {
    width: "500px", maxWidth: "92vw", height: "640px", maxHeight: "80vh",
    backgroundColor: "#fdfcf8", border: "1px solid #ede8da",
    borderRadius: "16px", boxShadow: "0 20px 50px rgba(0,0,0,0.2)",
    display: "flex", flexDirection: "column", overflow: "hidden",
  },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "14px 16px", borderBottom: "1px solid #ede8da",
  },
  title: { fontSize: "13px", fontWeight: "700", color: "#2a1f0e", fontFamily: "serif" },
  closeBtn: {
    width: "22px", height: "22px", borderRadius: "50%",
    border: "none", background: "#ede8da", color: "#4a3728",
    cursor: "pointer", fontSize: "12px", lineHeight: 1,
  },
  messages: {
    flex: 1, overflowY: "auto", padding: "16px",
    display: "flex", flexDirection: "column", gap: "10px",
  },
  bubbleUser: {
    alignSelf: "flex-end", maxWidth: "82%", padding: "8px 12px",
    borderRadius: "14px 14px 2px 14px", backgroundColor: "#5b9bd5",
    color: "#fff", fontSize: "13px", lineHeight: 1.5, whiteSpace: "pre-wrap",
  },
  bubbleAi: {
    alignSelf: "flex-start", maxWidth: "82%", padding: "8px 12px",
    borderRadius: "14px 14px 14px 2px", backgroundColor: "#fff",
    color: "#2a1f0e", fontSize: "13px", lineHeight: 1.5, whiteSpace: "pre-wrap",
    border: "1px solid #ede8da",
  },
  cardAi: {
    alignSelf: "flex-start", maxWidth: "94%", padding: "10px 14px",
    borderRadius: "14px 14px 14px 2px", backgroundColor: "#fff",
    color: "#2a1f0e", fontSize: "13px", lineHeight: 1.5, whiteSpace: "pre-wrap",
    border: "1px solid #ede8da",
    display: "flex", flexDirection: "column", gap: "10px",
  },
  coverRow: {
    display: "flex", gap: "6px", overflowX: "auto", paddingBottom: "2px",
  },
  coverImg: {
    width: "44px", height: "62px", objectFit: "cover", borderRadius: "3px",
    background: "#eee", flexShrink: 0, boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
  },
  messageGraphBox: {
    borderRadius: "10px", overflow: "hidden", border: "1px solid #ede8da",
    width: `${GRAPH_WIDTH}px`, height: "160px", background: "#0d1117",
  },
  errorBubble: {
    alignSelf: "center", fontSize: "12px", color: "#c9506a",
    padding: "8px 12px", borderRadius: "10px", backgroundColor: "#fff0f2",
  },
  inputRow: {
    display: "flex", gap: "8px", padding: "12px 14px",
    borderTop: "1px solid #ede8da",
  },
  input: {
    flex: 1, padding: "8px 10px", borderRadius: "8px",
    border: "1px solid #ddd", fontSize: "13px",
  },
  sendBtn: {
    padding: "8px 14px", backgroundColor: "#5b9bd5", color: "#fff",
    border: "none", borderRadius: "10px", cursor: "pointer",
    fontSize: "13px", fontWeight: "600",
  },
};

export default AnalysisChatPanel;
