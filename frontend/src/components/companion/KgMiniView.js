// 右ペイン「本詳細」のKGミニビジュアライズ（設計書6.1）。
//
// タップした本の「周辺」（関連本と、つながっている理由のノード）を見せる。
// 1冊だけを部分グラフAPIに投げると、つながる相手がいないので点が1つ出るだけになる。
// なので周辺グラフ（ego network、focusDetail.subgraph）を使うこと。
import { useCallback, useLayoutEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { NODE_CFG, LINK_CFG, nodeDisplayLabel } from "../../utils/graphConfig";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";

export default function KgMiniView({ height = 210 }) {
  const {
    focusIsbn, focusDetail, isFocusLoading,
    setFocusIsbn, setHighlightIsbns,
  } = useShelfWorkspace();

  const boxRef = useRef(null);
  const [width, setWidth] = useState(280);

  useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const update = () => setWidth(el.clientWidth || 280);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const data = focusDetail?.subgraph || { nodes: [], links: [] };
  const loading = isFocusLoading;

  // 中心にいる本（タップした本）は大きく橙で描いて、周辺と区別する
  const centerIsbn = focusIsbn;

  const nodeCanvasObject = useCallback((node, ctx, scale) => {
    const cfg = NODE_CFG[node.type] ?? { color: "#aaa", r: 5 };
    const isCenter = node.type === "Book" && node.isbn === centerIsbn;
    const r = (cfg.r ?? 5) + (isCenter ? 3 : 0);

    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = isCenter ? "#ff9d3d" : cfg.color;
    ctx.fill();
    ctx.strokeStyle = isCenter ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.4)";
    ctx.lineWidth = isCenter ? 1.4 : 0.8;
    ctx.stroke();

    // 周辺グラフは点数が少ないので、拡大しなくてもラベルを出す
    const showLabel = scale > 1.4 || data.nodes.length <= 18;
    if (showLabel) {
      const label = nodeDisplayLabel(node);
      if (label) {
        const fs = Math.max(5, 9 / scale);
        ctx.font = `${fs}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = isCenter ? "#ffdca8" : "rgba(255,255,255,0.8)";
        ctx.fillText(label.length > 10 ? label.slice(0, 10) + "…" : label, node.x, node.y + r + 2);
      }
    }
  }, [centerIsbn, data.nodes.length]);

  const linkColor = useCallback(link => (LINK_CFG[link.type]?.color ?? "#888888") + "aa", []);

  // グラフの本をクリックしたら、その本を中心に見直す（周辺をたどれるようにする）
  const handleNodeClick = useCallback((node) => {
    if (node.type === "Book" && node.isbn) setFocusIsbn(node.isbn);
  }, [setFocusIsbn]);

  // グラフの本にカーソルを合わせると、本棚側の同じ本が光る
  const handleNodeHover = useCallback((node) => {
    setHighlightIsbns(node?.type === "Book" && node.isbn ? [node.isbn] : []);
  }, [setHighlightIsbns]);

  const emptyMessage = focusIsbn
    ? "この本はまだどの本ともつながっていません"
    : "本棚で1冊タップすると、この本の周辺が表示されます";

  return (
    <div style={s.wrap}>
      <div style={s.head}>
        <span style={s.title}>この本の周辺</span>
        {(focusDetail?.related?.length ?? 0) > 0 && (
          <span style={s.count}>{focusDetail.related.length}冊とつながる</span>
        )}
      </div>

      <div ref={boxRef} style={{ ...s.box, height }}>
        {loading ? (
          <div style={s.empty}>読み込み中…</div>
        ) : data.nodes.length > 1 ? (
          <ForceGraph2D
            graphData={data}
            width={width}
            height={height}
            nodeId="id"
            nodeCanvasObject={nodeCanvasObject}
            nodeCanvasObjectMode={() => "replace"}
            nodeRelSize={6}
            linkColor={linkColor}
            linkDirectionalArrowLength={0}
            linkWidth={1}
            backgroundColor="#0d1117"
            cooldownTicks={80}
            onNodeClick={handleNodeClick}
            onNodeHover={handleNodeHover}
            enableZoomPanInteraction={true}
          />
        ) : (
          <div style={s.empty}>{emptyMessage}</div>
        )}
      </div>

      {data.nodes.length > 1 && (
        <div style={s.hint}>点をクリックすると、その本を中心に見直せます</div>
      )}
    </div>
  );
}

const s = {
  // 縦に潰れないよう固定。右ペインのスクロールに乗って一緒に流れる。
  wrap: { borderBottom: "1px solid #ede8da", padding: "10px 12px 12px", flexShrink: 0 },
  head: { display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 },
  title: {
    fontSize: 10, fontWeight: 700, color: "#c9a84c",
    letterSpacing: "0.08em", textTransform: "uppercase",
  },
  count: { fontSize: 10, color: "#9a8b76", marginLeft: "auto" },
  box: {
    borderRadius: 10, overflow: "hidden", border: "1px solid #ede8da",
    background: "#0d1117", display: "flex", alignItems: "center", justifyContent: "center",
  },
  empty: { fontSize: 11, color: "#7d8590", textAlign: "center", padding: "0 24px", lineHeight: 1.7 },
  hint: { fontSize: 9.5, color: "#b3a692", marginTop: 6, textAlign: "center" },
};
