import { createContext, useState } from "react";
import ErrorModal from "../components/ErrorModal";
import axios from "axios";

export const MyBookshelfContext = createContext();

export function MyBookshelfProvider({ children }) {
  const [myBookshelf, setMyBookshelf] = useState([]);
  const [errorMessage, setErrorMessage] = useState("");

  const fetchBookshelf = async () => {
    const res = await fetch("http://localhost:8000/bookshelf/");
    const data = await res.json();
    setMyBookshelf(data);
  };

  // 2. 段数（1段あたりの冊数）の更新・再構築
  const updateShelfLayout = async (newSize) => {
    // サーバー側のAPIエンドポイントに合わせてパスを変更してください
    await axios.post(`http://localhost:8000/bookshelf/add_per_shelf?books_per_shelf=${newSize}`);
    fetchBookshelf();
  };

  const addShelfRow = async () => {
    const res = await fetch("http://localhost:8000/bookshelf/add_shelves", {
      method: "POST",
    });
    if (res.ok) await fetchBookshelf();
  };

  const removeShelfRow = async () => {
    try{
      const res = await fetch("http://localhost:8000/bookshelf/remove_shelves", {
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
    <MyBookshelfContext.Provider value={{ myBookshelf, fetchBookshelf, updateShelfLayout, addShelfRow, removeShelfRow }}>
      {children}
      <ErrorModal 
        message={errorMessage}
        onClose={() => setErrorMessage("")}
      />
    </MyBookshelfContext.Provider>
  );
}
