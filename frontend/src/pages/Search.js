import { useState, useEffect, useContext } from "react";
import Layout from "../components/Layout";
import axios from "axios";
import { MyHandContext } from "../context/MyHandContext";

function Search() {
    const [query, setQuery] = useState("");
    const [books, setBooks] = useState([]);
    const { myHand, setMyHand } = useContext(MyHandContext);
    const [loading, setLoading] = useState(false);
    
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const perPage = 20;

    // 📚 検索する
    const searchBooks = async (p) => {
        if (!query.trim()) return;
        setLoading(true);
        try {
            const res = await axios.get(`http://localhost:8000/search?q=${query}&page=${p}&per_page=${perPage}`);
            const data = res.data;
            const validBooks = (data.books || []).filter(b => b.id);
            setBooks(validBooks);
            setPage(p);
            setTotalPages(data.total_pages || 1);
        } catch (error) {
            console.error("検索エラー：", error);
        }
        setLoading(false);
    };
    
    // 📚 手元に追加する処理
    const addToHand = async (book) => {
        try {
            const res = await axios.post("http://localhost:8000/books/add_to_hand", {
                book_id: book.id,
                title: book.title,
                author: book.author,
                cover: book.cover,
            });
            
            if (res.data.message === "already exists") {
                alert("既に追加されています。");
                return;
            }

            setMyHand([...myHand, { 
                book_id: book.id,
                title: book.title,
                author: book.author,
                cover: book.cover,
            }]);
            
            alert(`📚『${book.title}』を手元に追加しました！`);

        } catch (error) {
            console.error("追加エラー：", error);
            alert("追加に失敗しました");
        }
    };

    const viewDetails = (book) => {
        alert(
            `📘 タイトル: ${book.title}\n` +
            `👤 著者: ${book.author}\n` +
            `ID: ${book.id}\n` +
            `ISBN-13: ${book.isbn_13 || "不明"}\n` +
            `ISBN-10: ${book.isbn_10 || "不明"}`
        );
    };

    return (
        <Layout>
        <div>
            <h1>本を探す</h1>
            <input
                type="text"
                placeholder="書名で検索..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && searchBooks(1)}
            />
            <button 
                onClick={() => searchBooks(1)}
            >
                    検索
            </button>
            
                {/* 検索結果 */}
                {loading ? (
                    <p>検索中...</p>
                ) : (
                    <>
                        <div
                            style={{
                                display: "grid",
                                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                                gap: "20px",
                                width: "100%",
                            }}
                        >
                            {books.length === 0 ? (
                                <p>検索結果がありません。</p>
                            ) : (
                                books.map((book) => (
                                    <div
                                        key={book.id}
                                        style={{
                                            border: "1px solid #ddd",
                                            borderRadius: "10px",
                                            padding: "10px",
                                            textAlign: "center",
                                            boxShadow: "0 2px 5px rgba(0,0,0,0.1)",
                                            transition: "transform 0.2s",
                                        }}
                                    >
                                        {book.cover ? (
                                            <img
                                                src={book.cover}
                                                alt={book.title}
                                                style={{
                                                    width: "100px",
                                                    height: "150px",
                                                    objectFit: "cover",
                                                    borderRadius: "5px",
                                                }}
                                                onError={(e) => (e.target.style.display = "none")}
                                            />
                                        ) : (
                                            <div
                                                style={{
                                                    width: "100px",
                                                    height: "150px",
                                                    backgroundColor: "#f0f0f0",
                                                    display: "inline-flex",
                                                    alignItems: "center",
                                                    justifyContent: "center",
                                                    color: "#888",
                                                    fontSize: "12px",
                                                }}
                                            >
                                                No Image
                                            </div>
                                        )}
                                        <h3 style={{ fontSize: "14px", marginTop: "10px" }}>{book.title}</h3>
                                        <p style={{ fontSize: "12px", color: "#555" }}>{book.author}</p>

                                        <div style={{ marginTop: "10px" }}>
                                            <button
                                                onClick={() => viewDetails(book)}
                                                style={{
                                                    marginRight: "6px",
                                                    padding: "5px 10px",
                                                    borderRadius: "5px",
                                                    border: "1px solid #ccc",
                                                    background: "#fff",
                                                    cursor: "pointer",
                                                }}
                                            >
                                                詳細
                                            </button>

                                            {/* ⭐ 追加ボタン */}
                                            <button
                                                style={{
                                                    marginLeft: "5px",
                                                    padding: "5px 10px",
                                                    borderRadius: "5px",
                                                    backgroundColor: "#ddf",
                                                    border: "1px solid #99c",
                                                }}
                                                onClick={() => addToHand(book)}
                                            >
                                                📚 追加
                                            </button>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>

                        {/* ページネーション */}
                        {books.length > 0 && (
                            <div style={{ marginTop: "20px", textAlign: "center" }}>
                                <button
                                    onClick={() => searchBooks(page - 1)}
                                    disabled={page <= 1}
                                    style={{ marginRight: "10px" }}
                                >
                                    前へ
                                </button>
                                <span>{page} / {totalPages}</span>
                                <button
                                    onClick={() => searchBooks(page + 1)}
                                    disabled={page >= totalPages}
                                    style={{ marginLeft: "10px" }}
                                >
                                    次へ
                                </button>
                            </div>
                        )}
                    </>
                )}
        </div>
        </Layout>
    );
}

export default Search;
