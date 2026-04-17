import { useState, useContext, useEffect } from "react";
import { MyHandContext } from "../context/MyHandContext";
import HandPanel from "./HandPanel";
import { Link, useLocation } from "react-router-dom";
import axios from "axios";

export default function Navbar() {
    const { myHand } = useContext(MyHandContext);
    const [isOpen, setIsOpen] = useState(false);
    const [setHandBooks] = useState([]);
    const [isCompact, setIsCompact] = useState(false);

    const location = useLocation();
    const currentPath = location.pathname;

    const links = [
        { path: "/", label: "本棚", icon: "📚" },
        { path: "/Search", label: "探す", icon: "🔍" },
        // { path: "/KnowledgeGraph", label: "可視化用" },
    ];

    // ★ パネルが開いた瞬間に API を叩く
    useEffect(() => {
        if (isOpen) {
            axios.get("http://localhost:8000/books/myhand")
                .then(res => setHandBooks(res.data))
                .catch(err => console.error(err));
        }
    }, [isOpen]);

    useEffect(() => {
        const handleScroll = () => {
            setIsCompact(window.scrollY > 50);
        };

        window.addEventListener("scroll", handleScroll);
        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    return (
        <>
            {/* 1つの Navbar に統合 */}
        <nav
            style={{
                position: "fixed",
                top: 10,
                left: "50%",
                transform: "translateX(-50%)",
                width: "90%",
                maxWidth: "1000px",
                zIndex: 5000,

                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: isCompact ? "6px 12px" : "10px 16px",
                borderRadius: isCompact ? "12px" : "16px",
                transform: isCompact
                ? "translateX(-50%) scale(0.95)"
                : "translateX(-50%) scale(1)",
                transition: "all 0.3s ease",

                background: "rgba(255,255,255,0.9)", // ← ガラス感
                backdropFilter: "blur(10px)",        // ← ぼかし
                WebkitBackdropFilter: "blur(10px)",

                borderRadius: "18px",
                boxShadow: "0 8px 30px rgba(0,0,0,0.1)",
                border: "1px solid rgba(255,255,255, 0.7)",
            }}
            >
                {/* 左側リンク一覧 */}
                <div style={{ display: "flex", gap: "10px" }}>
                    {links
                        .filter((link) => link.path !== currentPath)
                        .map((link) => (
                            <Link
                                key={link.path}
                                to={link.path}
                                style={{
                                    textDecoration: "none",
                                    padding: "6px 14px",
                                    borderRadius: "999px", // ← ピル型
                                    color: "#333",
                                    fontSize: "14px",
                                    fontWeight: "500",
                                    transition: "all 0.2s ease",
                                }}
                                onMouseEnter={(e) => {
                                    e.target.style.backgroundColor = "rgba(0,0,0,0.05)";
                                }}
                                onMouseLeave={(e) => {
                                    e.target.style.backgroundColor = "transparent";
                                }}
                            >
                                {link.icon} {link.label}
                            </Link>
                        ))}
                </div>

                {/* 右上：手元（カート） */}
                <div
                    style={{
                        position: "relative",
                        cursor: "pointer",
                        fontSize: "14px",
                        padding: "6px 14px",
                        borderRadius: "999px",
                        background: "rgba(0,0,0,0.05)",
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        transition: "0.2s",
                    }}
                    onClick={() => setIsOpen(true)}

                    onMouseEnter={(e) => {
                        e.currentTarget.style.background = "rgba(0,0,0,0.1)";
                    }}
                    onMouseLeave={(e) => {
                        e.currentTarget.style.background = "rgba(0,0,0,0.05)";
                    }}
                >
                    📚 手元
                    <span
                        style={{
                            position: "absolute",
                            top: "-6px",
                            right: "-6px",
                            background: "#ff9900",
                            color: "#fff",
                            borderRadius: "999px",
                            padding: "2px 6px",
                            fontSize: "10px",
                            fontWeight: "bold",
                        }}
                    >
                        {myHand.length}
                    </span>
                </div>
            </nav>

            {/* 右からスライドして出てくるパネル */}
            <HandPanel
                isOpen={isOpen}
                onClose={() => setIsOpen(false)}
            />
        </>
    );
}
