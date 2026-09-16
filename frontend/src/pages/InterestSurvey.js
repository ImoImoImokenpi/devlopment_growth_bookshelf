// フェーズ2 (c) 興味分野質問。
//
// アンカリング防止のため、配置画面（Home）とは完全に独立した画面として
// 実装する。選択肢は「現在棚に並んでいる本のジャンル」から動的に作り、
// タップした順番がそのまま興味の強い順になる（フルランキングは強制しない。
// 興味がある分だけタップすればよい）。
import { useCallback, useEffect, useState } from "react";
import PageHeader from "../components/PageHeader";

const API = "http://localhost:8000";

export default function InterestSurvey() {
  const [genres, setGenres] = useState([]);
  const [ranked, setRanked] = useState([]); // [{tag, rank}]
  const [busyTag, setBusyTag] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => {
    fetch(`${API}/intent-survey/interests`)
      .then(res => res.json())
      .then(data => {
        setGenres(data.genres || []);
        setRanked(data.ranked || []);
      })
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => { load(); }, [load]);

  const rankOf = (tag) => {
    const found = ranked.find(r => r.tag === tag);
    return found ? found.rank : null;
  };

  const toggle = useCallback(async (tag) => {
    const isRanked = ranked.some(r => r.tag === tag);
    setBusyTag(tag);
    try {
      const res = await fetch(`${API}/intent-survey/interests${isRanked ? `/${encodeURIComponent(tag)}` : ""}`, {
        method: isRanked ? "DELETE" : "POST",
        headers: isRanked ? undefined : { "Content-Type": "application/json" },
        body: isRanked ? undefined : JSON.stringify({ tag }),
      });
      if (res.ok) {
        const data = await res.json();
        setGenres(data.genres || []);
        setRanked(data.ranked || []);
      }
    } finally {
      setBusyTag(null);
    }
  }, [ranked]);

  return (
    <div style={s.page}>
      <PageHeader
        title="興味・関心について"
        sub="今の本棚にあるジャンルの中から、興味が強いと思う順にタップしてください（いくつでも／途中までで構いません）"
      />

      {!loaded ? (
        <div style={s.status}>読み込み中…</div>
      ) : genres.length === 0 ? (
        <div style={s.status}>まだ棚に本が並んでいないため、選べるジャンルがありません</div>
      ) : (
        <>
          <div style={s.grid}>
            {genres.map(g => {
              const rank = rankOf(g.tag);
              const active = rank != null;
              return (
                <button
                  key={g.tag}
                  style={{ ...s.tile, ...(active ? s.tileActive : {}), ...(busyTag === g.tag ? s.tileBusy : {}) }}
                  onClick={() => toggle(g.tag)}
                  disabled={busyTag === g.tag}
                >
                  {active && <span style={s.rankBadge}>{rank}</span>}
                  <span style={s.tileTag}>{g.tag}</span>
                </button>
              );
            })}
          </div>
          <p style={s.savedHint}>タップした順番がそのまま興味の強い順として保存されます。もう一度タップすると取り消せます。</p>
        </>
      )}
    </div>
  );
}

const s = {
  page: {
    padding: "90px 28px 60px",
    minHeight: "100vh",
    backgroundColor: "#fdfcf8",
    maxWidth: "760px",
    margin: "0 auto",
  },
  status: { fontSize: 13, color: "#9a8b76", textAlign: "center", padding: "40px 0" },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
    gap: 10,
    marginTop: 12,
  },
  tile: {
    position: "relative",
    padding: "14px 10px",
    borderRadius: 12,
    border: "1px solid #e5ded0",
    background: "#fff",
    color: "#2a1f0e",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    transition: "all 0.15s",
  },
  tileActive: {
    borderColor: "#c9a84c",
    background: "#fdf6e3",
    color: "#8a6d1f",
    boxShadow: "0 0 0 1px #c9a84c inset",
  },
  tileBusy: { opacity: 0.6, cursor: "wait" },
  tileTag: { display: "block" },
  rankBadge: {
    position: "absolute", top: -8, left: -8,
    width: 22, height: 22, borderRadius: "50%",
    background: "#c9a84c", color: "#fff", fontSize: 11, fontWeight: 700,
    display: "flex", alignItems: "center", justifyContent: "center",
    boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
  },
  savedHint: { marginTop: 24, fontSize: 12, color: "#aaa", textAlign: "center" },
};
