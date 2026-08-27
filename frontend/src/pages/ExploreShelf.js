// 「他の参加者の本棚を観察する」個別画面の中身（BrowseLayout の子ルート
// /Browse/:participantId）。
//
// 見出し（パンくず）・表示切り替え・サイズ調整は親の BrowseLayout が持ち、
// Outlet 経由で viewMode/shelfWidthPct を受け取る。ここでは中央=本棚
// （読み取り専用）、左=差異対話、右=本詳細（読み取り専用）の3ペインだけを描く。
// 自分のIDは一切変えず、対象の participantId のデータだけを
// withParticipant() 経由で読む。
//
// カードから遷移してきた場合（cardOrigin）は、この3ペイン自体を
// クリックされたカードの位置・サイズから実サイズへ拡大させる
// （FLIPテクニック）。偽のカードを重ねてフェードで入れ替える方式だと
// 「拡大したカードと本棚が連動していない」違和感が出たため、本棚そのものを
// 動かして"カードが本棚に育つ"ように見せる。
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { getParticipantId } from "../utils/participant";
import ReadOnlyBookGrid from "../components/explore/ReadOnlyBookGrid";
import ReadOnlySpineShelf from "../components/explore/ReadOnlySpineShelf";
import ReadOnlyBookFocusPanel from "../components/explore/ReadOnlyBookFocusPanel";
import ComparisonDialoguePanel from "../components/explore/ComparisonDialoguePanel";

const DIALOGUE_WIDTH_PCT = 28;
const PANEL_WIDTH_PCT = 25;
const FLIP_MS = 340;

export default function ExploreShelf() {
  const { participantId } = useParams();
  const navigate = useNavigate();
  const myId = getParticipantId();
  const { viewMode, shelfWidthPct, cardOrigin, clearCardOrigin } = useOutletContext();
  const [focusIsbn, setFocusIsbn] = useState(null);
  const containerRef = useRef(null);

  // 自分自身のIDが指定された場合は観察の対象にならないため差し戻す
  // （自分の棚はMy本棚から見る導線と分離する）。
  useEffect(() => {
    if (participantId === myId) navigate("/Browse", { replace: true });
  }, [participantId, myId, navigate]);

  // null = 通常表示。値ありなら「まだ縮小した状態」を描画中で、次のフレームで
  // 恒等変換に切り替えてCSSトランジションを走らせる。
  const [flipTransform, setFlipTransform] = useState(null);

  useLayoutEffect(() => {
    setFocusIsbn(null);

    if (!cardOrigin || !containerRef.current) {
      setFlipTransform(null);
      return;
    }

    const toRect = containerRef.current.getBoundingClientRect();
    const scaleX = cardOrigin.width / toRect.width;
    const scaleY = cardOrigin.height / toRect.height;
    // 中心同士のズレを求める（transform-origin: center が既定のため）
    const dx = (cardOrigin.left + cardOrigin.width / 2) - (toRect.left + toRect.width / 2);
    const dy = (cardOrigin.top + cardOrigin.height / 2) - (toRect.top + toRect.height / 2);

    // まずカードだった頃の位置・大きさに一致させる（トランジション無し）
    setFlipTransform({ x: dx, y: dy, sx: scaleX, sy: scaleY, animate: false });
    clearCardOrigin();

    // 1フレーム後に恒等変換へ戻し、そこでトランジションを効かせる。
    // これで「カードが実サイズへ育つ」動きになる。
    const raf1 = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setFlipTransform({ x: 0, y: 0, sx: 1, sy: 1, animate: true });
      });
    });
    return () => cancelAnimationFrame(raf1);
    // participantId が変わるたびに（別のカードから来た場合）測り直す
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participantId]);

  const gridStyle = flipTransform
    ? {
        ...s.grid,
        transform: `translate(${flipTransform.x}px, ${flipTransform.y}px) scale(${flipTransform.sx}, ${flipTransform.sy})`,
        transition: flipTransform.animate ? `transform ${FLIP_MS}ms cubic-bezier(0.16, 1, 0.3, 1)` : "none",
      }
    : s.grid;

  if (participantId === myId) return null;

  return (
    <div ref={containerRef} style={gridStyle}>
      <div style={s.dialogueWrap}>
        <ComparisonDialoguePanel otherId={participantId} />
      </div>

      <main style={{ ...s.shelfPane, flexBasis: `${shelfWidthPct}%` }}>
        {viewMode === "spine" ? (
          <ReadOnlySpineShelf participantId={participantId} focusIsbn={focusIsbn} onFocus={setFocusIsbn} />
        ) : (
          <ReadOnlyBookGrid participantId={participantId} focusIsbn={focusIsbn} onFocus={setFocusIsbn} />
        )}
      </main>

      <div style={{ ...s.panelWrap, width: focusIsbn ? `${PANEL_WIDTH_PCT}%` : 0 }}>
        <ReadOnlyBookFocusPanel
          participantId={participantId}
          isbn={focusIsbn}
          onClose={() => setFocusIsbn(null)}
        />
      </div>
    </div>
  );
}

const s = {
  grid: {
    display: "flex",
    justifyContent: "center",
    height: "100%",
    boxSizing: "border-box",
    padding: "0 28px 20px",
    transformOrigin: "center center",
  },
  dialogueWrap: {
    flex: `0 0 ${DIALOGUE_WIDTH_PCT}%`,
    height: "100%", overflow: "hidden",
  },
  shelfPane: {
    flex: "0 0 auto", minWidth: 0, height: "100%",
    overflowY: "auto", boxSizing: "border-box",
    padding: "0 0 0 20px",
    transition: "flex-basis 240ms ease",
  },
  panelWrap: {
    flex: "0 0 auto", height: "100%", overflow: "hidden",
    transition: "width 240ms ease",
  },
};
