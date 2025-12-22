import { useEffect, useState } from "react";
import Layout from "../components/Layout";
import axios from "axios";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

// --- 定数・ユーティリティ ---
const WIDTH = 1200;
const HEIGHT = 800;
const PAD = 100;
const normalize = (v, min, max) =>
  max === min ? 0.5 : (v - min) / (max - min);

// 1. グラフ描画専用コンポーネント
const GraphCanvas = ({ nodes, edges, pos }) => (
  <div
    style={{
      border: "1px solid #ddd",
      borderRadius: "12px",
      overflow: "hidden",
      background: "#fafafa",
    }}
  >
    <TransformWrapper initialScale={0.8} minScale={0.2} maxScale={4}>
      <TransformComponent wrapperStyle={{ width: "100%", height: "60vh" }}>
        <svg width={WIDTH} height={HEIGHT}>
          {/* エッジ（線） */}
          {edges.map((e, i) => {
            const s = pos[e.source],
              t = pos[e.target];
            if (!s || !t) return null;
            const isConcept = e.type === "same_concept";
            return (
              <line
                key={i}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={isConcept ? "#ff9800" : "#88f"}
                strokeDasharray={isConcept ? "4 2" : "none"}
                strokeWidth={isConcept ? 2 : 1.2}
                opacity={0.6}
              />
            );
          })}
          {/* ノード（円と文字） */}
          {nodes.map((n) => (
            <g key={n.id}>
              <circle
                cx={pos[n.id].x}
                cy={pos[n.id].y}
                r={14}
                fill="#fff"
                stroke="#333"
                strokeWidth={1.5}
              />
              <text
                x={pos[n.id].x}
                y={pos[n.id].y - 20}
                fontSize="12"
                fontWeight="bold"
                textAnchor="middle"
                fill="#333"
              >
                {n.label}
              </text>
            </g>
          ))}
        </svg>
      </TransformComponent>
    </TransformWrapper>
  </div>
);

// 2. レポート一行分専用コンポーネント
const BookReport = ({ node, edges, allNodes }) => {
  const relatedEdges = edges.filter(
    (e) => e.source === node.id || e.target === node.id
  );

  // --- 重複排除のロジック ---
  const summary = {};
  relatedEdges.forEach((e) => {
    const targetId = e.source === node.id ? e.target : e.source;
    if (!summary[targetId]) {
      summary[targetId] = { labels: new Set(), types: new Set() };
    }
    if (e.label) summary[targetId].labels.add(e.label);
    summary[targetId].types.add(e.type);
  });

  return (
    <div
      style={{
        marginBottom: "20px",
        borderBottom: "1px solid #f0f0f0",
        paddingBottom: "10px",
      }}
    >
      <strong style={{ fontSize: "1.1rem" }}>『{node.label}』</strong>
      <p style={{ fontSize: "0.9rem", color: "#666", marginBottom: "5px" }}>
        ジャンル: {node.concepts?.join(" / ") || "なし"}
      </p>

      <ul
        style={{ fontSize: "0.85rem", listStyle: "none", paddingLeft: "10px" }}
      >
        {Object.entries(summary).map(([targetId, info]) => {
          const target = allNodes.find((n) => n.id === targetId);
          if (!target) return null;

          const hasConcept = info.types.has("same_concept");
          const labels = Array.from(info.labels);

          return (
            <li key={targetId} style={{ marginBottom: "4px" }}>
              <span
                style={{
                  color: hasConcept ? "#ff9800" : "#44f",
                  fontWeight: "bold",
                }}
              >
                {hasConcept
                  ? `● 共通概念 [${labels.join(", ")}]`
                  : "○ 内容が類似"}
              </span>
              {` : 『${target.label}』`}
            </li>
          );
        })}
      </ul>
    </div>
  );
};

// 3. メイン画面
export default function KnowledgeGraphView() {
  const [data, setData] = useState({ nodes: [], edges: [] });

  useEffect(() => {
    axios
      .get("http://localhost:8000/knowledge-graph/")
      .then((res) => setData(res.data))
      .catch(() => alert("取得失敗"));
  }, []);

  if (data.nodes.length === 0) return <p>📭 データがありません</p>;

  // 座標計算（1回だけ実行）
  const xs = data.nodes.map((n) => n.x),
    ys = data.nodes.map((n) => n.y);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs),
    minY = Math.min(...ys),
    maxY = Math.max(...ys);

  const pos = Object.fromEntries(
    data.nodes.map((n) => [
      n.id,
      {
        x: PAD + normalize(n.x, minX, maxX) * (WIDTH - PAD * 2),
        y: PAD + normalize(n.y, minY, maxY) * (HEIGHT - PAD * 2),
      },
    ])
  );

  return (
    <Layout>
      <div style={{ padding: "20px" }}>
        <h2>📚 知識グラフ</h2>

        {/* コンポーネント化してスッキリ */}
        <GraphCanvas nodes={data.nodes} edges={data.edges} pos={pos} />

        <div
          style={{
            marginTop: "30px",
            padding: "20px",
            background: "#fff",
            borderRadius: "12px",
            border: "1px solid #eee",
          }}
        >
          <h3>📝 書籍の関連性レポート</h3>
          {data.nodes.map((node) => (
            <BookReport
              key={node.id}
              node={node}
              edges={data.edges}
              allNodes={data.nodes}
            />
          ))}
        </div>
      </div>
    </Layout>
  );
}
