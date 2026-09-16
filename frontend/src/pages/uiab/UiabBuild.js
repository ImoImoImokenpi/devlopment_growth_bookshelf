import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { uiabGet, uiabPost, getUiabId } from "../../utils/uiabIdentity";
import NewFreeShelf from "../../components/uiab/NewFreeShelf";
import OldGridShelf from "../../components/uiab/OldGridShelf";
import UiabBookSearch from "../../components/uiab/UiabBookSearch";
import UiabGroupingPanel from "../../components/uiab/UiabGroupingPanel";
import UiabImpressionEditor from "../../components/uiab/UiabImpressionEditor";

const PERIOD_LABEL = { period1: "時期1(数年前)", period2: "時期2(現在)" };

export default function UiabBuild() {
  const { period } = useParams();
  const navigate = useNavigate();
  const [variant, setVariant] = useState(null);
  const [collection, setCollection] = useState([]);
  const [positions, setPositions] = useState([]);
  const [selectedIsbns, setSelectedIsbns] = useState([]);
  const [focusIsbn, setFocusIsbn] = useState(null);
  const [completing, setCompleting] = useState(false);

  const refresh = useCallback(() => {
    uiabGet(`/uiab/${period}/collection`).then(setCollection).catch(err => console.error(err));
    uiabGet(`/uiab/${period}/shelf`).then(setPositions).catch(err => console.error(err));
  }, [period]);

  useEffect(() => {
    if (!getUiabId()) { navigate("/Uiab"); return; }
    setFocusIsbn(null);
    setSelectedIsbns([]);
    uiabGet("/uiab/whoami").then(d => setVariant(d.ui_variant)).catch(err => console.error(err));
    uiabPost(`/uiab/${period}/session/start`).catch(err => console.error(err));
    refresh();
  }, [period, refresh, navigate]);

  const placedIsbns = new Set(positions.map(p => p.isbn));
  const unplaced = collection.filter(b => !placedIsbns.has(b.isbn));

  const toggleSelect = (isbn) => {
    setSelectedIsbns(prev => (prev.includes(isbn) ? prev.filter(i => i !== isbn) : [...prev, isbn]));
  };

  const complete = async () => {
    if (positions.length === 0) {
      if (!window.confirm("まだ1冊も配置していません。このまま完了しますか？")) return;
    }
    setCompleting(true);
    try {
      await uiabPost(`/uiab/${period}/session/complete`);
      navigate(`/Uiab/SelfReport/${period}`);
    } catch (err) {
      console.error(err);
    } finally {
      setCompleting(false);
    }
  };

  if (!variant) return <div style={s.loading}>読み込み中…</div>;

  const ShelfComponent = variant === "new" ? NewFreeShelf : OldGridShelf;
  const focusTitle = positions.find(p => p.isbn === focusIsbn)?.title
    || unplaced.find(b => b.isbn === focusIsbn)?.title;

  return (
    <div style={s.page}>
      <div style={s.header}>
        <h1 style={s.title}>{PERIOD_LABEL[period] || period}の本棚をつくる</h1>
        <button style={s.completeBtn} onClick={complete} disabled={completing}>
          {completing ? "保存中…" : "この時期の本棚を完成させる"}
        </button>
      </div>

      <div style={s.body}>
        <aside style={s.sidebar}>
          <UiabBookSearch period={period} onAdded={refresh} />
          <UiabGroupingPanel period={period} selectedIsbns={selectedIsbns} onCleared={() => setSelectedIsbns([])} />
          {focusIsbn && <UiabImpressionEditor period={period} isbn={focusIsbn} title={focusTitle} />}
        </aside>

        <main style={s.shelfArea}>
          <ShelfComponent
            period={period}
            positions={positions}
            unplaced={unplaced}
            selectedIsbns={selectedIsbns}
            onToggleSelect={toggleSelect}
            onFocus={setFocusIsbn}
            onChanged={refresh}
          />
        </main>
      </div>
    </div>
  );
}

const s = {
  page: { minHeight: "100vh", background: "#f7f3ea", padding: "24px 28px 60px" },
  loading: { padding: 60, textAlign: "center", color: "#9a8b76", fontSize: 13 },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    marginBottom: 18, flexWrap: "wrap", gap: 10,
  },
  title: { fontSize: 18, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif" },
  completeBtn: {
    padding: "10px 18px", background: "#c9a84c", color: "#fff", border: "none",
    borderRadius: 10, fontSize: 13, fontWeight: 700, cursor: "pointer",
  },
  body: { display: "flex", gap: 20, alignItems: "flex-start" },
  sidebar: {
    width: 280, flexShrink: 0, display: "flex", flexDirection: "column", gap: 18,
    background: "#fff", borderRadius: 14, padding: 16, border: "1px solid #ede8da",
  },
  shelfArea: { flex: 1, minWidth: 0 },
};
