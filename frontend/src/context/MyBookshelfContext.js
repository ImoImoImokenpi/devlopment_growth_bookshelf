import { createContext, useState, useEffect } from "react";
import axios from "axios";

export const MyBookshelfContext = createContext();

export function MyBookshelfProvider({ children }) {
  const [myBookshelf, setMyBookshelf] = useState([]);

  const fetchBookshelf = async () => {
    try {
      const res = await axios.get("http://localhost:8000/mybookshelf");
      setMyBookshelf(res.data);
    } catch (error) {
      console.error("本棚取得エラー:", error);
    }
  };

  useEffect(() => {
    fetchBookshelf();
  }, []);

  return (
    <MyBookshelfContext.Provider
      value={{ myBookshelf, setMyBookshelf, fetchBookshelf }}
    >
      {children}
    </MyBookshelfContext.Provider>
  );
}
