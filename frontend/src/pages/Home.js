import { useState, useEffect } from "react";
import Layout from "../components/Layout"; 
import axios from "axios";
import GraphView from "../components/Graph";

function Home() {
    const [graph, setGraph] = useState({ nodes: [], links: [] });
    
    const loadGraph = async () => {
        const res = await axios.get("http://localhost:8000/get_graph");
        setGraph(res.data);
    };

    useEffect(() => {
        loadGraph();
    }, []);

    return (
        <Layout>
        <div>
            <h1>本棚空間</h1>
            <GraphView graphData={graph} />
        </div>
        </Layout>
    );
}

export default Home;
