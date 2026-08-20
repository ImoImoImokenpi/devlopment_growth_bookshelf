// まとめて確認モード（設計書6.2）。
//
// 推測エッジや発見が一定数溜まると、本棚の上に質問カードが何枚も出て
// 邪魔になる。溜まったぶんをここで一気に片付けられるようにする。
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";
import DiscoveryResponse from "./DiscoveryResponse";

const API = "http://localhost:8000";

const TYPE_LABEL = {
  commonality: "共通点",
  contradiction: "食い違い",
  implicit_pattern: "並べ方の癖",
  structural: "全体の構造",
};

export default function BatchReview() {
  const {
    isBatchOpen, setIsBatchOpen,
    pendingDiscoveries, answerDiscovery,
    setHighlightIsbns, setChatSeed,
  } = useShelfWorkspace();

  if (!isBatchOpen) return null;

  return (
    <div style={s.overlay} onClick={() => setIsBatchOpen(false)}>
      <div style={s.panel} onClick={e => e.stopPropagation()}>
        <div style={s.head}>
          <div>
            <div style={s.title}>まとめて確認</div>
            <div style={s.sub}>
              {pendingDiscoveries.length > 0
                ? `${pendingDiscoveries.length}件の問いかけが待っています`
                : "確認待ちの問いかけはありません"}
            </div>
          </div>
          <button style={s.closeBtn} onClick={() => setIsBatchOpen(false)}>✕</button>
        </div>

        <div style={s.list}>
          {pendingDiscoveries.length === 0 && (
            <div style={s.empty}>
              本を並べ替えたり意味づけを重ねると、棚のほうから問いかけが増えていきます。
            </div>
          )}

          {pendingDiscoveries.map(d => (
            <div
              key={d.discovery_id}
              style={s.card}
              onMouseEnter={() => setHighlightIsbns(d.related_book_ids || [])}
              onMouseLeave={() => setHighlightIsbns([])}
            >
              <div style={s.cardHead}>
                <span style={s.typeBadge}>{TYPE_LABEL[d.type] || "気づき"}</span>
                {(d.related_book_ids || []).length > 0 && (
                  <span style={s.bookCount}>{d.related_book_ids.length}冊</span>
                )}
              </div>

              <div style={s.question}>{d.generated_question}</div>
              {d.body && <div style={s.body}>{d.body}</div>}

              {(d.related_book_ids || []).length > 0 && (
                <div style={s.coverRow}>
                  {d.related_book_ids.slice(0, 8).map(isbn => (
                    <img
                      key={isbn}
                      src={`${API}/register/cover/${isbn}`}
                      alt=""
                      style={s.cover}
                      onError={e => { e.target.style.display = "none"; }}
                    />
                  ))}
                </div>
              )}

              <DiscoveryResponse
                discovery={d}
                onAnswer={answerDiscovery}
                onTalkMore={() => {
                  setChatSeed({ question: d.generated_question, isbns: d.related_book_ids || [] });
                  setIsBatchOpen(false);
                }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const s = {
  overlay: {
    position: "fixed", inset: 0, zIndex: 4000,
    background: "rgba(30,24,14,0.35)", backdropFilter: "blur(3px)",
    display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
  },
  panel: {
    width: 560, maxWidth: "94vw", maxHeight: "82vh",
    background: "#fdfcf8", borderRadius: 16,
    border: "1px solid #ede8da", boxShadow: "0 24px 60px rgba(0,0,0,0.25)",
    display: "flex", flexDirection: "column", overflow: "hidden",
  },
  head: {
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    padding: "16px 18px", borderBottom: "1px solid #ede8da",
  },
  title: { fontSize: 15, fontWeight: 700, fontFamily: "serif", color: "#2a1f0e" },
  sub: { fontSize: 11.5, color: "#9a8b76", marginTop: 3 },
  closeBtn: {
    width: 24, height: 24, borderRadius: "50%", border: "none",
    background: "#ede8da", color: "#4a3728", cursor: "pointer", fontSize: 12, lineHeight: 1,
  },
  list: {
    flex: 1, overflowY: "auto", padding: 16,
    display: "flex", flexDirection: "column", gap: 12,
  },
  empty: {
    fontSize: 12, color: "#9a8b76", lineHeight: 1.9,
    textAlign: "center", padding: "40px 24px",
  },
  card: {
    border: "1px solid #ede8da", borderRadius: 12, padding: 14,
    background: "#fff", display: "flex", flexDirection: "column", gap: 10,
  },
  cardHead: { display: "flex", alignItems: "center", gap: 8 },
  typeBadge: {
    fontSize: 9.5, fontWeight: 700, color: "#c9a84c",
    border: "1px solid #e8dcb8", borderRadius: 999, padding: "2px 8px",
    letterSpacing: "0.04em",
  },
  bookCount: { fontSize: 10, color: "#b3a692" },
  question: { fontSize: 13.5, fontWeight: 600, color: "#2a1f0e", lineHeight: 1.6 },
  body: { fontSize: 11.5, color: "#6b5c47", lineHeight: 1.75 },
  coverRow: { display: "flex", gap: 5, overflowX: "auto" },
  cover: {
    width: 28, height: 40, objectFit: "cover", borderRadius: 3,
    background: "#eee", flexShrink: 0,
  },
};
