// 「みんなの本棚」の共通シェル（ルート /Browse とその子 /Browse/:participantId）。
//
// 以前は一覧ページ(BrowseParticipants)と個別画面(ExploreShelf)が別々のページ
// コンポーネントで、遷移するたびに見出し・パンくずも含めて全部作り直されていた。
// ここでは見出し行を親レイアウトに1つだけ持たせ、子ルート（一覧 or 個別）だけを
// <Outlet/> で差し替える。これで「みんなの本棚」の文字はそのまま、その横に
// 「› P01の本棚」が生えるように見え、下の中身だけがそのまま入れ替わる。
//
// カードクリック時の「カードが本棚に育つ」演出は、偽のカードを重ねてから
// フェードで入れ替える方式（overlayトリック）だと本棚と動きが連動して
// 見えなかったため、クリックされたカードの位置・サイズを ExploreShelf 側に
// 渡し、本棚そのものをその場所・大きさから実サイズへ拡大させる
// （FLIPテクニック、詳細は ExploreShelf.js）。
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import ViewModeToggle from "../components/ViewModeToggle";
import ShelfSizeAdjuster from "../components/ShelfSizeAdjuster";
import PageHeader from "../components/PageHeader";

const NAVBAR_SPACE = 66;
const SHELF_WIDTH_DEFAULT = 40; // My本棚（ShelfWorkspaceContext）の初期値と揃える

export default function BrowseLayout() {
  const { participantId } = useParams();
  const navigate = useNavigate();

  // 表示切り替え・サイズ調整は個別画面でしか使わないが、見出し行に置くため
  // ここで持つ（Outlet経由で子に渡す）。参加者を切り替えても引き継がれる
  // （以前のExploreShelfのローカルstateと同じ挙動）。
  const [viewMode, setViewMode] = useState("spine");
  const [shelfWidthPct, setShelfWidthPct] = useState(SHELF_WIDTH_DEFAULT);

  // 一覧→個別への遷移をなめらかにする：パンくずの「› P01の本棚」と右側の
  // コントロールは、見出し行そのものはそのまま（アンマウントされない）で、
  // 生えてくる部分だけをふわっとフェード・インさせる。
  const [headerEntered, setHeaderEntered] = useState(false);
  const headerTimerRef = useRef(null);

  useEffect(() => {
    if (!participantId) {
      setHeaderEntered(false);
      return;
    }
    setHeaderEntered(false);
    clearTimeout(headerTimerRef.current);
    headerTimerRef.current = setTimeout(() => setHeaderEntered(true), 10);
    return () => clearTimeout(headerTimerRef.current);
  }, [participantId]);

  // クリックされたカードの位置・サイズ。ExploreShelf側がこれを読み、
  // 自分自身をその位置・サイズから実サイズへ拡大させたら消費して null に戻す
  // （clearCardOrigin）。カード経由でない遷移（戻る操作やURL直打ち）では
  // null のままなので、その場合は通常のフェードで表示される。
  const [cardOrigin, setCardOrigin] = useState(null);

  const beginCardTransition = useCallback((fromRect, targetParticipantId) => {
    setCardOrigin(fromRect);
    navigate(targetParticipantId);
  }, [navigate]);

  const clearCardOrigin = useCallback(() => setCardOrigin(null), []);

  return (
    <div style={s.page}>
      <div style={s.headerRow}>
        <PageHeader
          title={
            <nav style={s.breadcrumb} aria-label="パンくずリスト">
              {participantId ? (
                <Link to="/Browse" style={s.breadcrumbLink}>みんなの本棚</Link>
              ) : (
                <span style={s.breadcrumbRoot}>みんなの本棚</span>
              )}
              {participantId && (
                <span
                  style={{
                    ...s.breadcrumbTail,
                    opacity: headerEntered ? 1 : 0,
                    transform: headerEntered ? "translateX(0)" : "translateX(-6px)",
                  }}
                >
                  <span style={s.breadcrumbSep}>›</span>
                  <span style={s.breadcrumbCurrent}>{participantId}の本棚</span>
                  <span style={s.readonlyTag}>読み取り専用</span>
                </span>
              )}
            </nav>
          }
          sub={!participantId
            ? "他の参加者の本棚を自由に見て回れます（読み取り専用）。気になる本棚を選ぶと、自分の本棚との違いについて対話できます。"
            : undefined}
          right={participantId ? (
            <div
              style={{
                ...s.headerControls,
                opacity: headerEntered ? 1 : 0,
                transform: headerEntered ? "translateY(0)" : "translateY(-4px)",
                transitionDelay: headerEntered ? "60ms" : "0ms",
              }}
            >
              <ShelfSizeAdjuster value={shelfWidthPct} onChange={setShelfWidthPct} />
              <ViewModeToggle mode={viewMode} onChange={setViewMode} />
            </div>
          ) : undefined}
        />
      </div>

      <div style={s.body}>
        <Outlet context={{ viewMode, shelfWidthPct, cardOrigin, clearCardOrigin, beginCardTransition }} />
      </div>
    </div>
  );
}

const s = {
  page: {
    height: "100vh", paddingTop: NAVBAR_SPACE, boxSizing: "border-box",
    display: "flex", flexDirection: "column",
    background: "#f7f3ea", overflow: "hidden",
  },
  headerRow: { flexShrink: 0, padding: "20px 28px 12px" },
  headerControls: {
    display: "flex", alignItems: "center", gap: 14,
    transition: "opacity 220ms ease, transform 220ms ease",
  },
  breadcrumb: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  breadcrumbRoot: { fontSize: 20, fontWeight: 700, color: "#222" },
  breadcrumbLink: { fontSize: 20, fontWeight: 700, color: "#9a8b76", textDecoration: "none" },
  breadcrumbTail: {
    display: "flex", alignItems: "center", gap: 8,
    transition: "opacity 220ms ease, transform 220ms ease",
  },
  breadcrumbSep: { fontSize: 17, color: "#c4b8a2" },
  breadcrumbCurrent: { fontSize: 20, fontWeight: 700, color: "#222" },
  readonlyTag: {
    fontSize: 10.5, fontWeight: 700, color: "#8a5a1f", background: "#fdeecb",
    borderRadius: 999, padding: "3px 10px", marginLeft: 4,
  },
  body: { flex: 1, minHeight: 0, overflow: "hidden", position: "relative" },
};
