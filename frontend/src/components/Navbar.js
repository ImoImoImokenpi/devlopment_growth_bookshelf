import { useState, useContext, useEffect } from "react";
import { MyHandContext } from "../context/MyHandContext";
import HandPanel from "./HandPanel";
import { Link, useLocation } from "react-router-dom";

export default function Navbar() {
    const { myHand } = useContext(MyHandContext);
    const [isOpen, setIsOpen] = useState(false);
    const [isCompact, setIsCompact] = useState(false);

    const location = useLocation();
    const currentPath = location.pathname;

    const links = [
        { path: "/", label: "My本棚", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="7" height="18"/><rect x="9" y="3" width="7" height="18"/><rect x="16" y="8" width="6" height="13"/>
            </svg>
        )},
        { path: "/Gallery", label: "ギャラリー", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
            </svg>
        )},
        { path: "/Register", label: "登録", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 5v14M5 12h14"/>
            </svg>
        )},
    ];

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
                                    borderRadius: "999px",
                                    color: "#333",
                                    fontSize: "14px",
                                    fontWeight: "500",
                                    transition: "all 0.2s ease",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "6px",
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
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M18 11V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2"/>
                      <path d="M14 10V4a2 2 0 0 0-2-2 2 2 0 0 0-2 2v2"/>
                      <path d="M10 10.5V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2v8"/>
                      <path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>
                    </svg>
                    手元
                    {myHand.length > 0 && (
                        <span style={{
                            background: "#c9a84c",
                            color: "#fff",
                            borderRadius: "999px",
                            padding: "1px 8px",
                            fontSize: "11px",
                            fontWeight: "700",
                            lineHeight: "1.8",
                        }}>
                            {myHand.length}
                        </span>
                    )}
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
