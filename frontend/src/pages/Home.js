import { useContext } from "react";
import Layout from "../components/Layout";
import GraphView from "../components/Graph";
import { MyHandContext } from "../context/MyHandContext";

function Home() {
    return (
        <Layout>
            <div>
                <h1>本棚空間</h1>
                <GraphView />
            </div>
        </Layout>
    );
}

export default Home;
