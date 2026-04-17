import React, { useEffect, useRef, useContext, useMemo, useState, useCallback } from "react";
import * as d3 from "d3";
import { MyBookshelfContext } from "../context/MyBookshelfContext";

// ─────────────────────────────────────────────
// 定数
// ─────────────────────────────────────────────
const TOP_GAP         = 28;
const FRAME           = 20;
const SHELF_PAD       = 8;
const SNAP            = 15;
const WOOD_URL        = "/sources/wood_texture.jpg";
const DARK_WOOD_URL   = "/sources/dark_wood_texture.jpg";
const SYNC_DELAY_MS   = 10_000;
const MAX_BOOK_HEIGHT = 220;
const SHELF_MAX_WIDTH = 800;

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

// ─────────────────────────────────────────────
// ヘルパー
// ─────────────────────────────────────────────
function hashCode(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}
function getPalette(isbn) {
  return SPINE_PALETTES[hashCode(isbn || "") % SPINE_PALETTES.length];
}
function resolveSpineWidth(book) {
  if (book?.spine_width_px != null) return book.spine_width_px;
  return 30; 
}
function resolveSpineHeight(book) {
  return book?.spine_height_px > 0 ? book.spine_height_px : 160;
}
function snapX(x) {
  return Math.round(x / SNAP) * SNAP;
}

// ─────────────────────────────────────────────
// SpineShelfView Component
// ─────────────────────────────────────────────
function SpineShelfView() {
  const { myBookshelf, fetchBookshelf, addShelfRow, removeShelfRow } = useContext(MyBookshelfContext);

  const svgRef = useRef();
  const syncTimerRef = useRef(null);
  const containerRef = useRef();

  const shelves = myBookshelf?.shelves || [];
  const shelfCount = myBookshelf?.total_shelves || 1;
  const books = useMemo(() => shelves.flatMap((s) => s.books), [shelves]);

  const [localLayout, setLocalLayout] = useState([]);
  const [selectedIsbns, setSelectedIsbns] = useState([]);
  const [isToolbarOpen, setIsToolbarOpen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [meaning, setMeaning] = useState("");

  const unitShelfHeight = TOP_GAP + MAX_BOOK_HEIGHT + SHELF_PAD;

  // 座標計算
  const booksWithPosition = useMemo(() => {
    return books.map((book) => {
      const local = localLayout.find((l) => l.isbn === book.isbn);
      const shelfIdx = local?.shelf_index ?? book.shelf_index ?? 0;
      const xPos = local?.x_pos ?? book.x_pos ?? FRAME;
      const orderIdx = local?.order_index ?? book.order_index ?? 0;
      return {
        ...book,
        gridRow: shelfIdx,
        gridCol: orderIdx,
        x: xPos,
        y: FRAME + shelfIdx * (unitShelfHeight + FRAME) + TOP_GAP,
      };
    });
  }, [books, localLayout, unitShelfHeight]);

  function getShelfWidthByPixels(books) {
    const totalWidth = books.reduce(
      (sum, b) => sum + resolveSpineWidth(b),
      0
    );

    const padding = 80; // 左右余白
    const rawWidth = totalWidth + padding;

    return Math.min(Math.max(rawWidth, 400), 1100);
  }
  
  const WIDTH = 900; 
  // const WIDTH = useMemo(() => {
  //   return d3.max(
  //     shelves.map((s) => getShelfWidthByPixels(s.books))
  //   ) || 400;
  // }, [shelves]);

  const HEIGHT = unitShelfHeight * shelfCount + FRAME * (shelfCount + 1);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    if (!containerRef.current) return;

    const resize = () => {
      const containerWidth = containerRef.current.clientWidth;
      const containerHeight = window.innerHeight - 200; // 余白

      const scaleX = containerWidth / WIDTH;
      const scaleY = containerHeight / HEIGHT;

      const nextScale = Math.min(scaleX, scaleY, 1); // 最大1（拡大しない）
      setScale(nextScale);
    };

    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [WIDTH, HEIGHT]);

  const getShelfIndex = useCallback((pxY) => {
    return Math.max(0, Math.min(Math.floor((pxY - FRAME) / (unitShelfHeight + FRAME)), shelfCount - 1));
  }, [unitShelfHeight, shelfCount]);

  // ライフサイクル
  useEffect(() => { fetchBookshelf(); }, []);

  useEffect(() => {
    if (!books.length) return;
    setLocalLayout(books.map((b) => ({
      isbn: b.isbn,
      shelf_index: b.shelf_index,
      x_pos: b.x_pos ?? FRAME,
      order_index: b.order_index ?? 0,
    })));
  }, [books]);

  useEffect(() => () => {
    if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
  }, []);

  // API連携
  const handleSyncLayout = useCallback(async (layoutData) => {
    try {
      await fetch("http://localhost:8000/bookshelf/sync-layout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ layout: layoutData }),
      });
    } catch (err) { console.error("Sync failed", err); }
  }, []);

  const handleSaveMeaning = async () => {
    if (!meaning.trim()) return alert("意味を入力してください");
    try {
      const res = await fetch("http://localhost:8000/bookshelf/save-concept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ meaning, isbns: selectedIsbns }),
      });
      if (res.ok) {
        setIsModalOpen(false);
        setMeaning("");
        setSelectedIsbns([]);
      }
    } catch (err) { console.error(err); }
  };

  // ─────────────────────────────────────────────
  // D3 Rendering
  // ─────────────────────────────────────────────
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current).attr("width", WIDTH).attr("height", HEIGHT);
    
    // 背景・構造の初期化
    let staticLayer = svg.select(".static-layer");
    if (staticLayer.empty()) {
      staticLayer = svg.append("g").attr("class", "static-layer");
      const defs = svg.append("defs");

      // 木目パターン
      const mkPattern = (id, url, size) => {
        defs.append("pattern").attr("id", id).attr("patternUnits", "userSpaceOnUse").attr("width", size).attr("height", size)
          .append("image").attr("href", url).attr("width", size).attr("height", size).attr("preserveAspectRatio", "xMidYMid slice");
      };
      mkPattern("woodPat", WOOD_URL, 300);
      mkPattern("darkWoodPat", DARK_WOOD_URL, 500);

      // 影
      defs.append("filter").attr("id", "bookShadow").attr("x", "-20%").attr("y", "-10%").attr("width", "140%").attr("height", "130%")
        .append("feDropShadow").attr("dx", 3).attr("dy", 4).attr("stdDeviation", 3).attr("flood-color", "rgba(0,0,0,0.5)");
    }

    // 描画更新
    staticLayer.selectAll("*").remove();
    staticLayer.append("rect").attr("width", WIDTH).attr("height", HEIGHT).attr("fill", "url(#darkWoodPat)");
    staticLayer.append("rect").attr("width", WIDTH).attr("height", HEIGHT).attr("fill", "rgba(0,0,0,0.25)");

    // 棚板
    for (let i = 0; i <= shelfCount; i++) {
      const y = i * (unitShelfHeight + FRAME);
      staticLayer.append("rect").attr("x", 0).attr("y", y).attr("width", WIDTH).attr("height", FRAME).attr("fill", "url(#woodPat)");
    }
    // 側面
    [0, WIDTH - FRAME].forEach(x => {
      staticLayer.append("rect").attr("x", x).attr("y", 0).attr("width", FRAME).attr("height", HEIGHT).attr("fill", "url(#woodPat)");
    });

    const guide = svg.selectAll(".drop-guide").data([0]).join("rect").attr("class", "drop-guide")
      .attr("width", 3).attr("height", MAX_BOOK_HEIGHT).attr("fill", "rgba(100,180,255,0.8)").style("visibility", "hidden");

    // ── Drag Logic ──
    // ── Drag Logic ──
    const dragHandler = d3.drag()
      .on("start", function(e, d) {
        if (isModalOpen) return;
        d3.select(this).raise().attr("cursor", "grabbing");
        guide.style("visibility", "visible");
      })

      .on("drag", function(e, d) {
        if (isModalOpen) return;
        const nx = snapX(e.x);
        const ny = e.y;
        const movingWidth = resolveSpineWidth(d);
        const centerX = nx + movingWidth / 2;

        d3.select(this).attr("transform", `translate(${nx}, ${ny})`);

        const targetShelf = getShelfIndex(ny + MAX_BOOK_HEIGHT / 2);
        const others = booksWithPosition
          .filter(b => b.gridRow === targetShelf && b.isbn !== d.isbn)
          .sort((a, b) => a.x - b.x);

        // 左右スタックを分類
        const midX = WIDTH / 2;
        const leftBooks = others.filter(b => b.x + resolveSpineWidth(b) / 2 < midX);
        const rightBooks = others.filter(b => b.x + resolveSpineWidth(b) / 2 >= midX);

        // 空きスペースの中央で左右判定
        let leftEdge = FRAME;
        let rightEdge = WIDTH - FRAME;
        leftBooks.forEach(b => { leftEdge = Math.max(leftEdge, b.x + resolveSpineWidth(b)); });
        rightBooks.forEach(b => { rightEdge = Math.min(rightEdge, b.x); });
        const gapCenter = (leftEdge + rightEdge) / 2;

        if (centerX <= gapCenter) {
          // ── 左スタックだけ動かす ──
          let cursor = FRAME;
          let inserted = false;
          leftBooks.forEach(b => {
            if (!inserted && centerX < cursor + resolveSpineWidth(b) / 2) {
              cursor += movingWidth;
              inserted = true;
            }
            svg.selectAll(".spine-book")
              .filter(node => node.isbn === b.isbn)
              .transition().duration(100).ease(d3.easeCubicOut)
              .attr("transform", `translate(${cursor}, ${b.y})`);
            cursor += resolveSpineWidth(b);
          });
          // 右スタックは元の位置に戻す（念のため）
          rightBooks.forEach(b => {
            svg.selectAll(".spine-book")
              .filter(node => node.isbn === b.isbn)
              .transition().duration(100).ease(d3.easeCubicOut)
              .attr("transform", `translate(${b.x}, ${b.y})`);
          });

        } else {
          // ── 右スタックだけ動かす ──
          let cursor = WIDTH - FRAME;
          // 右スタックは右端から積むので、逆順でスライド計算
          const reversed = [...rightBooks].reverse();
          let inserted = false;
          reversed.forEach(b => {
            const bw = resolveSpineWidth(b);
            if (!inserted && centerX > cursor - bw / 2) {
              cursor -= movingWidth;
              inserted = true;
            }
            cursor -= bw;
            svg.selectAll(".spine-book")
              .filter(node => node.isbn === b.isbn)
              .transition().duration(100).ease(d3.easeCubicOut)
              .attr("transform", `translate(${cursor}, ${b.y})`);
          });
          // 左スタックは元の位置に戻す（念のため）
          leftBooks.forEach(b => {
            svg.selectAll(".spine-book")
              .filter(node => node.isbn === b.isbn)
              .transition().duration(100).ease(d3.easeCubicOut)
              .attr("transform", `translate(${b.x}, ${b.y})`);
          });
        }
      })

      // ─────────────────────────────────────────────
      // drag "end" の置き換え部分（on("end") 全体）
      // ─────────────────────────────────────────────
      .on("end", function(e, d) {
        guide.style("visibility", "hidden");
        const tx = snapX(e.x);
        const ty = e.y;
        const targetShelfIdx = getShelfIndex(ty + MAX_BOOK_HEIGHT / 2);
        const movingWidth = resolveSpineWidth(d);
        const centerX = tx + movingWidth / 2;  // ドラッグ中の本の中心X

        // 1. ターゲット棚の「他の本」を取得（左から順にソート）
        const otherBooks = booksWithPosition
          .filter(b => b.isbn !== d.isbn && b.gridRow === targetShelfIdx)
          .sort((a, b) => a.x - b.x);

        // 2. 棚の「左スタック」と「右スタック」の境界を計算
        //    左スタック: FRAME から右に詰めた本の右端
        //    右スタック: WIDTH - FRAME から左に詰めた本の左端
        //    → 両者の間が「空きスペース」
        let leftEdge = FRAME;    // 左スタックの右端
        let rightEdge = WIDTH - FRAME; // 右スタックの左端

        // 本をどちらのスタックに属するか分類するために、
        // まず既存レイアウトの order_index と x_pos で左右を判定する
        // （ここでは簡易的に「中央より左にある本 = 左スタック」とする）
        const midX = WIDTH / 2;
        const leftBooks = otherBooks.filter(b => b.x + resolveSpineWidth(b) / 2 < midX);
        const rightBooks = otherBooks.filter(b => b.x + resolveSpineWidth(b) / 2 >= midX);

        leftBooks.forEach(b => { leftEdge = Math.max(leftEdge, b.x + resolveSpineWidth(b)); });
        rightBooks.forEach(b => { rightEdge = Math.min(rightEdge, b.x); });

        // 3. 空きスペースの中央で左右どちらに吸着するか判定
        const gapCenter = (leftEdge + rightEdge) / 2;
        const stackSide = centerX <= gapCenter ? "left" : "right";

        // 4. 新しい配列順序の生成
        //    left stack: 左から詰める、right stack: 右から詰める
        //    挿入位置はスタック内でのX座標の近さで決める
        let nextLayout = [];

        if (stackSide === "left") {
          // 左スタックに挿入
          const insertInto = [...leftBooks];
          // centerX に最も近い隙間に挿入
          let insertIdx = insertInto.length; // デフォルト: 末尾
          let cursor = FRAME;
          for (let i = 0; i < insertInto.length; i++) {
            const slotCenter = cursor + resolveSpineWidth(insertInto[i]) / 2;
            if (centerX < slotCenter) { insertIdx = i; break; }
            cursor += resolveSpineWidth(insertInto[i]);
          }
          insertInto.splice(insertIdx, 0, { ...d, gridRow: targetShelfIdx });

          // 左から詰めて座標確定
          cursor = FRAME;
          insertInto.forEach((b, i) => {
            nextLayout.push({ isbn: b.isbn, shelf_index: targetShelfIdx, x_pos: cursor, order_index: i });
            cursor += resolveSpineWidth(b);
          });
          // 右スタックはそのまま
          let rCursor = WIDTH - FRAME;
          [...rightBooks].reverse().forEach((b, i) => {
            rCursor -= resolveSpineWidth(b);
            nextLayout.push({ isbn: b.isbn, shelf_index: targetShelfIdx, x_pos: rCursor, order_index: insertInto.length + i });
          });

        } else {
          // 右スタックに挿入
          const insertInto = [...rightBooks];
          let insertIdx = 0; // デフォルト: 先頭（右スタックは右端から積む）
          let cursor = WIDTH - FRAME;
          for (let i = insertInto.length - 1; i >= 0; i--) {
            cursor -= resolveSpineWidth(insertInto[i]);
            const slotCenter = cursor + resolveSpineWidth(insertInto[i]) / 2;
            if (centerX > slotCenter) { insertIdx = i + 1; break; }
          }
          insertInto.splice(insertIdx, 0, { ...d, gridRow: targetShelfIdx });

          // 左スタックはそのまま
          let lCursor = FRAME;
          leftBooks.forEach((b, i) => {
            nextLayout.push({ isbn: b.isbn, shelf_index: targetShelfIdx, x_pos: lCursor, order_index: i });
            lCursor += resolveSpineWidth(b);
          });
          // 右から詰めて座標確定
          let rCursor = WIDTH - FRAME;
          [...insertInto].reverse().forEach((b, i) => {
            rCursor -= resolveSpineWidth(b);
            nextLayout.push({ isbn: b.isbn, shelf_index: targetShelfIdx, x_pos: rCursor, order_index: leftBooks.length + (insertInto.length - 1 - i) });
          });
        }

        // 5. 他の棚はそのまま維持
        for (let sIdx = 0; sIdx < shelfCount; sIdx++) {
          if (sIdx === targetShelfIdx) continue;
          booksWithPosition
            .filter(b => b.gridRow === sIdx)
            .forEach(b => {
              const existing = localLayout.find(l => l.isbn === b.isbn);
              if (existing) nextLayout.push(existing);
            });
        }

        setLocalLayout(nextLayout);
        if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
        syncTimerRef.current = setTimeout(() => handleSyncLayout(nextLayout), SYNC_DELAY_MS);
      });

    // ── Books Join ──
    const bookGroups = svg.selectAll(".spine-book")
      .data(booksWithPosition, d => d.isbn)
      .join("g")
      .attr("class", "spine-book")
      .attr("transform", d => `translate(${d.x}, ${d.y})`)
      .call(dragHandler);

    bookGroups.each(function(d) {
      const g = d3.select(this);
      if (g.select("rect").empty()) {
        const p = getPalette(d.isbn);
        const sw = resolveSpineWidth(d);
        const sh = resolveSpineHeight(d);
        const offset = MAX_BOOK_HEIGHT - sh;

        g.append("rect").attr("y", offset).attr("width", sw).attr("height", sh).attr("rx", 2).attr("fill", p.bg).attr("filter", "url(#bookShadow)");
        
        // 装飾ライン
        g.append("rect").attr("y", offset).attr("width", sw).attr("height", 4).attr("fill", p.accent).attr("opacity", 0.6);
        g.append("rect").attr("y", offset + sh - 4).attr("width", sw).attr("height", 4).attr("fill", p.accent).attr("opacity", 0.6);

        const fo = g.append("foreignObject").attr("y", offset + 10).attr("width", sw).attr("height", sh - 20);
        const div = fo.append("xhtml:div").attr("style", `color:${p.text}; font-size:10px; writing-mode:vertical-rl; padding:4px; height:100%; display:flex; align-items:center; font-family:serif; font-weight:600; overflow:hidden;`);
        div.text(d.title);
      }
    });

    // ハイライト表示
    svg.selectAll(".spine-hl").remove();
    selectedIsbns.forEach(isbn => {
      const b = booksWithPosition.find(x => x.isbn === isbn);
      if (!b) return;
      svg.append("rect").attr("class", "spine-hl")
        .attr("x", b.x - 2).attr("y", b.y + (MAX_BOOK_HEIGHT - resolveSpineHeight(b)) - 2)
        .attr("width", resolveSpineWidth(b) + 4).attr("height", resolveSpineHeight(b) + 4)
        .attr("fill", "none").attr("stroke", "#64b4ff").attr("stroke-width", 2).attr("rx", 4);
    });

  }, [booksWithPosition, WIDTH, HEIGHT, selectedIsbns, isModalOpen]);

  // ── ラバーバンド選択 ──
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    let startX, startY, rb;

    svg.on("mousedown", function(e) {
      if (e.target.tagName !== "svg" && !e.target.classList.contains("static-layer")) return;
      [startX, startY] = d3.pointer(e);
      rb = svg.append("rect").attr("fill", "rgba(100,180,255,0.1)").attr("stroke", "#64b4ff").attr("stroke-dasharray", "4");
    })
    .on("mousemove", function(e) {
      if (!rb) return;
      const [mx, my] = d3.pointer(e);
      rb.attr("x", Math.min(mx, startX)).attr("y", Math.min(my, startY))
        .attr("width", Math.abs(mx - startX)).attr("height", Math.abs(my - startY));
    })
    .on("mouseup", function(e) {
      if (!rb) return;
      const x = +rb.attr("x"), y = +rb.attr("y"), w = +rb.attr("width"), h = +rb.attr("height");
      const hits = booksWithPosition.filter(b => b.x < x + w && b.x + resolveSpineWidth(b) > x && b.y < y + h && b.y + MAX_BOOK_HEIGHT > y).map(b => b.isbn);
      if (hits.length) { setSelectedIsbns(hits); setIsModalOpen(true); }
      rb.remove(); rb = null;
    });
  }, [booksWithPosition]);

  return (
    <div style={s.container}>
      <div 
        ref={containerRef} 
        style={{ 
          perspective: "1200px",
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start"
        }}
      >
        <svg 
          ref={svgRef} 
          style={{
            ...s.svg,
            transform: `translateX(${(1 - scale) * WIDTH / 2}px) scale(${scale})`,
            transformOrigin: "top left"
          }} 
        />
      </div>
      <div style={s.fab} onClick={() => setIsToolbarOpen(v => !v)}>
        ⚙
      </div>

      {isToolbarOpen && (
        <div style={s.floatingPanel}>
          <label style={s.label}>本棚調整</label>
          <div style={{ display: "flex", gap: "10px" }}>
            <button onClick={addShelfRow} style={s.btnSecondary}>+ 段を足す</button>
            <button onClick={removeShelfRow} style={s.btnDanger}>- 段を減らす</button>
          </div>
        </div>
      )}

      {isModalOpen && (
        <div style={s.overlay}>
          <div style={s.modal}>
            <h3 style={{ marginBottom: "10px" }}>{selectedIsbns.length} Books Selected</h3>
            <input 
              autoFocus style={s.modalInput} value={meaning} 
              onChange={e => setMeaning(e.target.value)} placeholder="Enter concept name..."
            />
            <div style={{ display: "flex", gap: "10px", marginTop: "20px", justifyContent: "flex-end" }}>
              <button onClick={() => setIsModalOpen(false)} style={s.btnSecondary}>Cancel</button>
              <button onClick={handleSaveMeaning} style={s.btnPrimary}>Save Concept</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const s = {
  container: { padding: "60px 20px", display: "flex", flexDirection: "column", alignItems: "center", minHeight: "100vh", backgroundColor: "#fdfcf8" },
  toolbar: { display: "flex", gap: "24px", padding: "14px 28px", backgroundColor: "#fff", borderRadius: "16px", boxShadow: "0 4px 20px rgba(0,0,0,0.08)", marginBottom: "40px", border: "1px solid #e0d8c0" },
  toolGroup: { display: "flex", flexDirection: "column", gap: "5px" },
  label: { fontSize: "10px", fontWeight: "700", color: "#c9a84c", textTransform: "uppercase" },
  btnPrimary: { padding: "8px 18px", backgroundColor: "#c9a84c", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer", fontWeight: "700" },
  btnSecondary: { padding: "8px 18px", backgroundColor: "transparent", color: "#c9a84c", border: "1px solid #c9a84c", borderRadius: "8px", cursor: "pointer" },
  btnDanger: { padding: "8px 18px", backgroundColor: "transparent", color: "#c9506a", border: "1px solid #c9506a", borderRadius: "8px", cursor: "pointer" },
  svg: { boxShadow: "0 40px 80px rgba(0,0,0,0.15)", borderRadius: "4px", backgroundColor: "#333" },
  overlay: { position: "fixed", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: "rgba(0,0,0,0.4)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000 },
  modal: { backgroundColor: "#fff", padding: "30px", borderRadius: "12px", width: "350px", boxShadow: "0 20px 40px rgba(0,0,0,0.2)" },
  modalInput: { width: "100%", padding: "10px", borderRadius: "6px", border: "1px solid #ddd" },
  fab: { position: "fixed",
    bottom: "30px",
    right: "30px",
    width: "50px",
    height: "50px",
    borderRadius: "50%",
    backgroundColor: "#c9a84c",
    color: "#fff",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    fontSize: "20px",
    cursor: "pointer",
    boxShadow: "0 6px 20px rgba(0,0,0,0.2)",
    zIndex: 1000
  },

  floatingPanel: {
    position: "fixed",
    bottom: "90px",
    right: "30px",
    backgroundColor: "#fff",
    padding: "16px",
    borderRadius: "12px",
    boxShadow: "0 10px 30px rgba(0,0,0,0.2)",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    zIndex: 1000
  }
};

export default SpineShelfView;