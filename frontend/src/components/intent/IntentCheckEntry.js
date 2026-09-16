// Home画面のヘッダに置く、フェーズ2 (a)(b) への入口。
//
// (a) 優先度質問はモーダルで答える。答え終わったら、そのまま実際の本棚を
// 「区切り確認モード」に切り替える（(b)はモーダル内の再現ではなく、
// 本物の本棚の上で直接タップする方式 — Home.js / SpineShelfView.js 参照）。
// (a)に答え済みの場合は、モーダルを経由せずボタンから直接そのモードに入れる。
import { useEffect, useState } from "react";
import IntentCheckModal from "./IntentCheckModal";
import { useShelfWorkspace } from "../../context/ShelfWorkspaceContext";
import { getParticipantId } from "../../utils/participant";

const API = "http://localhost:8000";
const AUTO_OPEN_MIN_BOOKS = 5;

function dismissedKey(pid) {
  return `growth_bookshelf.intent_modal_dismissed.${pid}`;
}

export default function IntentCheckEntry() {
  const { mode, setMode } = useShelfWorkspace();
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState(false);
  const [answered, setAnswered] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const pid = getParticipantId();
    let dismissed = false;
    try { dismissed = localStorage.getItem(dismissedKey(pid)) === "1"; } catch { /* noop */ }

    fetch(`${API}/intent-survey/priority`)
      .then(r => r.json())
      .then(priority => {
        if (cancelled) return;
        setAnswered(!!priority.answered);
        if (dismissed || priority.answered) return;
        return fetch(`${API}/knowledge_graph/growth`).then(r => r.json()).then(growth => {
          if (!cancelled && (growth.books || 0) >= AUTO_OPEN_MIN_BOOKS) setOpen(true);
        });
      })
      .catch(err => console.error(err))
      .finally(() => { if (!cancelled) setChecked(true); });

    return () => { cancelled = true; };
  }, []);

  const closeModal = () => {
    setOpen(false);
    try { localStorage.setItem(dismissedKey(getParticipantId()), "1"); } catch { /* noop */ }
  };

  const handleAnswered = () => {
    setAnswered(true);
    setMode("boundary");
  };

  const handleButtonClick = () => {
    if (answered) {
      setMode(mode === "boundary" ? "normal" : "boundary");
    } else {
      setOpen(true);
    }
  };

  return (
    <>
      <button
        style={{ ...s.btn, ...(mode === "boundary" ? s.btnActive : {}) }}
        onClick={handleButtonClick}
        title={answered ? "本棚の上で区切りを確認する" : "本棚を並べるときの意識について答える"}
      >
        {mode === "boundary" ? "区切り確認中" : "配置について"}
      </button>
      {checked && <IntentCheckModal open={open} onClose={closeModal} onAnswered={handleAnswered} />}
    </>
  );
}

const s = {
  btn: {
    padding: "6px 12px", borderRadius: 999, border: "1px solid #e5ded0",
    background: "#fff", color: "#8a7960", fontSize: 12, cursor: "pointer",
  },
  btnActive: { background: "#c9a84c", color: "#fff", borderColor: "#c9a84c" },
};
