import React from "react";
import Navbar from "./Navbar";

const Layout = ({ children }) => {
    return (
        <div style={{ position: "relative", height: "130vh", overflow: "hidden" }}>
        <Navbar />

            {/* メインコンテンツ */}
            <div style={{ width: "100%", height: "100%", boxSizing: "border-box" }}>
                {children}
            </div>
        </div>
    );
};

export default Layout;