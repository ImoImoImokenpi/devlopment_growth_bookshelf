// アプリ共通の上部ナビバー。メインの3画面を行き来する。
//   育つ本棚   (/)          : 自分の本棚（背表紙を自由に並べ替えられる）
//   ギャラリー (/Gallery)   : 登録済みの本をすべて表示。ここから本を「手元」に追加する
//   本を探す   (/Search)    : 書名・著者・ISBNで本を探して、手元に加える
// 右端の「手元の本」から、手元に集めた本を育つ本棚へ加える(HandPanel)。
import { useContext, useState } from "react";
import { NavLink } from "react-router-dom";
import { MyHandContext } from "../context/MyHandContext";
import HandPanel from "./HandPanel";

export const NAV_H = 56;

const LINKS = [
  {
    to: "/", label: "育つ本棚", end: true,
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="4" height="18" /><rect x="8" y="5" width="4" height="16" /><path d="M14 6.5l3.8-1 3.7 14.5-3.8 1z" />
      </svg>
    ),
  },
  {
    to: "/Gallery", label: "ギャラリー",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
      </svg>
    ),
  },
  {
    to: "/Search", label: "本を探す",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
      </svg>
    ),
  },
];

export default function AppNavbar() {
  const { myHand } = useContext(MyHandContext);
  const [isHandOpen, setIsHandOpen] = useState(false);

  return (
    <>
      <header style={s.bar}>
        <div style={s.brand}>
          <span style={s.brandMark}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 21V11" /><path d="M12 11c0-4 3-6 7-6 0 4-3 6-7 6z" /><path d="M12 14c0-3-2.5-5-6-5 0 3 2.5 5 6 5z" />
            </svg>
          </span>
          育つ本棚
        </div>
        <nav style={s.links}>
          {LINKS.map(link => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              style={({ isActive }) => ({ ...s.link, ...(isActive ? s.linkActive : {}) })}
            >
              {link.icon}
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div style={s.right}>
        <button style={s.handBtn} onClick={() => setIsHandOpen(true)} title="手元の本を本棚に加える">
          手元の本
          <span style={{ ...s.badge, ...(myHand.length === 0 ? s.badgeEmpty : {}) }}>{myHand.length}</span>
        </button>
        </div>
      </header>
      <HandPanel isOpen={isHandOpen} onClose={() => setIsHandOpen(false)} />
    </>
  );
}

const s = {
  bar: {
    position: "sticky", top: 0, zIndex: 1000,
    height: NAV_H, boxSizing: "border-box",
    display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: 16,
    padding: "0 32px",
    background: "rgba(253,252,248,0.95)",
    backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)",
    borderBottom: "1px solid #ede8da",
  },
  brand: {
    justifySelf: "start",
    display: "inline-flex", alignItems: "center", gap: 8,
    fontFamily: "serif", fontSize: 17, fontWeight: 700,
    color: "#2a1f0e", letterSpacing: "0.06em", whiteSpace: "nowrap",
  },
  brandMark: {
    width: 28, height: 28, borderRadius: 8, background: "#c9a84c", color: "#fff",
    display: "inline-flex", alignItems: "center", justifyContent: "center",
  },
  // 3画面の切り替えは中央にまとめた1つのスイッチにする
  links: {
    display: "flex", alignItems: "center", gap: 2, padding: 4,
    borderRadius: 999, background: "#f2ecdf",
  },
  right: { justifySelf: "end", display: "flex", alignItems: "center" },
  link: {
    display: "inline-flex", alignItems: "center", gap: 6,
    padding: "7px 18px", borderRadius: 999,
    color: "#8a7960", fontSize: 13, fontWeight: 600,
    textDecoration: "none", whiteSpace: "nowrap",
    transition: "background 0.15s, color 0.15s",
  },
  linkActive: { background: "#fff", color: "#2a1f0e", boxShadow: "0 1px 4px rgba(80,60,20,0.15)" },
  handBtn: {
    display: "inline-flex", alignItems: "center", gap: 8,
    padding: "6px 8px 6px 14px", borderRadius: 999,
    border: "1px solid #e0d8c0", background: "#fff",
    color: "#6b5a3e", fontSize: 12.5, fontWeight: 600,
    cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit",
  },
  badge: {
    minWidth: 20, height: 20, padding: "0 6px", boxSizing: "border-box",
    borderRadius: 999, background: "#c9a84c", color: "#fff",
    fontSize: 11, fontWeight: 700,
    display: "inline-flex", alignItems: "center", justifyContent: "center",
  },
  badgeEmpty: { background: "#e5ded0", color: "#9a8b76" },
};
