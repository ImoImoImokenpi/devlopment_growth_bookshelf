import { createContext, useState, useEffect } from "react";
import axios from "axios";

export const MyHandContext = createContext(null);

export function MyHandProvider({ children }) {
    const [myHand, setMyHand] = useState([]);

    // 初回ロードで手元の本を取得
    useEffect(() => {
        const fetchMyHand = async () => {
        try {
            const res = await axios.get("http://localhost:8000/books/myhand");
            setMyHand(res.data);
        } catch (err) {
            console.error("手元本の取得エラー", err);
        }
        };
        fetchMyHand();
    }, []);
    
    return (
        <MyHandContext.Provider value={{ myHand, setMyHand }}>
            {children}
        </MyHandContext.Provider>
    );
}
