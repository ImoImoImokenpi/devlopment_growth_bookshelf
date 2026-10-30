import { createContext, useState, useCallback } from "react";
import ErrorModal from "../components/ErrorModal";

export const MyBookshelfContext = createContext();

// 本棚は「今の本棚」1つだけを扱う（動作確認用だった「過去の本棚」は廃止）。
// バックエンドAPIは period パラメータを受け取るので、値は "present" 固定で渡す。
const PERIOD = "present";

export function MyBookshelfProvider({ children }) {
  const [myBookshelf, setMyBookshelf] = useState([]);
  const [errorMessage, setErrorMessage] = useState("");
  const period = PERIOD;

  const fetchBookshelf = useCallback(async () => {
    const res = await fetch(`http://localhost:8000/bookshelf/?period=${period}`);
    const data = await res.json();
    setMyBookshelf(data);
  }, [period]);

  const addShelfRow = async () => {
    const res = await fetch(`http://localhost:8000/bookshelf/add_shelves?period=${period}`, {
      method: "POST",
    });
    if (res.ok) await fetchBookshelf();
  };

  // id は ShelfLayout の行id（本棚には同じ本を複数冊置けるため、
  // isbnだけでは「どの1冊か」を特定できない）。
  const removeBook = useCallback(async (id) => {
    await fetch(`http://localhost:8000/bookshelf/remove-book/${id}?period=${period}`, { method: "DELETE" });
    fetchBookshelf();
  }, [fetchBookshelf, period]);

  const removeShelfRow = async () => {
    try{
      const res = await fetch(`http://localhost:8000/bookshelf/remove_shelves?period=${period}`, {
        method: "POST",
      });

      const data = await res.json();

      if (!res.ok) {
        setErrorMessage(data.detail);
        return;
      }

      fetchBookshelf();

    } catch (err) {
      setErrorMessage("通信エラーが発生しました");
    }
  };

  return (
    <MyBookshelfContext.Provider value={{ myBookshelf, fetchBookshelf, addShelfRow, removeShelfRow, removeBook, period }}>
      {children}
      <ErrorModal
        message={errorMessage}
        onClose={() => setErrorMessage("")}
      />
    </MyBookshelfContext.Provider>
  );
}
