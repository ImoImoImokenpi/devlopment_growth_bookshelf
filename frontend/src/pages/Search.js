// 本を探す画面（/Search）。書名・著者・キーワード、またはISBNで本を探し、手元に加える。
// 手元に集めた本は、見出しの「手元の本」から育つ本棚に加える（これまでと同じ流れ）。
//
// 使うAPIはすでにあるもの:
//   探す       GET  /books/search?q=…   … 国会図書館 SRU と Google Books（おすすめと同じ検索）
//   書誌の取得 GET  /register/fetch/{isbn} … 国会図書館の詳しい書誌（高さ・ページ数・分類・内容）
//   登録       POST /register/save        … 書誌を保存する（手元に加えるには登録が要る）
//   手元に加える POST /books/add_to_hand
//
// 以前の「本の登録」画面（背表紙の写真とISBNで登録）は pages/RegisterLegacy.js に残してある。
import { useContext, useState } from "react";
import axios from "axios";
import PageHeader from "../components/PageHeader";
import { MyHandContext } from "../context/MyHandContext";

const API = "http://localhost:8000";

export default function Search() {
  const { myHand, refreshMyHand } = useContext(MyHandContext);
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState(null);   // 探した言葉
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);
  // 本ごとの手元に加える処理の状態 { [isbn]: "adding" | "added" | エラー文 }
  const [adding, setAdding] = useState({});

  const search = async (e) => {
    e?.preventDefault();
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    setError(null);
    try {
      const res = await axios.get(`${API}/books/search`, { params: { q } });
      setResults(res.data.results || []);
      setSearched(res.data.query);
      setAdding({});
    } catch (err) {
      setError(err.response?.data?.detail || "本を探せませんでした。少し待ってからもう一度お試しください。");
    } finally {
      setSearching(false);
    }
  };

  // 手元に加える: 未登録なら書誌を登録してから（国会図書館の詳しい書誌があればそちらを使う）
  const addToHand = async (book) => {
    setAdding(prev => ({ ...prev, [book.isbn]: "adding" }));
    try {
      if (!book.registered) {
        let detail = null;
        try {
          detail = (await axios.get(`${API}/register/fetch/${book.isbn}`)).data;
        } catch {
          // 国会図書館に詳しい書誌がない本は、検索で見つかった書誌で登録する
        }
        const data = detail || {
          isbn: book.isbn,
          title: book.title,
          authors: (book.authors || []).join(","),
          publisher: book.publisher,
          published_year: book.published_year,
          ndc_full: book.ndc,
          pages: book.pages,
          height_mm: book.height_mm,
          description: book.description,
        };
        const form = new FormData();
        form.append("book_data", JSON.stringify({ ...data, isbn: book.isbn }));
        await axios.post(`${API}/register/save`, form, { headers: { "Content-Type": "multipart/form-data" } });
      }
      await axios.post(`${API}/books/add_to_hand`, { isbn: book.isbn });
      await refreshMyHand();
      setResults(prev => prev.map(b => (b.isbn === book.isbn ? { ...b, registered: true, in_hand: true } : b)));
      setAdding(prev => ({ ...prev, [book.isbn]: "added" }));
    } catch (err) {
      setAdding(prev => ({ ...prev, [book.isbn]: err.response?.data?.detail || "手元に加えられませんでした" }));
    }
  };

  return (
    <div style={s.page}>
      <PageHeader title="本を探す" sub="書名・著者・ISBNで探して、手元に加えます。手元の本は見出しの「手元の本」から本棚に置けます" />

      <div style={s.columns}>
        <div style={s.mainCol}>
          <form onSubmit={search} style={s.searchRow}>
            <input
              style={s.searchInput}
              type="search"
              placeholder="例: ノルウェイの森 / 夏川草介 猫 / 978-4-06-123456-7"
              value={query}
              onChange={e => setQuery(e.target.value)}
              autoFocus
            />
            <button type="submit" style={{ ...s.btnPrimary, ...(!query.trim() || searching ? s.btnOff : {}) }} disabled={!query.trim() || searching}>
              {searching ? "探しています…" : "探す"}
            </button>
          </form>
          <p style={s.hint}>空白で区切ると、すべての言葉を含む本を探します。国会図書館と Google Books から探します。</p>

          {error && <div style={s.errorBox}>{error}</div>}

          {searched != null && !searching && (
            <div style={s.resultHead}>
              「{searched}」の検索結果 {results.length}件
            </div>
          )}
          {searched != null && !searching && results.length === 0 && !error && (
            <div style={s.empty}>見つかりませんでした。言葉を変えるか、ISBNで探してみてください。</div>
          )}

          <div style={s.results}>
            {results.map(book => (
              <ResultCard key={book.isbn} book={book} state={adding[book.isbn]} onAdd={() => addToHand(book)} />
            ))}
          </div>
        </div>

        <aside style={s.handCol}>
          <div style={s.handTitle}>手元の本（{myHand.length}冊）</div>
          <p style={s.handNote}>見出しの右の「手元の本」を開くと、ここにある本を本棚に置けます。</p>
          {myHand.length === 0 ? (
            <div style={s.handEmpty}>まだありません</div>
          ) : (
            <div style={s.handList}>
              {myHand.map(b => (
                <div key={b.isbn} style={s.handItem}>
                  <Cover isbn={b.isbn} cover={b.cover} title={b.title} small />
                  <div style={s.handText}>
                    <div style={s.handBookTitle}>{b.title || "（書名不明）"}</div>
                    {b.authors?.length > 0 && <div style={s.handAuthors}>{b.authors.join("、")}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function ResultCard({ book, state, onAdd }) {
  const meta = [
    (book.authors || []).join("、"),
    book.publisher,
    book.published_year,
    book.pages ? `${book.pages}ページ` : null,
  ].filter(Boolean).join(" ・ ");
  const failed = state && state !== "adding" && state !== "added";

  let action;
  if (book.in_hand) action = <span style={{ ...s.badge, ...s.badgeHand }}>{state === "added" ? "手元に加えました ✓" : "手元にあります"}</span>;
  else if (state === "adding") action = <button style={{ ...s.addBtn, ...s.btnOff }} disabled>加えています…</button>;
  else action = <button style={s.addBtn} onClick={onAdd}>手元に追加</button>;

  return (
    <div style={s.card}>
      <Cover isbn={book.isbn} title={book.title} />
      <div style={s.cardBody}>
        <div style={s.cardTitle}>{book.title}</div>
        {meta && <div style={s.cardMeta}>{meta}</div>}
        <div style={s.cardIsbn}>ISBN {book.isbn}</div>
        {book.description && <div style={s.cardDesc}>{book.description}</div>}
        <div style={s.cardFoot}>
          {book.on_shelf && <span style={{ ...s.badge, ...s.badgeShelf }}>この本棚にあります</span>}
          <span style={{ flex: 1 }} />
          {action}
        </div>
        {failed && <div style={s.cardError}>{state}</div>}
      </div>
    </div>
  );
}

// 表紙（取れなければ書名の札）。表紙は登録と同じ取り方（/register/cover）で取る
function Cover({ isbn, cover, title, small }) {
  const [src, setSrc] = useState(cover || `${API}/register/cover/${isbn}`);
  const [failed, setFailed] = useState(false);
  const box = small ? s.coverSmall : s.cover;
  if (failed) return <div style={{ ...box, ...s.coverEmpty }}>{small ? "" : (title || "").slice(0, 18)}</div>;
  return (
    <img
      src={src}
      alt=""
      style={box}
      loading="lazy"
      onError={() => {
        const proxy = `${API}/register/cover/${isbn}`;
        if (src !== proxy) setSrc(proxy); else setFailed(true);
      }}
    />
  );
}

const s = {
  page: {},
  columns: { display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(260px, 340px)", gap: 28, alignItems: "start" },
  mainCol: { background: "#fff", border: "1px solid #ede8da", borderRadius: 16, padding: "22px 24px 26px", minWidth: 0 },
  searchRow: { display: "flex", gap: 8 },
  searchInput: {
    flex: 1, minWidth: 0, padding: "12px 14px", borderRadius: 10, border: "1px solid #d0c4a8",
    fontSize: 15, backgroundColor: "#faf8f2", outline: "none", fontFamily: "inherit",
  },
  btnPrimary: {
    padding: "12px 22px", backgroundColor: "#c9a84c", color: "#fff", border: "none", borderRadius: 10,
    fontSize: 14, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit",
  },
  btnOff: { opacity: 0.5, cursor: "default" },
  hint: { fontSize: 12, color: "#aaa", margin: "8px 0 0", lineHeight: 1.6 },
  errorBox: {
    marginTop: 16, padding: "12px 16px", backgroundColor: "#fff0f0", borderRadius: 10,
    color: "#c94040", fontSize: 13, border: "1px solid #f5c6c6",
  },
  resultHead: { marginTop: 22, fontSize: 13, fontWeight: 700, color: "#8a7030" },
  empty: { marginTop: 12, fontSize: 13, color: "#9a8a6a" },
  results: { marginTop: 12, display: "flex", flexDirection: "column", gap: 10 },
  card: {
    display: "flex", gap: 16, padding: "14px 16px", border: "1px solid #ede8da", borderRadius: 12,
    background: "#fff", alignItems: "flex-start",
  },
  cover: { width: 64, height: 92, objectFit: "cover", borderRadius: 4, flexShrink: 0, background: "#f5f0e8", boxShadow: "0 2px 6px rgba(60,40,10,0.15)" },
  coverSmall: { width: 34, height: 48, objectFit: "cover", borderRadius: 3, flexShrink: 0, background: "#f5f0e8" },
  coverEmpty: {
    display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center",
    fontSize: 10, color: "#9a8a6a", padding: 4, boxSizing: "border-box", fontFamily: "serif",
  },
  cardBody: { flex: 1, minWidth: 0 },
  cardTitle: { fontSize: 15, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif", lineHeight: 1.4 },
  cardMeta: { fontSize: 12.5, color: "#7a6a4a", marginTop: 4 },
  cardIsbn: { fontSize: 11, color: "#bbb", marginTop: 2, fontFamily: "monospace" },
  cardDesc: {
    fontSize: 12, color: "#888", marginTop: 6, lineHeight: 1.6,
    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
  },
  cardFoot: { display: "flex", alignItems: "center", gap: 8, marginTop: 10, flexWrap: "wrap" },
  cardError: { fontSize: 12, color: "#c94040", marginTop: 6 },
  addBtn: {
    padding: "8px 16px", borderRadius: 999, border: "none", background: "#c9a84c", color: "#fff",
    fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
  },
  badge: { fontSize: 12, fontWeight: 700, borderRadius: 999, padding: "5px 12px", whiteSpace: "nowrap" },
  badgeHand: { background: "#e8f5e9", color: "#2e7d32" },
  badgeShelf: { background: "#f5efdd", color: "#8a7030" },
  handCol: { background: "#f3eee2", borderRadius: 16, padding: "20px 18px", position: "sticky", top: 16 },
  handTitle: { fontSize: 13, fontWeight: 700, color: "#c9a84c", letterSpacing: "0.05em" },
  handNote: { fontSize: 12, color: "#8a7a5a", lineHeight: 1.6, margin: "6px 0 12px" },
  handEmpty: { fontSize: 12.5, color: "#a09070" },
  handList: { display: "flex", flexDirection: "column", gap: 8, maxHeight: "60vh", overflowY: "auto" },
  handItem: { display: "flex", gap: 10, alignItems: "center", background: "#fff", borderRadius: 10, padding: "8px 10px", border: "1px solid #ede8da" },
  handText: { minWidth: 0 },
  handBookTitle: { fontSize: 12.5, fontWeight: 700, color: "#2a1f0e", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  handAuthors: { fontSize: 11, color: "#9a8a6a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
};
