import { createContext, useState, useEffect } from "react";
import axios from "axios";

export const MyBookshelfContext = createContext();

export const MyBookshelfProvider = ({ children }) => {
    const [myBookshelf, setMyBookshelf] = useState([]);

    // 初回だけDBから取得
    useEffect(() => {
        axios.get("http://localhost:8000/books/mybookshelf")
        .then(res => setMyBookshelf(res.data))
        .catch(err => console.error(err));
    }, []);

    return (
        <MyBookshelfContext.Provider value={{ myBookshelf, setMyBookshelf }}>
        {children}
        </MyBookshelfContext.Provider>
    );
};
