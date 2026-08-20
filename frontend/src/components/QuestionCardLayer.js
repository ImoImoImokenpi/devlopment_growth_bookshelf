// 本棚に埋め込む発見バッジ＋質問カード（設計書6.2）。
//
// 発見は自動生成されてもすぐには吹き出しを出さない。対象の本の背表紙に
// 小さな「！」マークだけを付け、棚を眺めているだけでは静かなままにする。
// マークを押した（＝開いた）ときだけ、その場に質問カードが開いて
// 回答したり「もっと話す」で左ペインの対話に引き継いだりできる。
//
// 複数冊にまたがる発見の場合は related_book_ids の先頭の本を代表として
// マークを付ける（総当たりで全冊に付けると棚が「！」だらけになるため）。
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useShelfWorkspace } from "../context/ShelfWorkspaceContext";
import DiscoveryResponse from "./companion/DiscoveryResponse";

const CARD_WIDTH = 260;
const GAP = 14; // 背表紙の上端とカード／マークの間隔

export default function QuestionCardLayer() {
  const {
    pendingDiscoveries, answerDiscovery,
    setHighlightIsbns, setChatSeed, setIsDialogueOpen,
  } = useShelfWorkspace();

  const [openIsbn, setOpenIsbn] = useState(null);
  const [anchors, setAnchors] = useState({}); // { [isbn]: {cx, top} }

  // 本ごとに未回答の発見をまとめる（代表の本が同じなら古い順にキューする）
  const pendingByIsbn = useMemo(() => {
    const map = new Map();
    for (const d of pendingDiscoveries) {
      const isbn = d.related_book_ids?.[0];
      if (!isbn) continue;
      if (!map.has(isbn)) map.set(isbn, []);
      map.get(isbn).push(d);
    }
    return map;
  }, [pendingDiscoveries]);

  const badgeIsbns = useMemo(() => [...pendingByIsbn.keys()], [pendingByIsbn]);

  const measure = useCallback(() => {
    setAnchors(prev => {
      const next = {};
      for (const isbn of badgeIsbns) {
        const el = document.getElementById(`spine-${isbn}`);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        next[isbn] = { cx: r.left + r.width / 2, top: r.top };
      }
      return next;
    });
  }, [badgeIsbns]);

  useLayoutEffect(() => { measure(); }, [measure]);

  useEffect(() => {
    if (badgeIsbns.length === 0) return;
    // 棚のスクロール・リサイズ・並べ替えで背表紙が動くので追従させる
    const onChange = () => measure();
    window.addEventListener("resize", onChange);
    window.addEventListener("scroll", onChange, true);
    const timer = setInterval(onChange, 500);
    return () => {
      window.removeEventListener("resize", onChange);
      window.removeEventListener("scroll", onChange, true);
      clearInterval(timer);
    };
  }, [badgeIsbns, measure]);

  // 開いていた本の発見がすべて回答済みになったら、カードは自動で閉じる
  useEffect(() => {
    if (openIsbn && !pendingByIsbn.has(openIsbn)) setOpenIsbn(null);
  }, [openIsbn, pendingByIsbn]);

  const target = openIsbn ? pendingByIsbn.get(openIsbn)?.[0] : null;

  // カードが開いている間は、対象の本を棚側でも光らせる
  useEffect(() => {
    if (!target) return;
    setHighlightIsbns(target.related_book_ids || []);
    return () => setHighlightIsbns([]);
  }, [target, setHighlightIsbns]);

  const close = () => setOpenIsbn(null);

  let card = null;
  if (target && anchors[openIsbn]) {
    const anchor = anchors[openIsbn];
    const left = Math.min(
      Math.max(anchor.cx - CARD_WIDTH / 2, 12),
      window.innerWidth - CARD_WIDTH - 12
    );
    const tailOffset = Math.min(Math.max(anchor.cx - left, 20), CARD_WIDTH - 20);
    const showBelow = anchor.top < 190; // 上に置くと画面外に出る場合は下に回す

    card = (
      <div
        style={{
          ...s.card,
          left,
          ...(showBelow
            ? { top: anchor.top + GAP + 60 }
            : { top: Math.max(anchor.top - GAP - 150, 12) }),
        }}
      >
        <div style={s.head}>
          <span style={s.mark}>棚からの問いかけ</span>
          <button style={s.close} onClick={close} title="閉じる">✕</button>
        </div>

        <div style={s.question}>{target.generated_question}</div>

        <DiscoveryResponse
          discovery={target}
          compact
          onAnswer={(id, status, extra) => {
            answerDiscovery(id, status, extra);
            // 「一部ちがう」は訂正コメントの入力が続くので、確定するまで閉じない
            if (status !== "modified" || extra.comment) close();
          }}
          onTalkMore={() => {
            setChatSeed({
              question: target.generated_question,
              isbns: target.related_book_ids || [],
            });
            setIsDialogueOpen(true);
            close();
          }}
        />

        {/* 対象の本へ伸びる吹き出しの尻尾 */}
        <div
          style={{
            ...s.tail,
            left: tailOffset - 7,
            ...(showBelow
              ? { top: -7, borderBottom: "none", borderRight: "none" }
              : { bottom: -7, borderTop: "none", borderLeft: "none" }),
          }}
        />
      </div>
    );
  }

  return (
    <>
      {badgeIsbns.map(isbn => {
        const anchor = anchors[isbn];
        if (!anchor || isbn === openIsbn) return null;
        return (
          <button
            key={isbn}
            style={{ ...s.badge, left: anchor.cx - 11, top: anchor.top - 22 }}
            onClick={() => setOpenIsbn(isbn)}
            title="棚が何かに気づいたようです。押すと開きます"
          >
            !
          </button>
        );
      })}
      {card}
    </>
  );
}

const s = {
  badge: {
    position: "fixed", zIndex: 2400,
    width: 22, height: 22, borderRadius: "50%",
    display: "flex", alignItems: "center", justifyContent: "center",
    background: "#c9a84c", color: "#fff",
    border: "2px solid #fffdf7", boxShadow: "0 2px 10px rgba(60,45,20,0.4)",
    fontSize: 12, fontWeight: 800, lineHeight: 1,
    cursor: "pointer", padding: 0,
  },
  card: {
    position: "fixed", width: CARD_WIDTH, zIndex: 2500,
    background: "#fffdf7", border: "1px solid #e8dcb8", borderRadius: 14,
    boxShadow: "0 10px 34px rgba(60,45,20,0.18)",
    padding: "11px 13px 12px",
    display: "flex", flexDirection: "column", gap: 9,
  },
  head: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  mark: {
    fontSize: 9, fontWeight: 700, color: "#c9a84c",
    letterSpacing: "0.1em", textTransform: "uppercase",
  },
  close: {
    width: 18, height: 18, borderRadius: "50%", border: "none",
    background: "transparent", color: "#c4b8a2", cursor: "pointer",
    fontSize: 11, lineHeight: 1, padding: 0,
  },
  question: { fontSize: 12.5, fontWeight: 600, color: "#2a1f0e", lineHeight: 1.65 },
  tail: {
    position: "absolute", width: 13, height: 13,
    background: "#fffdf7", border: "1px solid #e8dcb8",
    transform: "rotate(45deg)",
  },
};
