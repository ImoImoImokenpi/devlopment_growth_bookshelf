// 「他の参加者の本棚を観察する」画面の右ペイン（本詳細・読み取り専用）。
//
// 感想・意味づけはその人の主観的な記録なので、観察画面では表示しない
// （書誌情報のみを見せる）。差異対話（ComparisonDialoguePanel）で扱う
// 構造的な傾向の話とは別に、1冊単位の個人的な内容を覗けてしまわないようにする。
import { useEffect, useState } from "react";
import { withParticipant } from "../../utils/participant";

const API = "http://localhost:8000";

export default function ReadOnlyBookFocusPanel({ participantId, isbn, onClose }) {
  const [book, setBook] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isbn) {
      setBook(null);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetch(`${API}/knowledge_graph/book/${isbn}/basic`, withParticipant(participantId))
      .then(res => (res.ok ? res.json() : null))
      .then(basic => { if (!cancelled) setBook(basic); })
      .catch(err => {
        if (!cancelled) setError("読み込みに失敗しました");
        console.error(err);
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });

    return () => { cancelled = true; };
  }, [isbn, participantId]);

  if (!isbn) {
    return (
      <div style={s.wrap}>
        <div style={s.status}>本棚で1冊クリックすると、ここに書誌情報が表示されます</div>
      </div>
    );
  }

  return (
    <div style={s.wrap}>
      <div style={s.head}>
        <span style={s.title}>{book?.title || "本詳細"}</span>
        <button style={s.closeBtn} onClick={onClose}>✕</button>
      </div>

      {isLoading && !book && <div style={s.status}>読み込み中…</div>}
      {error && <div style={s.statusError}>{error}</div>}

      {book && (
        <div style={s.body}>
          <div style={s.bookHeader}>
            {(book.cover || book.spine_image) && (
              <img
                src={book.cover || `${API}/register/cover/${book.isbn}`}
                alt=""
                style={s.cover}
                onError={e => {
                  if (!e.target.dataset.fallback) {
                    e.target.dataset.fallback = "1";
                    e.target.src = `${API}/register/cover/${book.isbn}`;
                  }
                }}
              />
            )}
            <div style={{ minWidth: 0 }}>
              {book.authors && <div style={s.meta}>{book.authors}</div>}
              {book.publisher && (
                <div style={s.meta}>
                  {book.publisher}{book.published_year ? `（${book.published_year}）` : ""}
                </div>
              )}
            </div>
          </div>

          {book.description && <div style={s.description}>{book.description}</div>}

          <div style={s.hiddenHint}>感想・意味づけはこの人だけのものなので表示されません</div>
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: {
    borderBottom: "1px solid #ede8da",
    background: "#fffdf7",
    flexShrink: 0,
    height: "100%",
    overflowY: "auto",
  },
  head: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "10px 12px 8px", gap: 8,
    position: "sticky", top: 0, background: "#fffdf7", zIndex: 1,
  },
  title: {
    fontSize: 12.5, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif",
    lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  closeBtn: {
    width: 20, height: 20, borderRadius: "50%", border: "none",
    background: "#ede8da", color: "#4a3728", cursor: "pointer",
    fontSize: 11, lineHeight: 1, flexShrink: 0,
  },
  body: { padding: "0 12px 12px" },
  status: { fontSize: 12, color: "#9a8b76", textAlign: "center", padding: "20px 10px" },
  statusError: { fontSize: 12, color: "#c9506a", textAlign: "center", padding: "12px 10px" },
  bookHeader: { display: "flex", gap: 10, marginBottom: 4 },
  cover: {
    width: 44, height: 62, objectFit: "cover", borderRadius: 4,
    background: "#eee", flexShrink: 0, boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
  },
  meta: { fontSize: 11, color: "#6b5c47", marginBottom: 2, lineHeight: 1.45 },
  description: {
    fontSize: 11.5, color: "#3a2f20", lineHeight: 1.7,
    marginTop: 10,
  },
  hiddenHint: {
    fontSize: 10.5, color: "#c4b8a2", marginTop: 14,
    paddingTop: 10, borderTop: "1px solid #ede8da",
  },
};
