import { useState } from "react";
import axios from "axios";

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);

  const searchBooks = async () => {
    const res = await axios.get(`https://www.googleapis.com/books/v1/volumes?q=${query}`);
    setResults(res.data.items || []);
  };

  const addBook = async (book) => {
    await axios.post("http://localhost:8000/add_book", {
      title: book.volumeInfo.title,
      authors: book.volumeInfo.authors,
      description: book.volumeInfo.description,
    });
  };

  return (
    <div style={{ padding: 20 }}>
      <h1>Google Books 検索</h1>

      <input
        placeholder="本のタイトルを検索"
        onChange={(e)=>setQuery(e.target.value)}
      />
      <button onClick={searchBooks}>検索</button>

      <div>
        {results.map((b) => (
          <div key={b.id} style={{border: "1px solid #ddd", padding: "10px", margin: "10px"}}>
            <h3>{b.volumeInfo.title}</h3>
            <p>{b.volumeInfo.authors?.join(", ")}</p>
            <button onClick={()=>addBook(b)}>本棚に追加</button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
