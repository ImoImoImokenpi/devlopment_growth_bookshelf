// 「他の参加者の本棚を観察する」画面の「グリッド表示」モード。
//
// 対象の参加者IDを withParticipant() で明示的に指定して読み取る
// （自分のIDは変えない）。見た目とソートはMy本棚と共通の BookGridPane に任せる。
import { useEffect, useState } from "react";
import { withParticipant } from "../../utils/participant";
import BookGridPane from "../BookGridPane";

const API = "http://localhost:8000";

export default function ReadOnlyBookGrid({ participantId, focusIsbn, onFocus }) {
  const [bookshelf, setBookshelf] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    fetch(`${API}/bookshelf/`, withParticipant(participantId))
      .then(res => (res.ok ? res.json() : Promise.reject(new Error("本棚を読み込めませんでした"))))
      .then(json => { if (!cancelled) setBookshelf(json); })
      .catch(err => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [participantId]);

  if (isLoading) return <p style={s.status}>読み込み中…</p>;
  if (error) return <p style={s.statusError}>{error}</p>;

  const books = (bookshelf?.shelves || []).flatMap(shelf => shelf.books || []);
  return (
    <BookGridPane
      books={books}
      focusIsbn={focusIsbn}
      onFocus={onFocus}
      emptyMessage="この参加者の本棚にはまだ本がありません。"
    />
  );
}

const s = {
  status: { color: "#888", fontSize: 14 },
  statusError: { color: "#c9506a", fontSize: 14 },
};
