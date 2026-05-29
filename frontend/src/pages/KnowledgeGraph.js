import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import axios from "axios";
import ForceGraph2D from "react-force-graph-2d";

const API = "http://localhost:8000";

const NDC_L1 = {
  "0": "総記", "1": "哲学", "2": "歴史・地理", "3": "社会科学",
  "4": "自然科学", "5": "技術", "6": "産業", "7": "芸術", "8": "言語", "9": "文学",
};

const NODE_CFG = {
  Book:      { color: "#5b9bd5", r: 7,    ja: "本" },
  Author:    { color: "#c9a84c", r: 5,    ja: "著者" },
  Publisher: { color: "#6aab8c", r: 5,    ja: "出版社" },
  NDC:       { color: "#9d78c4", r: null, ja: "NDC" },
  Concept:   { color: "#e07070", r: 6,    ja: "コンセプト" },
  Meaning:   { color: "#e09040", r: 4,    ja: "意味" },
};

const LINK_CFG = {
  WRITTEN_BY:    { color: "#c9a84c", ja: "著者" },
  PUBLISHED_BY:  { color: "#6aab8c", ja: "出版社" },
  CLASSIFIED_AS: { color: "#9d78c4", ja: "分類" },
  BROADER:       { color: "#c8a0e8", ja: "上位NDC" },
  SHELF_NEXT:    { color: "#5b9bd5", ja: "本棚で隣接" },
  CONCEPT:       { color: "#e07070", ja: "コンセプト" },
  HAS_MEANING:   { color: "#e09040", ja: "意味" },
};

const ndcR = (level) => ([13, 9, 7, 5][level - 1] ?? 5);

const nodeDisplayLabel = (n) =>
  n.title || n.name || n.code || n.text || "";

export default function KnowledgeGraph() {
  const [rawData, setRawData]     = useState({ nodes: [], links: [] });
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(false);
  const [selected, setSelected]   = useState(null);
  const [hoverId, setHoverId]     = useState(null);
  const [hlNodes, setHlNodes]     = useState(new Set());
  const [hlLinks, setHlLinks]     = useState(new Set());
  const [showTypes, setShowTypes] = useState({
    Book: true, Author: true, Publisher: true,
    NDC: true, Concept: true, Meaning: false,
  });
  const [filterOpen, setFilterOpen] = useState(false);
  const [dims, setDims]           = useState({ w: window.innerWidth, h: window.innerHeight });
  const fgRef = useRef();

  useEffect(() => {
    const onResize = () => setDims({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    axios.get(`${API}/knowledge_graph/`)
      .then(res => { setRawData(res.data); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, []);

  const graphData = useMemo(() => {
    const activeIds = new Set(
      rawData.nodes.filter(n => showTypes[n.type]).map(n => n.id)
    );
    return {
      nodes: rawData.nodes.filter(n => showTypes[n.type]),
      links: rawData.links.filter(l => {
        const s = typeof l.source === "object" ? l.source.id : l.source;
        const t = typeof l.target === "object" ? l.target.id : l.target;
        return activeIds.has(s) && activeIds.has(t);
      }),
    };
  }, [rawData, showTypes]);

  const setHighlight = useCallback((node) => {
    if (!node) { setHlNodes(new Set()); setHlLinks(new Set()); return; }
    const hn = new Set([node.id]);
    const hl = new Set();
    graphData.links.forEach(link => {
      const s = typeof link.source === "object" ? link.source.id : link.source;
      const t = typeof link.target === "object" ? link.target.id : link.target;
      if (s === node.id || t === node.id) { hn.add(s); hn.add(t); hl.add(link); }
    });
    setHlNodes(hn);
    setHlLinks(hl);
  }, [graphData.links]);

  const handleNodeClick = useCallback(node => {
    setSelected(node);
    setHighlight(node);
    fgRef.current?.centerAt(node.x, node.y, 600);
    fgRef.current?.zoom(3, 600);
  }, [setHighlight]);

  const handleNodeHover = useCallback(node => {
    setHoverId(node?.id ?? null);
  }, []);

  const handleBgClick = useCallback(() => {
    setSelected(null);
    setHighlight(null);
  }, [setHighlight]);

  const nodeCanvasObject = useCallback((node, ctx, scale) => {
    const cfg = NODE_CFG[node.type] ?? { color: "#aaa", r: 5 };
    const r = node.type === "NDC" ? ndcR(node.level) : cfg.r;
    const dimmed = hlNodes.size > 0 && !hlNodes.has(node.id);

    ctx.save();
    ctx.globalAlpha = dimmed ? 0.12 : 1;

    if (!dimmed && (node.id === hoverId || hlNodes.has(node.id))) {
      ctx.shadowColor = cfg.color;
      ctx.shadowBlur  = 14;
    }

    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = cfg.color;
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.35)";
    ctx.lineWidth   = 0.8;
    ctx.stroke();
    ctx.shadowBlur  = 0;

    const label = nodeDisplayLabel(node);
    if (label) {
      const show = node.type === "Book"
        ? scale > 1.2
        : node.type === "NDC"
        ? scale > 2.5
        : scale > 2;
      if (show) {
        const fs = Math.max(5, 10 / scale);
        ctx.font         = `${fs}px sans-serif`;
        ctx.textAlign    = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle    = "rgba(255,255,255,0.88)";
        const t = label.length > 12 ? label.slice(0, 12) + "…" : label;
        ctx.fillText(t, node.x, node.y + r + 2);
      }
    }
    ctx.restore();
  }, [hlNodes, hoverId]);

  const nodePointerAreaPaint = useCallback((node, color, ctx) => {
    const cfg = NODE_CFG[node.type] ?? { r: 5 };
    const r = node.type === "NDC" ? ndcR(node.level) : cfg.r;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
  }, []);

  const getLinkColor = useCallback(link => {
    const base = LINK_CFG[link.type]?.color ?? "#888888";
    if (hlLinks.size > 0 && !hlLinks.has(link)) return base + "18";
    if (hlLinks.size > 0 && hlLinks.has(link))  return base + "dd";
    return base + "55";
  }, [hlLinks]);

  const getNodeLabel = useCallback(node => {
    const lbl = nodeDisplayLabel(node);
    const type = NODE_CFG[node.type]?.ja ?? node.type;
    return `[${type}] ${lbl}`;
  }, []);

  const panelW = selected ? 300 : 0;
  const canvasW = dims.w - panelW;

  return (
    <div style={s.root}>
      {/* Graph Canvas */}
      {!loading && !error && (
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData}
          width={canvasW}
          height={dims.h}
          nodeId="id"
          nodeLabel={getNodeLabel}
          nodeCanvasObject={nodeCanvasObject}
          nodeCanvasObjectMode={() => "replace"}
          nodePointerAreaPaint={nodePointerAreaPaint}
          linkColor={getLinkColor}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkWidth={1.2}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          onBackgroundClick={handleBgClick}
          backgroundColor="#0d1117"
          cooldownTicks={120}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
        />
      )}

      {/* Loading */}
      {loading && (
        <div style={s.center}>
          <div style={s.spinner} />
          <div style={s.loadingText}>グラフを読み込んでいます…</div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={s.center}>
          <div style={s.errorText}>Neo4j に接続できませんでした</div>
          <div style={s.errorSub}>バックエンドと Neo4j が起動しているか確認してください</div>
        </div>
      )}

      {/* ── Overlays ─────────────────────────────────── */}

      {/* Filter button */}
      <button style={s.filterBtn} onClick={() => setFilterOpen(o => !o)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="4" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="16" y2="12"/>
          <line x1="11" y1="18" x2="13" y2="18"/>
        </svg>
        フィルター
      </button>

      {/* Filter panel */}
      {filterOpen && (
        <div style={s.filterPanel}>
          <div style={s.panelHeading}>ノードタイプ</div>
          {Object.entries(NODE_CFG).map(([type, cfg]) => (
            <label key={type} style={s.filterRow}>
              <span style={{ ...s.dot, background: cfg.color }} />
              <input
                type="checkbox"
                checked={!!showTypes[type]}
                onChange={() => setShowTypes(p => ({ ...p, [type]: !p[type] }))}
                style={{ accentColor: cfg.color, marginRight: 6 }}
              />
              <span style={s.filterLabel}>{cfg.ja}</span>
            </label>
          ))}
          <div style={{ ...s.panelHeading, marginTop: 12 }}>エッジタイプ</div>
          {Object.entries(LINK_CFG).map(([type, cfg]) => (
            <div key={type} style={s.linkRow}>
              <span style={{ ...s.linkLine, background: cfg.color }} />
              <span style={s.filterLabel}>{cfg.ja}</span>
            </div>
          ))}
        </div>
      )}

      {/* Stats + Legend */}
      {!loading && !error && (
        <div style={s.legend}>
          <div style={s.statsText}>
            {graphData.nodes.length} nodes · {graphData.links.length} edges
          </div>
          <div style={s.legendRow}>
            {Object.entries(NODE_CFG).filter(([t]) => showTypes[t]).map(([type, cfg]) => (
              <span key={type} style={s.legendItem}>
                <span style={{ ...s.dot, background: cfg.color, display: "inline-block" }} />
                {cfg.ja}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Node detail panel */}
      <div style={{ ...s.detail, transform: selected ? "translateX(0)" : "translateX(100%)" }}>
        {selected && (
          <>
            <button style={s.closeBtn} onClick={() => { setSelected(null); setHighlight(null); }}>✕</button>
            <NodeDetail node={selected} />
          </>
        )}
      </div>
    </div>
  );
}

// ── Detail panel content ──────────────────────────────────

function NodeDetail({ node }) {
  const type = NODE_CFG[node.type]?.ja ?? node.type;

  if (node.type === "Book") {
    const hasCover = node.cover || node.spine_image;
    return (
      <div>
        <div style={s.detailChip}>{type}</div>
        {hasCover && (
          <img
            src={node.cover || `${API}/register/cover/${node.isbn}`}
            alt=""
            style={s.detailCover}
            onError={e => { if (!e.target.dataset.fallback) { e.target.dataset.fallback = "1"; e.target.src = `${API}/register/cover/${node.isbn}`; }}}
          />
        )}
        <div style={s.detailTitle}>{node.title || "（タイトル不明）"}</div>
        {node.authors  && <div style={s.detailMeta}>{node.authors}</div>}
        {node.publisher && (
          <div style={s.detailMeta}>
            {node.publisher}{node.published_year ? ` (${node.published_year})` : ""}
          </div>
        )}
        {node.isbn && <div style={s.detailIsbn}>ISBN {node.isbn}</div>}
        {node.description && (
          <p style={s.detailDesc}>
            {node.description.length > 220
              ? node.description.slice(0, 220) + "…"
              : node.description}
          </p>
        )}
      </div>
    );
  }

  if (node.type === "Author") return (
    <div>
      <div style={s.detailChip}>{type}</div>
      <div style={s.detailTitle}>{node.name}</div>
    </div>
  );

  if (node.type === "Publisher") return (
    <div>
      <div style={s.detailChip}>{type}</div>
      <div style={s.detailTitle}>{node.name}</div>
    </div>
  );

  if (node.type === "NDC") {
    const catName = NDC_L1[node.code?.[0]] ?? "";
    return (
      <div>
        <div style={s.detailChip}>{type} Level {node.level}</div>
        <div style={s.detailTitle}>{node.code}</div>
        {catName && <div style={s.detailMeta}>{catName}</div>}
      </div>
    );
  }

  if (node.type === "Concept") return (
    <div>
      <div style={s.detailChip}>{type}</div>
      <div style={s.detailTitle}>{node.text}</div>
    </div>
  );

  return (
    <div>
      <div style={s.detailChip}>{type}</div>
      <div style={s.detailTitle}>{nodeDisplayLabel(node)}</div>
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────

const s = {
  root: {
    position: "fixed",
    inset: 0,
    background: "#0d1117",
    display: "flex",
    fontFamily: "sans-serif",
  },
  center: {
    position: "absolute",
    inset: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
  },
  spinner: {
    width: 36,
    height: 36,
    border: "3px solid #ffffff22",
    borderTop: "3px solid #c9a84c",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  loadingText: { color: "#aaa", fontSize: 14 },
  errorText:   { color: "#e07070", fontSize: 16, fontWeight: 700 },
  errorSub:    { color: "#888", fontSize: 13 },

  // Filter button (top-left)
  filterBtn: {
    position: "absolute",
    top: 72,
    left: 16,
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 14px",
    background: "rgba(255,255,255,0.07)",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 10,
    color: "#ddd",
    fontSize: 13,
    cursor: "pointer",
    backdropFilter: "blur(8px)",
    zIndex: 100,
  },
  filterPanel: {
    position: "absolute",
    top: 110,
    left: 16,
    background: "rgba(20,22,30,0.94)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 14,
    padding: "14px 18px",
    backdropFilter: "blur(12px)",
    zIndex: 100,
    minWidth: 160,
  },
  panelHeading: {
    fontSize: 10,
    fontWeight: 700,
    color: "#888",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    marginBottom: 8,
  },
  filterRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginBottom: 6,
    cursor: "pointer",
  },
  filterLabel: { fontSize: 13, color: "#ccc" },
  linkRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 6,
  },
  linkLine: {
    display: "inline-block",
    width: 22,
    height: 2,
    borderRadius: 1,
    flexShrink: 0,
  },

  // Legend (bottom-left)
  legend: {
    position: "absolute",
    bottom: 20,
    left: 16,
    background: "rgba(20,22,30,0.85)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 12,
    padding: "10px 14px",
    backdropFilter: "blur(8px)",
    zIndex: 100,
  },
  statsText: { fontSize: 11, color: "#666", marginBottom: 8 },
  legendRow: { display: "flex", flexWrap: "wrap", gap: "8px 14px" },
  legendItem: { display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#bbb" },
  dot: { width: 9, height: 9, borderRadius: "50%", flexShrink: 0 },

  // Detail panel (right)
  detail: {
    position: "absolute",
    top: 0,
    right: 0,
    width: 300,
    height: "100%",
    background: "rgba(18,20,26,0.97)",
    borderLeft: "1px solid rgba(255,255,255,0.1)",
    backdropFilter: "blur(16px)",
    overflowY: "auto",
    padding: "64px 22px 24px",
    transition: "transform 0.3s ease",
    zIndex: 200,
    boxSizing: "border-box",
  },
  closeBtn: {
    position: "absolute",
    top: 16,
    right: 16,
    background: "rgba(255,255,255,0.07)",
    border: "none",
    color: "#aaa",
    width: 32,
    height: 32,
    borderRadius: "50%",
    cursor: "pointer",
    fontSize: 14,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  detailChip: {
    display: "inline-block",
    padding: "3px 10px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.07)",
    color: "#aaa",
    fontSize: 11,
    marginBottom: 14,
  },
  detailCover: {
    width: "100%",
    maxHeight: 180,
    objectFit: "contain",
    borderRadius: 8,
    marginBottom: 14,
    background: "#1a1d24",
  },
  detailTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "#e8e0d0",
    fontFamily: "serif",
    lineHeight: 1.5,
    marginBottom: 8,
  },
  detailMeta: {
    fontSize: 12,
    color: "#888",
    marginBottom: 4,
    lineHeight: 1.5,
  },
  detailIsbn: {
    fontSize: 11,
    color: "#555",
    fontFamily: "monospace",
    marginTop: 6,
    marginBottom: 10,
  },
  detailDesc: {
    fontSize: 12,
    color: "#777",
    lineHeight: 1.7,
    marginTop: 12,
    borderTop: "1px solid rgba(255,255,255,0.06)",
    paddingTop: 12,
  },
};

// CSS animation injection
const styleEl = document.createElement("style");
styleEl.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(styleEl);
