import { createContext, useState, useEffect } from "react";
import axios from "axios";

export const MyBookshelfContext = createContext();

export function MyBookshelfProvider({ children }) {
  const [myBookshelf, setMyBookshelf] = useState({
    rows: 0,
    cols: 0,
    cells: [],
  });

  const fetchBookshelf = async () => {
    try {
      const res = await axios.get("http://localhost:8000/bookshelf");
      setMyBookshelf(res.data);
    } catch (error) {
      console.error("本棚取得エラー:", error);
    }
  };

  useEffect(() => {
    fetchBookshelf();
  }, []);

  return (
    <MyBookshelfContext.Provider value={{ myBookshelf, fetchBookshelf }}>
      {children}
    </MyBookshelfContext.Provider>
  );
}
