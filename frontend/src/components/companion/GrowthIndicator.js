// 育成インジケータ（設計書6.4）。
//
// 「KGの成長を数値でなく雰囲気で表現する」ため、冊数や意味づけ数といった
// 数字は一切出さない。灯りの強さと言葉づかいだけで、育ってきたことを伝える。
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";

// 育ち具合に応じた語り。数値の代わりにこれで段階を感じ取ってもらう。
const PHASES = [
  { upTo: 0.05, label: "灯りはまだ小さい",   hint: "本に言葉を添えると、棚が少しずつ目を覚まします" },
  { upTo: 0.25, label: "ほのかに灯っている", hint: "いくつかの本が、あなたの言葉でつながり始めました" },
  { upTo: 0.50, label: "棚が温まってきた",   hint: "棚のほうから話しかけてくることが増えてきます" },
  { upTo: 0.75, label: "よく灯っている",     hint: "あなたらしい並びの輪郭が見えてきました" },
  { upTo: 1.01, label: "棚が深く息づいている", hint: "この棚は、もうあなたのことをかなり知っています" },
];

function phaseOf(level) {
  return PHASES.find(p => level < p.upTo) ?? PHASES[PHASES.length - 1];
}

export default function GrowthIndicator() {
  const { growth } = useShelfWorkspace();
  const level = growth?.level ?? 0;
  const phase = phaseOf(level);

  // 灯りの強さ。完全な消灯にはせず、常にわずかに灯している。
  const glow = 0.18 + level * 0.82;

  return (
    <div style={s.wrap} title={phase.hint}>
      <div style={s.lampBox}>
        <div
          style={{
            ...s.halo,
            opacity: glow,
            transform: `scale(${0.7 + level * 0.6})`,
          }}
        />
        <div
          style={{
            ...s.core,
            background: `radial-gradient(circle at 40% 35%, rgba(255,244,214,${0.55 + glow * 0.45}), rgba(201,168,76,${0.35 + glow * 0.5}))`,
            boxShadow: `0 0 ${6 + level * 22}px rgba(201,168,76,${glow})`,
          }}
        />
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={s.label}>{phase.label}</div>
        <div style={s.hint}>{phase.hint}</div>
      </div>
    </div>
  );
}

const s = {
  wrap: {
    display: "flex", alignItems: "center", gap: 12,
    padding: "12px 14px",
    borderBottom: "1px solid #ede8da",
    background: "linear-gradient(180deg, #fffdf7 0%, #fdfcf8 100%)",
    flexShrink: 0,
  },
  lampBox: {
    position: "relative", width: 30, height: 30, flexShrink: 0,
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  halo: {
    position: "absolute", inset: -6, borderRadius: "50%",
    background: "radial-gradient(circle, rgba(201,168,76,0.45) 0%, rgba(201,168,76,0) 70%)",
    transition: "opacity 1.2s ease, transform 1.2s ease",
    pointerEvents: "none",
  },
  core: {
    width: 14, height: 14, borderRadius: "50%",
    transition: "box-shadow 1.2s ease, background 1.2s ease",
  },
  label: {
    fontSize: 12, fontWeight: 700, color: "#2a1f0e",
    fontFamily: "serif", lineHeight: 1.4,
  },
  hint: {
    fontSize: 10.5, color: "#9a8b76", lineHeight: 1.5, marginTop: 2,
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
};
