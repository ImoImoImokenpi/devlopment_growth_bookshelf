// My本棚画面の「グリッド表示」モード（背表紙表示 SpineShelfView との切り替え先）。
//
// データは自分の本棚（MyBookshelfContext）そのまま。クリックすると
// ShelfWorkspaceContext の focusIsbn をセットし、右ペインの本詳細
// （感想・意味づけ）を背表紙表示のときと同じように開けるようにする。
import { useContext, useEffect, useMemo } from "react";
import { MyBookshelfContext } from "../context/MyBookshelfContext";
import { useShelfWorkspace } from "../context/ShelfWorkspaceContext";
import BookGridPane from "./BookGridPane";

export default function OwnBookGrid() {
  const { myBookshelf, fetchBookshelf } = useContext(MyBookshelfContext);
  const { focusIsbn, setFocusIsbn } = useShelfWorkspace();

  useEffect(() => { fetchBookshelf(); }, [fetchBookshelf]);

  const books = useMemo(
    () => (myBookshelf?.shelves || []).flatMap(shelf => shelf.books || []),
    [myBookshelf]
  );

  return <BookGridPane books={books} focusIsbn={focusIsbn} onFocus={setFocusIsbn} />;
}
