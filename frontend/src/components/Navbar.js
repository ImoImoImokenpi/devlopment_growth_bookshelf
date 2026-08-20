import { useState, useContext, useEffect } from "react";
import { MyHandContext } from "../context/MyHandContext";
import HandPanel from "./HandPanel";
import { Link, useLocation } from "react-router-dom";
import { getParticipantId, setParticipantId, PARTICIPANT_IDS } from "../utils/participant";

export default function Navbar() {
    const { myHand } = useContext(MyHandContext);
    const [isOpen, setIsOpen] = useState(false);
    const [isCompact, setIsCompact] = useState(false);
    const participantId = getParticipantId();

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
        { path: "/KnowledgeGraph", label: "知識グラフ", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/>
                <line x1="7" y1="11" x2="17" y2="6"/><line x1="7" y1="13" x2="17" y2="18"/>
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

                {/* 右上：被験者の切り替えと手元（カート） */}
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>

                {/* 被験者ID。本棚・知識グラフはこのIDごとに完全に分かれている。 */}
                <label
                    title="被験者ID（本棚と知識グラフはこのIDごとに分かれています）"
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        fontSize: "12px",
                        color: "#666",
                    }}
                >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
                    </svg>
                    <select
                        value={participantId}
                        onChange={(e) => setParticipantId(e.target.value)}
                        style={{
                            border: "1px solid rgba(0,0,0,0.12)",
                            borderRadius: "999px",
                            padding: "4px 8px",
                            fontSize: "12px",
                            background: "rgba(255,255,255,0.8)",
                            color: "#333",
                            cursor: "pointer",
                        }}
                    >
                        {PARTICIPANT_IDS.map((id) => (
                            <option key={id} value={id}>{id}</option>
                        ))}
                    </select>
                </label>

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
