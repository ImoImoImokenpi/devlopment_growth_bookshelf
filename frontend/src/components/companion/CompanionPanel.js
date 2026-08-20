// 2ペイン構成の右ペイン（設計書6.1「右（サブ）：本詳細」）。
//
// 右ペインは「本詳細」専用。本棚で1冊タップすると、その本がハイライトされ、
// ここに詳細が表示される。
import BookFocusPanel from "./BookFocusPanel";

export default function CompanionPanel() {
  return (
    <aside style={s.panel}>
      <BookFocusPanel />
    </aside>
  );
}

const s = {
  // 右ペインはここ1箇所だけがスクロールする。
  // 中の各セクションに個別のスクロールを持たせると、途中に短いスクロール領域が
  // 挟まって、どこを転がしているのか分からなくなる。
  panel: {
    display: "flex", flexDirection: "column",
    width: "100%",
    background: "#fdfcf8", borderLeft: "1px solid #ede8da",
    height: "100%", overflowY: "auto", overflowX: "hidden",
  },
};
