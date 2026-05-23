import { useState, useRef, useEffect, useCallback } from "react";
import axios from "axios";

const API = "http://localhost:8000";

export default function Register() {
  const [imageFile, setImageFile]   = useState(null);   // File オブジェクト（保存時に使う）
  const [preview,   setPreview]     = useState(null);   // プレビューURL
  const [dragging,  setDragging]    = useState(false);
  const [isbnInput, setIsbnInput]   = useState("");
  const [extracting, setExtracting] = useState(false);  // Gemini 処理中
  const [searching,  setSearching]  = useState(false);  // NDL 検索中
  const [saving,     setSaving]     = useState(false);
  const [result,     setResult]     = useState(null);   // NDL 書誌情報
  const [error,      setError]      = useState(null);
  const [saved,      setSaved]      = useState(false);
  const [bookList,   setBookList]   = useState([]);
  const inputRef = useRef();

  const fetchList = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/register/list`);
      setBookList(res.data);
    } catch {}
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  // ── 画像選択 ──────────────────────────────────────
  const handleFile = (file) => {
    if (!file) return;
    setImageFile(file);
    setPreview(URL.createObjectURL(file));
    setResult(null);
    setError(null);
    setSaved(false);
  };

  // ── Gemini でISBN自動抽出 ─────────────────────────
  const handleExtract = async () => {
    if (!imageFile) return setError("先に画像をアップロードしてください");
    setError(null);
    setExtracting(true);
    const formData = new FormData();
    formData.append("file", imageFile);
    try {
      const res = await axios.post(`${API}/register/extract-isbn`, formData);
      setIsbnInput(res.data.isbn);
      if (res.data.book) {
        setResult(res.data.book);  // OCR+NDL で書誌情報まで取得できた場合はそのまま表示
      }
    } catch (err) {
      setError(err.response?.data?.detail || "ISBN抽出に失敗しました");
    } finally {
      setExtracting(false);
    }
  };

  // ── NDL API で書誌情報を検索 ──────────────────────
  const handleSearch = async () => {
    const isbn = isbnInput.trim();
    if (!isbn) return setError("ISBNを入力してください");
    if (!imageFile) return setError("先に画像をアップロードしてください");
    setError(null);
    setResult(null);
    setSaved(false);
    setSearching(true);
    try {
      const res = await axios.get(`${API}/register/fetch/${isbn}`);
      setResult(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "書誌情報が見つかりませんでした");
    } finally {
      setSearching(false);
    }
  };

  // ── 画像 + 書誌情報を一緒に保存 ──────────────────
  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("book_data", JSON.stringify(result));
      if (imageFile) formData.append("image", imageFile);
      await axios.post(`${API}/register/save`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setSaved(true);
      fetchList();
    } catch (err) {
      setError(err.response?.data?.detail || "保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files[0]);
  };

  const rows = result
    ? [
        ["ISBN",    result.isbn],
        ["著者",    result.authors],
        ["出版社",  result.publisher],
        ["出版年",  result.published_year],
        ["NDC",     result.ndc_full],
        ["ページ数",result.pages],
        ["高さ",    result.height_mm ? `${result.height_mm} mm` : null],
      ].filter(([, v]) => v != null && v !== "")
    : [];

  return (
    <div style={s.page}>
      <h2 style={s.heading}>本を登録する</h2>
      <p style={s.sub}>背表紙の写真とISBNを紐づけて書誌情報を保存します</p>

      {/* ── STEP 1: 画像アップロード ── */}
      <div style={s.stepLabel}>① 背表紙の写真を選ぶ</div>
      <div
        style={{ ...s.drop, ...(dragging ? s.dropActive : {}) }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          style={{ display: "none" }}
          onChange={(e) => handleFile(e.target.files[0])}
        />
        {preview ? (
          <img src={preview} alt="preview" style={s.previewImg} />
        ) : (
          <div style={s.dropHint}>
            <span style={s.dropIcon}>📷</span>
            <span style={s.dropText}>ドロップ または クリックして画像を選択</span>
          </div>
        )}
      </div>
      {preview && (
        <button style={s.retryBtn} onClick={() => inputRef.current.click()}>
          別の画像を選ぶ
        </button>
      )}

      {/* ── STEP 2: ISBNを入力 or 自動抽出 ── */}
      <div style={{ ...s.stepLabel, marginTop: "24px" }}>② ISBNを入力する</div>
      <div style={s.isbnRow}>
        <input
          style={s.isbnInput}
          type="text"
          placeholder="例: 978-4-06-123456-7"
          value={isbnInput}
          onChange={(e) => setIsbnInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button
          style={{ ...s.btnOutline, ...(extracting ? s.btnDisabled : {}) }}
          onClick={handleExtract}
          disabled={extracting}
          title="Gemini APIで画像からISBNを自動抽出"
        >
          {extracting ? "抽出中…" : "自動抽出"}
        </button>
        <button
          style={{ ...s.btnPrimary, ...(searching ? s.btnDisabled : {}) }}
          onClick={handleSearch}
          disabled={searching}
        >
          {searching ? "検索中…" : "検索"}
        </button>
      </div>
      <p style={s.hint}>
        「自動抽出」は Gemini API でISBNを読み取ります（APIクォータが必要）。<br />
        ISBNが分かる場合は直接入力して「検索」してください。
      </p>

      {/* ── エラー ── */}
      {error && <div style={s.errorBox}>{error}</div>}

      {/* ── STEP 3: 書誌情報確認 + 保存 ── */}
      {result && (
        <div style={s.card}>
          <div style={s.stepLabel}>③ 内容を確認して保存</div>
          <div style={s.cardInner}>
            {/* 背表紙プレビュー */}
            {preview && (
              <img src={preview} alt="spine" style={s.cardSpine} />
            )}
            <div style={{ flex: 1 }}>
              <h3 style={s.cardTitle}>{result.title || "（タイトル不明）"}</h3>
              <table style={s.table}>
                <tbody>
                  {rows.map(([label, value]) => (
                    <tr key={label}>
                      <td style={s.tdLabel}>{label}</td>
                      <td style={s.tdValue}>{String(value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.description && (
                <p style={s.cardDesc}>{result.description}</p>
              )}
            </div>
          </div>
          {saved ? (
            <div style={s.savedBadge}>データベースに保存しました ✓</div>
          ) : (
            <button
              style={{ ...s.saveBtn, ...(saving ? s.btnDisabled : {}) }}
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "保存中…" : "背表紙と紐づけて保存"}
            </button>
          )}
        </div>
      )}
      {/* ── 登録済み一覧（最新5冊） ── */}
      {bookList.length > 0 && (
        <div style={s.listSection}>
          <div style={{ ...s.stepLabel, marginBottom: "16px" }}>
            最近の登録 ({Math.min(bookList.length, 5)} / {bookList.length}冊)
          </div>
          <div style={s.listGrid}>
            {[...bookList].reverse().slice(0, 5).map((b) => {
              const meta = [
                ["著者",    (b.authors || []).join(", ")],
                ["出版社",  b.publisher],
                ["出版年",  b.published_year],
                ["NDC",     b.ndc_full],
                ["ページ数",b.pages],
                ["高さ",    b.height_mm ? `${b.height_mm} mm` : null],
                ["ISBN",    b.isbn],
              ].filter(([, v]) => v != null && v !== "");
              return (
                <div key={b.isbn} style={s.listItem}>
                  <div style={s.listThumb}>
                    <img
                      src={b.spine_image || `${API}/register/cover/${b.isbn}`}
                      alt={b.title}
                      style={s.thumbImg}
                      onError={(e) => { e.target.style.display = "none"; }}
                    />
                  </div>
                  <div style={s.listInfo}>
                    <div style={s.listTitle}>{b.title || "（タイトル不明）"}</div>
                    <table style={s.metaTable}>
                      <tbody>
                        {meta.map(([label, value]) => (
                          <tr key={label}>
                            <td style={s.metaTdLabel}>{label}</td>
                            <td style={s.metaTdValue}>{String(value)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {b.description && (
                      <div style={s.listDesc}>{b.description}</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const s = {
  page: {
    padding: "60px 40px",
    minHeight: "100vh",
    backgroundColor: "#fdfcf8",
    maxWidth: "680px",
    margin: "0 auto",
  },
  heading: {
    fontSize: "24px",
    fontWeight: "700",
    color: "#2a1f0e",
    fontFamily: "serif",
    marginBottom: "6px",
  },
  sub: {
    fontSize: "13px",
    color: "#888",
    marginBottom: "24px",
  },
  stepLabel: {
    fontSize: "13px",
    fontWeight: "700",
    color: "#c9a84c",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    marginBottom: "10px",
  },
  drop: {
    border: "2px dashed #d0c4a8",
    borderRadius: "14px",
    padding: "32px",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    cursor: "pointer",
    backgroundColor: "#faf8f2",
    transition: "all 0.2s",
    minHeight: "40px",
  },
  dropActive: {
    borderColor: "#c9a84c",
    backgroundColor: "#fdf6e3",
  },
  dropHint: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "10px",
  },
  dropIcon: { fontSize: "32px" },
  dropText: { fontSize: "14px", color: "#999" },
  previewImg: {
    maxWidth: "100%",
    maxHeight: "220px",
    objectFit: "contain",
    borderRadius: "8px",
  },
  retryBtn: {
    marginTop: "8px",
    background: "none",
    border: "none",
    color: "#c9a84c",
    cursor: "pointer",
    fontSize: "13px",
    textDecoration: "underline",
    padding: 0,
  },
  isbnRow: {
    display: "flex",
    gap: "8px",
  },
  isbnInput: {
    flex: 1,
    padding: "11px 14px",
    borderRadius: "10px",
    border: "1px solid #d0c4a8",
    fontSize: "14px",
    backgroundColor: "#faf8f2",
    outline: "none",
  },
  btnPrimary: {
    padding: "11px 20px",
    backgroundColor: "#c9a84c",
    color: "#fff",
    border: "none",
    borderRadius: "10px",
    fontSize: "14px",
    fontWeight: "700",
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  btnOutline: {
    padding: "11px 16px",
    backgroundColor: "transparent",
    color: "#c9a84c",
    border: "1px solid #c9a84c",
    borderRadius: "10px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  btnDisabled: {
    opacity: 0.5,
    cursor: "not-allowed",
  },
  hint: {
    fontSize: "12px",
    color: "#aaa",
    marginTop: "8px",
    lineHeight: "1.6",
  },
  errorBox: {
    marginTop: "16px",
    padding: "12px 16px",
    backgroundColor: "#fff0f0",
    borderRadius: "10px",
    color: "#c94040",
    fontSize: "13px",
    border: "1px solid #f5c6c6",
  },
  card: {
    marginTop: "28px",
    padding: "24px",
    backgroundColor: "#fff",
    borderRadius: "14px",
    boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
    border: "1px solid #ede8da",
  },
  cardInner: {
    display: "flex",
    gap: "20px",
    alignItems: "flex-start",
    marginBottom: "20px",
  },
  cardSpine: {
    width: "70px",
    objectFit: "cover",
    borderRadius: "4px",
    flexShrink: 0,
    border: "1px solid #eee",
  },
  cardTitle: {
    fontSize: "16px",
    fontWeight: "700",
    color: "#2a1f0e",
    fontFamily: "serif",
    marginBottom: "12px",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "13px",
    marginBottom: "4px",
  },
  tdLabel: {
    width: "80px",
    padding: "5px 0",
    color: "#aaa",
    fontWeight: "600",
    verticalAlign: "top",
    borderBottom: "1px solid #f5f0e8",
  },
  tdValue: {
    padding: "5px 0 5px 10px",
    color: "#333",
    borderBottom: "1px solid #f5f0e8",
  },
  cardDesc: {
    marginTop: "12px",
    fontSize: "12px",
    color: "#666",
    lineHeight: "1.7",
    borderTop: "1px solid #f5f0e8",
    paddingTop: "10px",
  },
  saveBtn: {
    width: "100%",
    padding: "13px",
    backgroundColor: "#c9a84c",
    color: "#fff",
    border: "none",
    borderRadius: "10px",
    fontSize: "14px",
    fontWeight: "700",
    cursor: "pointer",
  },
  savedBadge: {
    textAlign: "center",
    padding: "13px",
    backgroundColor: "#e8f5e9",
    color: "#2e7d32",
    borderRadius: "10px",
    fontWeight: "600",
    fontSize: "14px",
  },
  listSection: {
    marginTop: "48px",
    paddingTop: "32px",
    borderTop: "1px solid #ede8da",
  },
  listGrid: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  listItem: {
    display: "flex",
    gap: "16px",
    alignItems: "flex-start",
    padding: "14px 16px",
    backgroundColor: "#fff",
    borderRadius: "12px",
    border: "1px solid #ede8da",
    boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
  },
  listThumb: {
    width: "30px",
    height: "100px",
    flexShrink: 0,
    borderRadius: "3px",
    overflow: "hidden",
    backgroundColor: "#f5f0e8",
    position: "relative",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  thumbImg: {
    position: "absolute",
    width: "90px",
    height: "20px",
    objectFit: "contain",
    top: "50%",
    left: "50%",
    transform: "translate(-50%, -50%) rotate(90deg)",
  },
  thumbPlaceholder: {
    fontSize: "22px",
  },
  listInfo: {
    flex: 1,
    minWidth: 0,
  },
  listTitle: {
    fontSize: "14px",
    fontWeight: "700",
    color: "#2a1f0e",
    fontFamily: "serif",
    marginBottom: "4px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  listMeta: {
    fontSize: "12px",
    color: "#888",
    marginBottom: "2px",
  },
  listIsbn: {
    fontSize: "11px",
    color: "#bbb",
    marginTop: "4px",
    fontFamily: "monospace",
  },
  listDesc: {
    fontSize: "11px",
    color: "#999",
    marginTop: "8px",
    lineHeight: "1.6",
    borderTop: "1px solid #f5f0e8",
    paddingTop: "8px",
  },
  metaTable: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "12px",
    marginTop: "6px",
  },
  metaTdLabel: {
    width: "72px",
    padding: "3px 0",
    color: "#aaa",
    fontWeight: "600",
    verticalAlign: "top",
  },
  metaTdValue: {
    padding: "3px 0 3px 8px",
    color: "#555",
  },
};
