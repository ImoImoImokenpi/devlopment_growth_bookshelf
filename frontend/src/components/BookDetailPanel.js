import { useEffect, useRef, useState, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { NODE_CFG, LINK_CFG, NDC_L1, nodeDisplayLabel, REASON_LINK_TYPE } from "../utils/graphConfig";

const API = "http://localhost:8000";

function BookDetailPanel({ isbn, onClose, onSelectRelated, onRelatedChange }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const fgRef = useRef();

  useEffect(() => {
    if (!isbn) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    fetch(`${API}/knowledge_graph/book/${isbn}`)
      .then(res => {
        if (!res.ok) throw new Error(res.status === 404 ? "本が見つかりません" : "取得に失敗しました");
        return res.json();
      })
      .then(json => { if (!cancelled) { setData(json); setLoading(false); } })
      .catch(err => { if (!cancelled) { setError(err.message); setLoading(false); } });
    return () => { cancelled = true; };
  }, [isbn]);

  // 本棚側でタップ中の本＋関連本をハイライトできるように、関連ISBNを親へ通知する
  useEffect(() => {
    onRelatedChange?.(data?.related?.map(r => r.isbn) || []);
    return () => { onRelatedChange?.([]); };
  }, [data, onRelatedChange]);

  const nodeCanvasObject = useCallback((node, ctx, scale) => {
    const cfg = NODE_CFG[node.type] ?? { color: "#aaa", r: 5 };
    const isCenter = node.id === `book_${isbn}`;
    const r = (cfg.r ?? 5) + (isCenter ? 2 : 0);

    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = isCenter ? "#ff9d3d" : cfg.color;
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
  }, [isbn]);

  const getLinkColor = useCallback(link => {
    const base = LINK_CFG[link.type]?.color ?? "#888888";
    return base + "aa";
  }, []);

  const handleGraphNodeClick = useCallback((node) => {
    if (node.type === "Book" && node.isbn && node.isbn !== isbn) {
      onSelectRelated(node.isbn);
    }
  }, [isbn, onSelectRelated]);

  if (!isbn) return null;

  const book = data?.book;
  const related = data?.related || [];
  const subgraph = data?.subgraph || { nodes: [], links: [] };

  return (
    <div className="book-detail-panel" style={s.panel}>
      <button style={s.closeBtn} onClick={onClose}>✕</button>

      {loading && <div style={s.status}>読み込み中…</div>}
      {error && !loading && <div style={s.statusError}>{error}</div>}

      {!loading && !error && book && (
        <>
          <div style={s.header}>
            {(book.cover || book.spine_image) && (
              <img
                src={book.cover || `${API}/register/cover/${book.isbn}`}
                alt=""
                style={s.cover}
                onError={e => { if (!e.target.dataset.fallback) { e.target.dataset.fallback = "1"; e.target.src = `${API}/register/cover/${book.isbn}`; } }}
              />
            )}
            <div style={{ minWidth: 0 }}>
              <div style={s.title}>{book.title || "（タイトル不明）"}</div>
              {book.authors && <div style={s.meta}>{book.authors}</div>}
              {book.publisher && (
                <div style={s.meta}>
                  {book.publisher}{book.published_year ? `（${book.published_year}）` : ""}
                </div>
              )}
              <div style={s.isbn}>ISBN {book.isbn}</div>
            </div>
          </div>

          {book.description && (
            <p style={s.desc}>
              {book.description.length > 200 ? book.description.slice(0, 200) + "…" : book.description}
            </p>
          )}

          <div style={s.sectionTitle}>知識グラフのつながり</div>
          <div style={s.graphBox}>
            {subgraph.nodes.length > 1 ? (
              <ForceGraph2D
                ref={fgRef}
                graphData={subgraph}
                width={272}
                height={200}
                nodeId="id"
                nodeCanvasObject={nodeCanvasObject}
                nodeCanvasObjectMode={() => "replace"}
                linkColor={getLinkColor}
                linkDirectionalArrowLength={0}
                linkWidth={1}
                backgroundColor="#0d1117"
                cooldownTicks={80}
                onNodeClick={handleGraphNodeClick}
                enableZoomPanInteraction={true}
              />
            ) : (
              <div style={s.graphEmpty}>まだ他の本とのつながりがありません</div>
            )}
          </div>

          <div style={s.sectionTitle}>
            関連する本{related.length > 0 ? `（${related.length}）` : ""}
          </div>
          {related.length === 0 && (
            <div style={s.emptyRelated}>関連する本はまだ見つかりません</div>
          )}
          <div style={s.relatedList}>
            {related.map(r => (
              <div key={r.isbn} style={s.relatedCard} onClick={() => onSelectRelated(r.isbn)}>
                {(r.cover || r.spine_image) && (
                  <img
                    src={r.cover || `${API}/register/cover/${r.isbn}`}
                    alt=""
                    style={s.relatedCover}
                    onError={e => { if (!e.target.dataset.fallback) { e.target.dataset.fallback = "1"; e.target.src = `${API}/register/cover/${r.isbn}`; } }}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={s.relatedTitle}>{r.title}</div>
                  <div style={s.reasonRow}>
                    {r.reasons.map((reason, i) => (
                      <span
                        key={i}
                        style={{ ...s.reasonBadge, borderColor: LINK_CFG[REASON_LINK_TYPE[reason.type]]?.color || "#888" }}
                        title={reason.detail ? `${reason.label}: ${reason.detail}` : reason.label}
                      >
                        {reason.label}{reason.type === "ndc" && reason.detail ? `（${NDC_L1[reason.detail[0]] || reason.detail}）` : reason.detail && reason.type !== "shelf" ? `: ${reason.detail}` : ""}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

const s = {
  panel: {
    position: "fixed",
    top: 70,
    right: 0,
    bottom: 0,
    width: 320,
    maxWidth: "92vw",
    background: "#fdfcf8",
    borderLeft: "1px solid #ede8da",
    boxShadow: "-8px 0 32px rgba(0,0,0,0.12)",
    padding: "18px",
    overflowY: "auto",
    boxSizing: "border-box",
    zIndex: 1500,
  },
  closeBtn: {
    position: "absolute",
    top: 14,
    right: 14,
    width: 26,
    height: 26,
    borderRadius: "50%",
    border: "none",
    background: "#ede8da",
    color: "#4a3728",
    cursor: "pointer",
    fontSize: 12,
  },
  status: { fontSize: 13, color: "#999", textAlign: "center", padding: "40px 10px" },
  statusError: { fontSize: 13, color: "#c9506a", textAlign: "center", padding: "40px 10px" },
  header: { display: "flex", gap: 12, marginTop: 6, marginBottom: 10 },
  cover: {
    width: 64, height: 88, objectFit: "cover", borderRadius: 4,
    background: "#eee", flexShrink: 0, boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
  },
  title: { fontSize: 15, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", lineHeight: 1.4, marginBottom: 6 },
  meta: { fontSize: 12, color: "#6b5c47", marginBottom: 2, lineHeight: 1.4 },
  isbn: { fontSize: 10, color: "#aaa", fontFamily: "monospace", marginTop: 4 },
  desc: { fontSize: 12, color: "#6b5c47", lineHeight: 1.7, marginBottom: 14 },
  sectionTitle: {
    fontSize: 11, fontWeight: 700, color: "#c9a84c",
    textTransform: "uppercase", letterSpacing: "0.06em",
    marginTop: 16, marginBottom: 8,
  },
  graphBox: {
    borderRadius: 10, overflow: "hidden", border: "1px solid #ede8da",
    width: 272, height: 200, background: "#0d1117",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  graphEmpty: { fontSize: 11, color: "#666", textAlign: "center", padding: "0 20px" },
  emptyRelated: { fontSize: 12, color: "#bbb", padding: "6px 0" },
  relatedList: { display: "flex", flexDirection: "column", gap: 8 },
  relatedCard: {
    display: "flex", gap: 10, padding: 8, borderRadius: 8,
    border: "1px solid #ede8da", cursor: "pointer", background: "#fff",
  },
  relatedCover: {
    width: 34, height: 48, objectFit: "cover", borderRadius: 3,
    background: "#eee", flexShrink: 0,
  },
  relatedTitle: { fontSize: 12.5, fontWeight: 600, color: "#2a1f0e", marginBottom: 4, lineHeight: 1.4 },
  reasonRow: { display: "flex", flexWrap: "wrap", gap: 4 },
  reasonBadge: {
    fontSize: 10, padding: "2px 6px", borderRadius: 8,
    border: "1px solid #888", color: "#6b5c47", lineHeight: 1.5,
    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 180,
  },
};

export default BookDetailPanel;
