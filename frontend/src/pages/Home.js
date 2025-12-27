import { useContext } from "react";
import Layout from "../components/Layout";
import ShelfView from "../components/ShelfView";
import { MyHandContext } from "../context/MyHandContext";

function Home() {
  return (
    <Layout>
      <div>
        <h1>本棚空間</h1>
        <ShelfView />
      </div>
    </Layout>
  );
}

export default Home;
