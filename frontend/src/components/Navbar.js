import { useState, useContext, useEffect, useRef } from "react";
import { MyHandContext } from "../context/MyHandContext";
import HandPanel from "./HandPanel";
import { Link, useLocation } from "react-router-dom";
import { getParticipantId, setParticipantId, PARTICIPANT_IDS } from "../utils/participant";

export default function Navbar() {
    const { myHand } = useContext(MyHandContext);
    const [isOpen, setIsOpen] = useState(false);
    const [isCompact, setIsCompact] = useState(false);
    const [isPrepOpen, setIsPrepOpen] = useState(false);
    const prepRef = useRef(null);
    const [isMyShelfOpen, setIsMyShelfOpen] = useState(false);
    const myShelfRef = useRef(null);
    const participantId = getParticipantId();

    const location = useLocation();
    const currentPath = location.pathname;

    // 「みんなの本棚」→「P01の本棚」のように、リンク先がそのページ自身だけでなく
    // 配下のページ（/Browse/:id、BrowseLayoutの子ルート）も含む場合がある。
    // 個別の本棚を見ている間も実質「みんなの本棚」の中にいるので、その間は
    // ナビバーから消す（現在地と同じページへのリンクを消すのと同じ扱いにする）。
    const isCurrentSection = (linkPath) =>
        linkPath === currentPath ||
        (linkPath === "/Browse" && currentPath.startsWith("/Browse/"));

    // 中核の画面はここ。知識グラフはいったん非表示にしている
    // （ページ・ルート自体は残したまま、ナビからのみ外す）。
    const links = [
        { path: "/Browse", label: "みんなの本棚", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
        )},
        // 興味・関心質問（フェーズ2c）。配置画面とのアンカリングを避けるため、
        // 「My本棚」ドロップダウンにはまとめず、独立した導線として置く。
        { path: "/InterestSurvey", label: "興味・関心", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
        )},
        // 研究者専用の画面。参加者向けの導線（My本棚・みんなの本棚）とは
        // 性質が違うため、実験準備ドロップダウンにはまとめず独立させる。
        { path: "/ExperimentAdmin", label: "実験管理", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
            </svg>
        )},
        // 新旧UI比較実験の研究者向け管理画面。参加者/観察者は /Uiab から直接
        // アクセスする別導線なので、ここには参加者向けリンクは置かない。
        { path: "/UiabAdmin", label: "新旧UI実験管理", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
            </svg>
        )},
    ];

    // 「My本棚」は本棚そのものと、その構造をスタイル分析した画面の2つを
    // ドロップダウンにまとめる（実験準備と同じ見せ方）。
    const myShelfLinks = [
        { path: "/", label: "本棚", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="7" height="18"/><rect x="9" y="3" width="7" height="18"/><rect x="16" y="8" width="6" height="13"/>
            </svg>
        )},
        { path: "/MyStyleAnalysis", label: "スタイル分析", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 3v18h18"/><path d="M7 15l4-6 3 4 5-8"/>
            </svg>
        )},
    ];
    const isMyShelfSectionActive = myShelfLinks.some((link) => isCurrentSection(link.path));

    // 登録・ギャラリーは便宜的な機能（実験の準備作業）なので、単独のリンクとして
    // 並べず「実験準備」1つにまとめてドロップダウンに収める。
    const prepLinks = [
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
        { path: "/StyleProjection", label: "投影スタイル分析", icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 3v18h18"/><path d="M7 15l4-6 3 4 5-8"/>
            </svg>
        )},
    ];
    const isPrepSectionActive = prepLinks.some((link) => isCurrentSection(link.path));

    useEffect(() => {
        const handleScroll = () => {
            setIsCompact(window.scrollY > 50);
        };

        window.addEventListener("scroll", handleScroll);
        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    // 「実験準備」ドロップダウン：外側クリックとページ遷移で閉じる
    useEffect(() => {
        if (!isPrepOpen) return;
        const handleClickOutside = (e) => {
            if (prepRef.current && !prepRef.current.contains(e.target)) setIsPrepOpen(false);
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [isPrepOpen]);

    // 「My本棚」ドロップダウン：外側クリックとページ遷移で閉じる
    useEffect(() => {
        if (!isMyShelfOpen) return;
        const handleClickOutside = (e) => {
            if (myShelfRef.current && !myShelfRef.current.contains(e.target)) setIsMyShelfOpen(false);
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [isMyShelfOpen]);

    useEffect(() => { setIsPrepOpen(false); setIsMyShelfOpen(false); }, [currentPath]);

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
                    {/* My本棚：本棚そのものと、その構造をスタイル分析した画面をドロップダウンにまとめる */}
                    <div ref={myShelfRef} style={{ position: "relative" }}>
                        <button
                            type="button"
                            onClick={() => setIsMyShelfOpen((v) => !v)}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "6px",
                                padding: "6px 14px",
                                borderRadius: "999px",
                                border: "none",
                                background: isMyShelfSectionActive ? "#c9a84c" : (isMyShelfOpen ? "rgba(0,0,0,0.08)" : "transparent"),
                                color: isMyShelfSectionActive ? "#fff" : "#333",
                                fontSize: "14px",
                                fontWeight: isMyShelfSectionActive ? "700" : "500",
                                cursor: "pointer",
                                transition: "all 0.2s ease",
                            }}
                            onMouseEnter={(e) => {
                                if (!isMyShelfSectionActive && !isMyShelfOpen) e.currentTarget.style.backgroundColor = "rgba(0,0,0,0.05)";
                            }}
                            onMouseLeave={(e) => {
                                if (!isMyShelfSectionActive && !isMyShelfOpen) e.currentTarget.style.backgroundColor = "transparent";
                            }}
                        >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <rect x="2" y="3" width="7" height="18"/><rect x="9" y="3" width="7" height="18"/><rect x="16" y="8" width="6" height="13"/>
                            </svg>
                            My本棚
                            <svg
                                width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
                                style={{ transform: isMyShelfOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}
                            >
                                <polyline points="6 9 12 15 18 9"/>
                            </svg>
                        </button>

                        {isMyShelfOpen && (
                            <div
                                style={{
                                    position: "absolute",
                                    top: "calc(100% + 8px)",
                                    left: 0,
                                    background: "#fff",
                                    borderRadius: "14px",
                                    boxShadow: "0 8px 30px rgba(0,0,0,0.15)",
                                    border: "1px solid rgba(0,0,0,0.06)",
                                    padding: "6px",
                                    minWidth: "150px",
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "2px",
                                    zIndex: 5001,
                                }}
                            >
                                {myShelfLinks.map((link) => {
                                    const isActive = isCurrentSection(link.path);
                                    return (
                                        <Link
                                            key={link.path}
                                            to={link.path}
                                            onClick={() => setIsMyShelfOpen(false)}
                                            style={{
                                                textDecoration: "none",
                                                padding: "8px 12px",
                                                borderRadius: "10px",
                                                color: isActive ? "#fff" : "#333",
                                                background: isActive ? "#c9a84c" : "transparent",
                                                fontSize: "13.5px",
                                                fontWeight: isActive ? "700" : "500",
                                                display: "flex",
                                                alignItems: "center",
                                                gap: "8px",
                                            }}
                                            onMouseEnter={(e) => {
                                                if (!isActive) e.currentTarget.style.backgroundColor = "rgba(0,0,0,0.06)";
                                            }}
                                            onMouseLeave={(e) => {
                                                if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
                                            }}
                                        >
                                            {link.icon} {link.label}
                                        </Link>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {links.map((link) => {
                        const isActive = isCurrentSection(link.path);
                        return (
                            <Link
                                key={link.path}
                                to={link.path}
                                style={{
                                    textDecoration: "none",
                                    padding: "6px 14px",
                                    borderRadius: "999px",
                                    color: isActive ? "#fff" : "#333",
                                    background: isActive ? "#c9a84c" : "transparent",
                                    fontSize: "14px",
                                    fontWeight: isActive ? "700" : "500",
                                    transition: "all 0.2s ease",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "6px",
                                }}
                                onMouseEnter={(e) => {
                                    if (!isActive) e.currentTarget.style.backgroundColor = "rgba(0,0,0,0.05)";
                                }}
                                onMouseLeave={(e) => {
                                    if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
                                }}
                            >
                                {link.icon} {link.label}
                            </Link>
                        );
                    })}

                    {/* 実験準備（登録・ギャラリー）：便宜的な機能なのでまとめて1つの
                        ドロップダウンに収め、中核の画面と並べない。今いる場所が
                        この中にあるときは、ボタン自体も色付けして現在地を示す。 */}
                    <div ref={prepRef} style={{ position: "relative" }}>
                        <button
                            type="button"
                            onClick={() => setIsPrepOpen((v) => !v)}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "6px",
                                padding: "6px 14px",
                                borderRadius: "999px",
                                border: "none",
                                background: isPrepSectionActive ? "#c9a84c" : (isPrepOpen ? "rgba(0,0,0,0.08)" : "transparent"),
                                color: isPrepSectionActive ? "#fff" : "#333",
                                fontSize: "14px",
                                fontWeight: isPrepSectionActive ? "700" : "500",
                                cursor: "pointer",
                                transition: "all 0.2s ease",
                            }}
                            onMouseEnter={(e) => {
                                if (!isPrepSectionActive && !isPrepOpen) e.currentTarget.style.backgroundColor = "rgba(0,0,0,0.05)";
                            }}
                            onMouseLeave={(e) => {
                                if (!isPrepSectionActive && !isPrepOpen) e.currentTarget.style.backgroundColor = "transparent";
                            }}
                        >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M9 2v6.3L4.6 17a2 2 0 0 0 1.8 3h11.2a2 2 0 0 0 1.8-3L15 8.3V2"/>
                                <path d="M9 2h6"/>
                                <path d="M7 14h10"/>
                            </svg>
                            実験準備
                            <svg
                                width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
                                style={{ transform: isPrepOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}
                            >
                                <polyline points="6 9 12 15 18 9"/>
                            </svg>
                        </button>

                        {isPrepOpen && (
                            <div
                                style={{
                                    position: "absolute",
                                    top: "calc(100% + 8px)",
                                    left: 0,
                                    background: "#fff",
                                    borderRadius: "14px",
                                    boxShadow: "0 8px 30px rgba(0,0,0,0.15)",
                                    border: "1px solid rgba(0,0,0,0.06)",
                                    padding: "6px",
                                    minWidth: "150px",
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "2px",
                                    zIndex: 5001,
                                }}
                            >
                                {prepLinks.map((link) => {
                                    const isActive = isCurrentSection(link.path);
                                    return (
                                        <Link
                                            key={link.path}
                                            to={link.path}
                                            onClick={() => setIsPrepOpen(false)}
                                            style={{
                                                textDecoration: "none",
                                                padding: "8px 12px",
                                                borderRadius: "10px",
                                                color: isActive ? "#fff" : "#333",
                                                background: isActive ? "#c9a84c" : "transparent",
                                                fontSize: "13.5px",
                                                fontWeight: isActive ? "700" : "500",
                                                display: "flex",
                                                alignItems: "center",
                                                gap: "8px",
                                            }}
                                            onMouseEnter={(e) => {
                                                if (!isActive) e.currentTarget.style.backgroundColor = "rgba(0,0,0,0.06)";
                                            }}
                                            onMouseLeave={(e) => {
                                                if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
                                            }}
                                        >
                                            {link.icon} {link.label}
                                        </Link>
                                    );
                                })}
                            </div>
                        )}
                    </div>
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
