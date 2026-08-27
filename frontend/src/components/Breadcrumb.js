// ページ見出し用の簡易パンくず（例:「実験準備 › ギャラリー」）。
// PageHeader の title に渡して使う。BrowseLayout.js の「みんなの本棚 › P01の
// 本棚」と同じ書体・色使いに揃えているが、あちらは遷移時のフェード演出付きの
// 専用実装なので、ここでは演出のない単純な版として別に持つ。
import { Link } from "react-router-dom";

// items: [{ label, to? }]  to があればリンク、無ければただのラベル
// （「実験準備」のように、そのもの自体のページが無い場合はリンクにしない）。
export default function Breadcrumb({ items }) {
  return (
    <nav style={s.wrap} aria-label="パンくずリスト">
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} style={s.item}>
            {i > 0 && <span style={s.sep}>›</span>}
            {item.to ? (
              <Link to={item.to} style={s.link}>{item.label}</Link>
            ) : (
              <span style={isLast ? s.current : s.parent}>{item.label}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

const s = {
  wrap: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  item: { display: "flex", alignItems: "center", gap: 8 },
  link: { fontSize: 20, fontWeight: 700, color: "#9a8b76", textDecoration: "none" },
  parent: { fontSize: 20, fontWeight: 700, color: "#9a8b76" },
  current: { fontSize: 20, fontWeight: 700, color: "#222" },
  sep: { fontSize: 17, color: "#c4b8a2" },
};
