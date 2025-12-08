import React, { useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

const GraphView = () => {
    const [graphData, setGraphData] = useState({
        nodes: [
        { id: "1", name: "スタート" }
        ],
        links: []
    });

    const addNode = () => {
        const newId = (graphData.nodes.length + 1).toString();
        const newNode = { id: newId, name: `Book ${newId}` };

        setGraphData({
        nodes: [...graphData.nodes, newNode],
        links: [
            ...graphData.links,
            { source: "1", target: newId } // 最初は仮で全部 root につなぐ
        ]
        });
    };

    return (
        <div>
        <button onClick={addNode}>ノード追加</button>
        <ForceGraph2D
            graphData={graphData}
            nodeLabel="name"
            width={800}
            height={600}
        />
        </div>
    );
};

export default GraphView;
