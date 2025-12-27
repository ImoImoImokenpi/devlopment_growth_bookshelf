import React, { useEffect, useRef, useContext, useMemo } from "react";
import * as d3 from "d3";
import { MyBookshelfContext } from "../context/MyBookshelfContext";

function ShelfView() {
  const { myBookshelf, fetchBookshelf } = useContext(MyBookshelfContext);
  const svgRef = useRef();

  const BOOK_WIDTH = 80;
  const BOOK_HEIGHT = 120;
  const TOP_GAP = 25;
  const FRAME_THICKNESS = 15;
  const BOOKS_PER_SHELF = 5;

  // 画像パスが正しいか、publicフォルダを確認してください
  const WOOD_URL = "/sources/wood_texture.jpg";
  const DARK_WOOD_URL = "/sources/dark_wood_texture.jpg";

  const books = myBookshelf?.books || [];
  const bookCount = books.length;

  const shelfCount = Math.max(1, Math.ceil(bookCount / BOOKS_PER_SHELF));
  const effectiveColCount = bookCount <= 4 ? bookCount : BOOKS_PER_SHELF;
  const shelfInnerWidth = effectiveColCount * BOOK_WIDTH;
  const unitShelfHeight = TOP_GAP + BOOK_HEIGHT;

  const WIDTH = shelfInnerWidth + FRAME_THICKNESS * 2;
  const HEIGHT =
    unitShelfHeight * shelfCount + FRAME_THICKNESS * (shelfCount + 1);

  const booksWithPosition = useMemo(() => {
    return books.map((book, index) => {
      const shelfIndex = Math.floor(index / BOOKS_PER_SHELF);
      const colIndex = index % BOOKS_PER_SHELF;
      return {
        ...book,
        x: FRAME_THICKNESS + colIndex * BOOK_WIDTH,
        y:
          FRAME_THICKNESS +
          shelfIndex * (unitShelfHeight + FRAME_THICKNESS) +
          TOP_GAP,
      };
    });
  }, [books, shelfInnerWidth]);

  useEffect(() => {
    fetchBookshelf();
  }, []);

  useEffect(() => {
    if (bookCount === 0) return;

    const svg = d3
      .select(svgRef.current)
      .attr("width", WIDTH)
      .attr("height", HEIGHT);

    svg.selectAll("*").remove();

    const defs = svg.append("defs");

    // テクスチャ定義 (href を xlink:href ではなく href で統一)
    const createPattern = (id, url, brightness = 1) => {
      const p = defs
        .append("pattern")
        .attr("id", id)
        .attr("patternUnits", "userSpaceOnUse")
        .attr("width", 200)
        .attr("height", 200);

      p.append("image")
        .attr("href", url)
        .attr("width", 200)
        .attr("height", 200)
        .attr("preserveAspectRatio", "xMidYMid slice");

      if (brightness !== 1) {
        p.append("rect")
          .attr("width", 200)
          .attr("height", 200)
          .attr(
            "fill",
            brightness > 1 ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.3)"
          );
      }
    };

    createPattern("woodPattern", WOOD_URL, 1.1);
    createPattern("darkWoodPattern", DARK_WOOD_URL, 0.7);

    // 1. 背板（一番奥）: 画像がなくても茶色になるよう、まず色を塗る
    svg
      .append("rect")
      .attr("width", WIDTH)
      .attr("height", HEIGHT)
      .attr("fill", "#3d2b1f"); // フォールバック色

    svg
      .append("rect")
      .attr("width", WIDTH)
      .attr("height", HEIGHT)
      .attr("fill", "url(#darkWoodPattern)");

    // 2. 水平方向の棚板（天板〜底板）
    for (let i = 0; i <= shelfCount; i++) {
      const yPos = i * (unitShelfHeight + FRAME_THICKNESS);
      svg
        .append("rect")
        .attr("x", 0)
        .attr("y", yPos)
        .attr("width", WIDTH)
        .attr("height", FRAME_THICKNESS)
        .attr("fill", "#8b4513") // フォールバック色
        .attr("fill", "url(#woodPattern)")
        .attr("stroke", "#4d2b13") // 境界線をクッキリさせる
        .attr("stroke-width", 0.5);
    }

    // 3. 垂直方向の外枠（左右）: 棚板を覆うように最後に描く
    [0, WIDTH - FRAME_THICKNESS].forEach((xPos) => {
      svg
        .append("rect")
        .attr("x", xPos)
        .attr("y", 0)
        .attr("width", FRAME_THICKNESS)
        .attr("height", HEIGHT)
        .attr("fill", "#6d3d1a") // フォールバック色
        .attr("fill", "url(#woodPattern)");
    });

    // 4. 本の描画
    const bookGroups = svg
      .selectAll(".book")
      .data(booksWithPosition)
      .join("g")
      .attr("class", "book-group");

    bookGroups
      .append("image")
      .attr("xlink:href", (d) => d.cover)
      .attr("x", (d) => d.x)
      .attr("y", (d) => d.y)
      .attr("width", BOOK_WIDTH)
      .attr("height", BOOK_HEIGHT)
      .attr("preserveAspectRatio", "xMidYMid slice")
      .style("filter", "drop-shadow(3px 4px 4px rgba(0,0,0,0.6))");
  }, [booksWithPosition, WIDTH, HEIGHT]);

  if (bookCount === 0) return <p>本棚に本がありません。</p>;

  return (
    <div
      style={{
        padding: "40px",
        display: "flex",
        justifyContent: "center",
        backgroundColor: "#fdfaf6",
      }}
    >
      <div style={{ boxShadow: "0 20px 50px rgba(0,0,0,0.3)" }}>
        <svg ref={svgRef} style={{ display: "block" }}></svg>
      </div>
    </div>
  );
}

export default ShelfView;
