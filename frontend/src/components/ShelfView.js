import React, { useEffect, useRef, useContext, useMemo } from "react";
import * as d3 from "d3";
import { MyBookshelfContext } from "../context/MyBookshelfContext";

function ShelfView() {
  const { myBookshelf, fetchBookshelf } = useContext(MyBookshelfContext);
  const svgRef = useRef();

  // 定数定義
  const BOOK_WIDTH = 80;
  const BOOK_HEIGHT = 120;
  const TOP_GAP = 25;
  const FRAME_THICKNESS = 15;
  const BOOKS_PER_SHELF = 5;

  // テクスチャ設定
  const WOOD_URL = "/sources/wood_texture.jpg";
  const DARK_WOOD_URL = "/sources/dark_wood_texture.jpg";

  const books = myBookshelf?.books || [];

  // 1. 最大行数を取得して本棚の段数を決める
  const shelfCount = useMemo(() => {
    if (books.length === 0) return 1;
    // バックエンドから届く book.x は row (0, 1, 2...)
    const maxRow = Math.max(...books.map((b) => b.x || 0));
    return maxRow + 1;
  }, [books]);

  // 2. 本棚の全体サイズ計算
  const unitShelfHeight = TOP_GAP + BOOK_HEIGHT;
  const WIDTH = BOOKS_PER_SHELF * BOOK_WIDTH + FRAME_THICKNESS * 2;
  const HEIGHT = unitShelfHeight * shelfCount + FRAME_THICKNESS * (shelfCount + 1);

  // 3. サーバーの座標(x, y)をピクセル(drawX, drawY)に変換
  const booksWithPosition = useMemo(() => {
    return books.map((book) => {
      // book.x = row(段), book.y = col(列)
      const rowIndex = book.x || 0;
      const colIndex = book.y || 0;

      return {
        ...book,
        drawX: FRAME_THICKNESS + colIndex * BOOK_WIDTH,
        drawY:
          FRAME_THICKNESS +
          rowIndex * (unitShelfHeight + FRAME_THICKNESS) +
          TOP_GAP,
      };
    });
  }, [books, unitShelfHeight]);

  // 初回データ取得
  useEffect(() => {
    fetchBookshelf();
  }, []);

  // D3.js による描画
  useEffect(() => {
    if (books.length === 0) return;

    const svg = d3
      .select(svgRef.current)
      .attr("width", WIDTH)
      .attr("height", HEIGHT);

    svg.selectAll("*").remove();

    const defs = svg.append("defs");

    // テクスチャパターンの作成
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
          .attr("fill", brightness > 1 ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.2)");
      }
    };

    createPattern("woodPattern", WOOD_URL, 1.1);
    createPattern("darkWoodPattern", DARK_WOOD_URL, 0.7);

    // 1. 背板（背景）
    svg.append("rect")
      .attr("width", WIDTH)
      .attr("height", HEIGHT)
      .attr("fill", "#3d2b1f"); // フォールバック色

    svg.append("rect")
      .attr("width", WIDTH)
      .attr("height", HEIGHT)
      .attr("fill", "url(#darkWoodPattern)");

    // 2. 棚板（水平方向）
    for (let i = 0; i <= shelfCount; i++) {
      const yPos = i * (unitShelfHeight + FRAME_THICKNESS);
      svg.append("rect")
        .attr("x", 0)
        .attr("y", yPos)
        .attr("width", WIDTH)
        .attr("height", FRAME_THICKNESS)
        .attr("fill", "#8b4513")
        .attr("fill", "url(#woodPattern)")
        .attr("stroke", "#4d2b13")
        .attr("stroke-width", 0.5);
    }

    // 3. 外枠（左右の柱）
    [0, WIDTH - FRAME_THICKNESS].forEach((xPos) => {
      svg.append("rect")
        .attr("x", xPos)
        .attr("y", 0)
        .attr("width", FRAME_THICKNESS)
        .attr("height", HEIGHT)
        .attr("fill", "#6d3d1a")
        .attr("fill", "url(#woodPattern)");
    });

    // 4. 本の描画
    const bookGroups = svg
      .selectAll(".book-group")
      .data(booksWithPosition)
      .join("g")
      .attr("class", "book-group");

    bookGroups
      .append("image")
      .attr("href", (d) => d.cover) // xlink:href ではなく href 推奨
      .attr("x", (d) => d.drawX)
      .attr("y", (d) => d.drawY)
      .attr("width", BOOK_WIDTH)
      .attr("height", BOOK_HEIGHT)
      .attr("preserveAspectRatio", "xMidYMid slice")
      .style("filter", "drop-shadow(2px 4px 6px rgba(0,0,0,0.7))")
      .on("error", function() {
        d3.select(this).attr("href", "https://via.placeholder.com/80x120?text=No+Image");
      });

  }, [booksWithPosition, WIDTH, HEIGHT, shelfCount]);

  if (books.length === 0) return <p style={{ textAlign: "center", padding: "20px" }}>本棚に本がありません。</p>;

  return (
    <div
      style={{
        padding: "40px",
        display: "flex",
        justifyContent: "center",
        backgroundColor: "#fdfaf6",
      }}
    >
      <div style={{ boxShadow: "0 30px 60px rgba(0,0,0,0.4)", borderRadius: "4px", overflow: "hidden" }}>
        <svg ref={svgRef} style={{ display: "block" }}></svg>
      </div>
    </div>
  );
}

export default ShelfView;