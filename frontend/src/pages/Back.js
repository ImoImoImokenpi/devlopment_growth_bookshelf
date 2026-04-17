import { useContext } from "react";
import SpineShelfView from "../components/SpineShelfView";
import { MyHandContext } from "../context/MyHandContext";

function Back() {
    return (
        <div>
            <h1>背表紙本棚空間</h1>
            <SpineShelfView />
        </div>
    );
}

export default Back;
