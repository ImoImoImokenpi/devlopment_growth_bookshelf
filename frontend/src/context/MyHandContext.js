import { createContext, useState, useEffect, useCallback } from "react";
import axios from "axios";

export const MyHandContext = createContext(null);

export function MyHandProvider({ children }) {
    const [myHand, setMyHand] = useState([]);

    // 手元の本を取り直す（本を探す画面で手元に加えたあとにも呼ぶ）
    const refreshMyHand = useCallback(async () => {
        try {
            const res = await axios.get("http://localhost:8000/books/myhand");
            setMyHand(res.data);
        } catch (err) {
            console.error("手元本の取得エラー", err);
        }
    }, []);

    // 初回ロードで手元の本を取得
    useEffect(() => { refreshMyHand(); }, [refreshMyHand]);

    return (
        <MyHandContext.Provider value={{ myHand, setMyHand, refreshMyHand }}>
            {children}
        </MyHandContext.Provider>
    );
}
