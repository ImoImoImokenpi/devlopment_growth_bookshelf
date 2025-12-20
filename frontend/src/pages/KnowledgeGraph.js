import { useEffect, useState } from "react";
import axios from "axios";

const WIDTH = 900;
const HEIGHT = 600;
const PAD = 60;

const normalize = (v, min, max) =>
  max === min ? 0.5 : (v - min) / (max - min);

export default function KnowledgeGraphView() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);

  useEffect(() => {
    axios
      .get("http://localhost:8000/knowledge-graph")
      .then((res) => {
        setNodes(res.data.nodes);
        setEdges(res.data.edges);
      })
      .catch(() => alert("取得失敗"));
  }, []);

  if (nodes.length === 0) return <p>データなし</p>;

  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const pos = Object.fromEntries(
    nodes.map((n) => [
      n.id,
      {
        x: PAD + normalize(n.x, minX, maxX) * (WIDTH - PAD * 2),
        y: PAD + normalize(n.y, minY, maxY) * (HEIGHT - PAD * 2),
      },
    ])
  );

  return (
    <div>
      <h2>📚 知識グラフ</h2>

      <svg
        width={WIDTH}
        height={HEIGHT}
        style={{
          border: "1px solid #ddd",
          borderRadius: "12px",
          background: "#fafafa",
        }}
      >
        {/* エッジ */}
        {edges.map((e, i) => {
          const s = pos[e.source];
          const t = pos[e.target];
          if (!s || !t) return null;

          return (
            <line
              key={i}
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              stroke="#88f"
              strokeWidth={1 + e.weight * 3}
              opacity={0.7}
            />
          );
        })}

        {/* ノード */}
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
              y={pos[n.id].y - 18}
              fontSize="11"
              textAnchor="middle"
            >
              {n.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
