// 感想記入。新UI/旧UIで機能を揃えるための共通コンポーネント。
import { useEffect, useState } from "react";
import { uiabGet, uiabPost } from "../../utils/uiabIdentity";

export default function UiabImpressionEditor({ period, isbn, title }) {
  const [text, setText] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isbn) return;
    setSaved(false);
    uiabGet(`/uiab/${period}/impression/${isbn}`)
      .then(data => setText(data.text || ""))
      .catch(err => console.error(err));
  }, [period, isbn]);

  if (!isbn) return null;

  const save = async () => {
    setSaving(true);
    try {
      await uiabPost(`/uiab/${period}/impression/${isbn}`, { text });
      setSaved(true);
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={s.wrap}>
      <div style={s.heading}>感想「{title}」</div>
      <textarea
        style={s.textarea}
        value={text}
        onChange={e => { setText(e.target.value); setSaved(false); }}
        placeholder="読んで感じたことを書いてください"
      />
      <div style={s.row}>
        {saved && <span style={s.savedHint}>保存しました</span>}
        <button style={s.saveBtn} onClick={save} disabled={saving}>{saving ? "保存中…" : "保存"}</button>
      </div>
    </div>
  );
}

const s = {
  wrap: { display: "flex", flexDirection: "column", gap: 6 },
  heading: { fontSize: 10.5, fontWeight: 700, color: "#c9a84c", textTransform: "uppercase", letterSpacing: "0.05em" },
  textarea: {
    minHeight: 64, padding: 9, borderRadius: 8, border: "1px solid #e5ded0",
    fontSize: 12, lineHeight: 1.6, fontFamily: "inherit", resize: "vertical",
  },
  row: { display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8 },
  savedHint: { fontSize: 10.5, color: "#7ab893" },
  saveBtn: {
    padding: "6px 14px", background: "#c9a84c", color: "#fff", border: "none",
    borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: "pointer",
  },
};
