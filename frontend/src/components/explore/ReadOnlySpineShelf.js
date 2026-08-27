// 「他の参加者の本棚を観察する」画面の「背表紙表示」モード（デフォルト）。
//
// 以前はCSS(flexbox)による簡易再現だったが、「ありのままの並び替え」を
// 見せるため、SpineShelfView.js と同じ座標計算（x_pos/shelf_index を
// そのままpxに変換、本の高さ・厚みの算出式、背表紙の配色ハッシュ）で
// 実際の配置を1px単位で再現する。ドラッグ配置・段の増減・意味づけ入力
// など書き込み系のD3操作は一切持たず、クリックで右ペインに詳細
// （読み取り専用）を開く以外の操作はできない。
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import { withParticipant } from "../../utils/participant";

const API = "http://localhost:8000";

// ── SpineShelfView.js と揃える定数・計算式 ─────────────────────────
const TOP_GAP         = 40;
const FRAME           = 20;
const SHELF_PAD       = 0;
const WOOD_URL        = "/sources/wood_texture.jpg";
const DARK_WOOD_URL   = "/sources/dark_wood_texture.jpg";
const MAX_BOOK_HEIGHT = 250;
const PX_TO_MM_SCALE  = 1.2;

const SPINE_PALETTES = [
  { bg: "#1a1a2e", text: "#e8d5a3", accent: "#c9a84c" },
  { bg: "#2d1b33", text: "#f0e6d3", accent: "#d4a0c0" },
  { bg: "#0d2137", text: "#cce5f0", accent: "#5ba3c9" },
  { bg: "#1e3a2f", text: "#d4edd8", accent: "#7ab893" },
  { bg: "#3b1f0e", text: "#f5dfc5", accent: "#d4823a" },
  { bg: "#2a2a2a", text: "#e8e8e8", accent: "#ff6b35" },
  { bg: "#1f2d3d", text: "#d8e4ec", accent: "#4a9eca" },
  { bg: "#3d1f1f", text: "#f5d5d5", accent: "#c9506a" },
  { bg: "#2d2d1a", text: "#eeeeda", accent: "#c8b84a" },
  { bg: "#1a2d2d", text: "#d5eeed", accent: "#4abcb8" },
  { bg: "#f5f0e8", text: "#2a2018", accent: "#8b4513" },
  { bg: "#eef5f0", text: "#1a2d22", accent: "#2d7a4a" },
  { bg: "#f5eef5", text: "#2a1a2a", accent: "#7a2d8b" },
  { bg: "#f0f5ee", text: "#1e2a1a", accent: "#4a8b2d" },
];

function hashCode(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}
function getPalette(isbn) {
  return SPINE_PALETTES[hashCode(isbn || "") % SPINE_PALETTES.length];
}
function resolveSpineHeight(book) {
  return Math.min(1000, Math.max(10, book.height_mm * 1.2));
}
function resolveSpineWidth(book) {
  return book?.pages ? Math.min(100, Math.max(1, book.pages * 0.08)) : 20;
}

export default function ReadOnlySpineShelf({ participantId, focusIsbn, onFocus }) {
  const [bookshelf, setBookshelf] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const svgRef = useRef();

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    fetch(`${API}/bookshelf/`, withParticipant(participantId))
      .then(res => (res.ok ? res.json() : Promise.reject(new Error("本棚を読み込めませんでした"))))
      .then(json => { if (!cancelled) setBookshelf(json); })
      .catch(err => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [participantId]);

  const shelves = useMemo(() => bookshelf?.shelves || [], [bookshelf]);
  const shelfCount = bookshelf?.total_shelves || 1;
  const books = useMemo(() => shelves.flatMap(s => s.books), [shelves]);
  const hasBooks = books.length > 0;

  const unitShelfHeight = TOP_GAP + MAX_BOOK_HEIGHT + SHELF_PAD;

  const booksWithPosition = useMemo(() => {
    return books.map(book => {
      const shelfIdx = book.shelf_index ?? 0;
      const xPosMM = book.x_pos ?? 0;
      return {
        ...book,
        gridRow: shelfIdx,
        x: xPosMM * PX_TO_MM_SCALE + FRAME,
        y: FRAME + shelfIdx * (unitShelfHeight + FRAME) + TOP_GAP,
      };
    });
  }, [books, unitShelfHeight]);

  const WIDTH = useMemo(() => {
    const maxWidth = d3.max(
      shelves.map(s => {
        const total = (s.books || []).reduce((sum, b) => sum + resolveSpineWidth(b), 0);
        return total + FRAME * 2;
      })
    );
    return Math.min(Math.max(maxWidth || 400, 400), 1200);
  }, [shelves]);

  const HEIGHT = unitShelfHeight * shelfCount + FRAME * (shelfCount + 1);

  useEffect(() => {
    if (!svgRef.current || !hasBooks) return;
    const svg = d3.select(svgRef.current)
      .attr("width", "100%")
      .attr("height", "100%")
      .attr("viewBox", `0 0 ${WIDTH} ${HEIGHT}`)
      .attr("preserveAspectRatio", "xMidYMid meet");

    let staticLayer = svg.select(".static-layer");
    if (staticLayer.empty()) {
      staticLayer = svg.append("g").attr("class", "static-layer");
      const defs = svg.append("defs");

      const mkPattern = (id, url, size) => {
        defs.append("pattern").attr("id", id).attr("patternUnits", "userSpaceOnUse").attr("width", size).attr("height", size)
          .append("image").attr("href", url).attr("width", size).attr("height", size).attr("preserveAspectRatio", "xMidYMid slice");
      };
      mkPattern("roWoodPat", WOOD_URL, 300);
      mkPattern("roDarkWoodPat", DARK_WOOD_URL, 500);

      defs.append("filter").attr("id", "roBookShadow").attr("x", "-20%").attr("y", "-10%").attr("width", "140%").attr("height", "130%")
        .append("feDropShadow").attr("dx", 3).attr("dy", 4).attr("stdDeviation", 3).attr("flood-color", "rgba(0,0,0,0.5)");
    }

    staticLayer.selectAll("*").remove();
    staticLayer.append("rect").attr("width", WIDTH).attr("height", HEIGHT).attr("fill", "url(#roDarkWoodPat)");
    staticLayer.append("rect").attr("width", WIDTH).attr("height", HEIGHT).attr("fill", "rgba(0,0,0,0.25)");

    for (let i = 0; i <= shelfCount; i++) {
      const y = i * (unitShelfHeight + FRAME);
      staticLayer.append("rect").attr("x", 0).attr("y", y).attr("width", WIDTH).attr("height", FRAME).attr("fill", "url(#roWoodPat)");
    }
    [0, WIDTH - FRAME].forEach(x => {
      staticLayer.append("rect").attr("x", x).attr("y", 0).attr("width", FRAME).attr("height", HEIGHT).attr("fill", "url(#roWoodPat)");
    });

    const bookGroups = svg.selectAll(".ro-spine-book")
      .data(booksWithPosition, d => d.isbn)
      .join(
        enter => enter.append("g")
          .attr("class", "ro-spine-book")
          .attr("id", d => `ro-spine-${d.isbn}`)
          .attr("transform", d => `translate(${d.x}, ${d.y})`)
          .style("cursor", "pointer")
          .on("click", (_e, d) => onFocus?.(d.isbn)),
        update => update.attr("transform", d => `translate(${d.x}, ${d.y})`),
        exit => exit.remove()
      );

    bookGroups.each(function(d) {
      const g = d3.select(this);
      if (g.select("rect").empty()) {
        const p = getPalette(d.isbn);
        const sw = resolveSpineWidth(d);
        const sh = resolveSpineHeight(d);
        const offset = MAX_BOOK_HEIGHT - sh;

        g.append("rect").attr("y", offset).attr("width", sw).attr("height", sh).attr("rx", 2).attr("fill", p.bg).attr("filter", "url(#roBookShadow)");

        if (d.spine_image) {
          const fo = g.append("foreignObject").attr("y", offset).attr("width", sw).attr("height", sh);
          fo.append("xhtml:div")
            .attr("style", `width:${sw}px; height:${sh}px; overflow:hidden; position:relative; border-radius:2px;`)
            .append("xhtml:img")
            .attr("src", d.spine_image)
            .attr("style", `position:absolute; width:${sh}px; height:${sw}px; object-fit:fill; top:50%; left:50%; transform:translate(-50%,-50%) rotate(90deg);`);
        } else {
          g.append("rect").attr("y", offset).attr("width", sw).attr("height", 4).attr("fill", p.accent).attr("opacity", 0.6);
          g.append("rect").attr("y", offset + sh - 4).attr("width", sw).attr("height", 4).attr("fill", p.accent).attr("opacity", 0.6);

          const fo = g.append("foreignObject").attr("y", offset + 10).attr("width", sw).attr("height", sh - 20);
          const div = fo.append("xhtml:div").attr("style", `color:${p.text}; font-size:10px; writing-mode:vertical-rl; padding:4px; height:100%; display:flex; align-items:center; font-family:serif; font-weight:600; overflow:hidden;`);
          div.text(d.title);
        }
      }
    });

    svg.selectAll(".ro-spine-hl").remove();
    if (focusIsbn) {
      const b = booksWithPosition.find(x => x.isbn === focusIsbn);
      if (b) {
        const top = b.y + (MAX_BOOK_HEIGHT - resolveSpineHeight(b));
        svg.append("rect").attr("class", "ro-spine-hl")
          .attr("x", b.x - 3).attr("y", top - 3)
          .attr("width", resolveSpineWidth(b) + 6).attr("height", resolveSpineHeight(b) + 6)
          .attr("fill", "none").attr("stroke", "#ff9d3d").attr("stroke-width", 2).attr("rx", 5)
          .style("filter", "drop-shadow(0 0 4px #ff9d3d99)")
          .style("pointer-events", "none");
      }
    }
  }, [booksWithPosition, WIDTH, HEIGHT, shelfCount, unitShelfHeight, focusIsbn, hasBooks, onFocus]);

  if (isLoading) return <p style={s.status}>読み込み中…</p>;
  if (error) return <p style={s.statusError}>{error}</p>;
  if (!hasBooks) return <p style={s.empty}>この参加者の本棚にはまだ本がありません。</p>;

  return (
    <div style={s.container}>
      <svg ref={svgRef} style={{ width: "100%", height: "auto", display: "block" }} />
    </div>
  );
}

const s = {
  status: { color: "#888", fontSize: 14 },
  statusError: { color: "#c9506a", fontSize: 14 },
  empty: { color: "#888", fontSize: 14 },
  container: { width: "100%" },
};
