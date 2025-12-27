import { useEffect, useRef } from "react";
import axios from "axios";
import { Network } from "vis-network/standalone";

function KnowledgeGraph() {
  const containerRef = useRef(null);
  const networkRef = useRef(null);

  useEffect(() => {
    const fetchGraph = async () => {
      const res = await axios.get("http://localhost:8000/knowledge_graph/");
      const { nodes, links } = res.data;

      const visNodes = nodes.map((n) => ({
        id: n.id,
        label: n.title,
        group: n.type,
      }));

      const visEdges = links.map((l) => ({
        from: l.source,
        to: l.target,
        label: l.type,
        arrows: "to",
      }));

      const data = {
        nodes: visNodes,
        edges: visEdges,
      };

      const options = {
        physics: {
          enabled: true,
          stabilization: true,
          barnesHut: {
            gravitationalConstant: -3000,
            springLength: 120,
          },
        },
        nodes: {
          shape: "dot",
          size: 16,
          font: { size: 14 },
        },
        groups: {
          Book: { color: "#4a90e2" },
          Concept: { color: "#f5a623" },
        },
      };

      networkRef.current = new Network(containerRef.current, data, options);
    };

    fetchGraph();
  }, []);

  return (
    <div>
      <h2>知識グラフ</h2>
      <div
        ref={containerRef}
        style={{ width: "100%", height: "700px", border: "1px solid #ddd" }}
      />
    </div>
  );
}

export default KnowledgeGraph;
