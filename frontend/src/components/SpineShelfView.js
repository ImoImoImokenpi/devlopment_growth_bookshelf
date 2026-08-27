import React, { useEffect, useRef, useContext, useMemo, useState, useCallback } from "react";
import * as d3 from "d3";
import { MyBookshelfContext } from "../context/MyBookshelfContext";
import { useShelfWorkspace } from "../context/ShelfWorkspaceContext";

// ─────────────────────────────────────────────
// 定数
// ─────────────────────────────────────────────
const TOP_GAP         = 40;
const FRAME           = 20;
const SHELF_PAD       = 0;
const SNAP            = 15;
const WOOD_URL        = "/sources/wood_texture.jpg";
const DARK_WOOD_URL   = "/sources/dark_wood_texture.jpg";
const SYNC_DELAY_MS   = 10_000;
const MAX_BOOK_HEIGHT = 250;
const SHELF_MAX_WIDTH = 800;
const LONG_PRESS_MS      = 400; // これ以上押し続けたら「移動」ジェスチャーとみなす
const TAP_MOVE_THRESHOLD = 6;   // 長押しに至らなかった場合、この移動量未満なら「タップ」扱い
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
function resolveSpineHeight(book) {
  return Math.min(1000, Math.max(10, book.height_mm * 1.2));
}
function resolveSpineWidth(book) {
  const fromPages = book?.pages ? Math.min(100, Math.max(1, book.pages * 0.08)) : 20;
  return fromPages;
}

function snapX(x) {
  return Math.round(x / SNAP) * SNAP;
}

// ─────────────────────────────────────────────
// gapベースのスタック判定（案C）
// ─────────────────────────────────────────────
/**
 * 棚上の本を「最大gap」で左右2スタックに分割する。
 * 本が0冊・1冊の場合は全冊を left に入れて返す。
 *
 * @param {Array}  books       - 対象棚の本（x座標がセット済み）
 * @param {number} frameLeft   - 棚の左端px（= FRAME）
 * @param {number} frameRight  - 棚の右端px（= WIDTH - FRAME）
 * @returns {{ splitX: number, left: Array, right: Array }}
 */
function detectStacks(books, frameLeft, frameRight) {
  const sorted = [...books].sort((a, b) => a.x - b.x);

  if (sorted.length <= 1) {
    return {
      splitX: (frameLeft + frameRight) / 2,
      left: sorted,
      right: [],
    };
  }

  let maxGap = -Infinity;
  let splitX = (frameLeft + frameRight) / 2;

  for (let i = 0; i < sorted.length - 1; i++) {
    const rightEdge = sorted[i].x + resolveSpineWidth(sorted[i]);
    const leftEdge  = sorted[i + 1].x;
    const gap = leftEdge - rightEdge;
    if (gap > maxGap) {
      maxGap = gap;
      splitX = (rightEdge + leftEdge) / 2; // gapの中心を分割点とする
    }
  }

  return {
    splitX,
    left:  sorted.filter(b => b.x + resolveSpineWidth(b) / 2 <= splitX),
    right: sorted.filter(b => b.x + resolveSpineWidth(b) / 2 >  splitX),
  };
}

// ─────────────────────────────────────────────
// SpineShelfView Component
// ─────────────────────────────────────────────
function SpineShelfView() {
  const { myBookshelf, fetchBookshelf, removeBook } = useContext(MyBookshelfContext);

  // 選択・強調・発見の線は右ペインと共有する（設計書6.1の2ペイン構成）
  const {
    selectedIsbns, setSelectedIsbns,
    focusIsbn, setFocusIsbn,
    highlightIsbns, conceptHighlight,
    refreshDiscoveries, refreshGrowth,
  } = useShelfWorkspace();

  const svgRef = useRef();
  const syncTimerRef = useRef(null);
  const containerRef = useRef();
  const isDraggingBookRef = useRef(false);
  const trashRef = useRef(null);
  const overTrashRef = useRef(false);
  const removeBookRef = useRef(null);
  const stackOwnershipRef = useRef({}); // isbn → "left" | "right"、ドラッグ開始時の所属を記録
  const longPressRef = useRef({ armed: false, inited: false, timer: null, startX: 0, startY: 0 }); // タップ/長押し移動の判定用

  const shelves = myBookshelf?.shelves || [];
  const shelfCount = myBookshelf?.total_shelves || 1;
  const books = useMemo(() => shelves.flatMap((s) => s.books), [shelves]);

  const [localLayout, setLocalLayout] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [meaningInput, setMeaningInput] = useState("");
  const [isSavingMeaning, setIsSavingMeaning] = useState(false);
  const [rubberBand, setRubberBand] = useState(null);
  const [deletedIsbns, setDeletedIsbns] = useState(new Set());

  // 本棚からの語りかけは右ペインの対話パネルが担当する（設計書6.1）。
  // ここでは棚の描画と操作だけに集中する。

  // 意味づけの色分け強調は、右ペインの「この本について」で意味づけに
  // カーソルを合わせたときにだけ出す。棚の上をなぞるだけでは出さない。

  // AI分析の提案は「発見(Discovery)」として保存され、
  // 本棚上の質問カードと右ペインの「まとめて確認」で扱う（設計書6.2）。
  // 強調する本も右ペインから共有されるので、ここでは状態を持たない。

  const unitShelfHeight = TOP_GAP + MAX_BOOK_HEIGHT + SHELF_PAD;

  const PX_TO_MM_SCALE = 1.2;

  const booksWithPosition = useMemo(() => {
    return books
      .filter(b => !deletedIsbns.has(b.isbn))
      .map((book) => {
        const local = localLayout.find((l) => l.isbn === book.isbn);
        const shelfIdx = local?.shelf_index ?? book.shelf_index ?? 0;
        const xPosMM = local?.x_pos ?? book.x_pos ?? 0;
        const xPx = xPosMM * PX_TO_MM_SCALE + FRAME;
        const orderIdx = local?.order_index ?? book.order_index ?? 0;
        return {
          ...book,
          gridRow: shelfIdx,
          gridCol: orderIdx,
          x: xPx,
          y: FRAME + shelfIdx * (unitShelfHeight + FRAME) + TOP_GAP,
        };
      });
  }, [books, localLayout, unitShelfHeight, deletedIsbns]);

  const WIDTH = useMemo(() => {
    const maxWidth = d3.max(
      shelves.map((s) => {
        const total = s.books.reduce(
          (sum, b) => sum + resolveSpineWidth(b),
          0
        );
        return total + FRAME * 2;
      })
    );
    return Math.min(Math.max(maxWidth || 400, 400), 1200);
  }, [shelves]);

  const HEIGHT = unitShelfHeight * shelfCount + FRAME * (shelfCount + 1);

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
      x_pos: b.x_pos ?? 0,
      order_index: b.order_index ?? 0,
    })));
  }, [books]);

  useEffect(() => () => {
    if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
  }, []);

  useEffect(() => { removeBookRef.current = removeBook; }, [removeBook]);

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
    const text = meaningInput.trim();
    if (!text) return alert("意味を入力してください");
    setIsSavingMeaning(true);
    try {
      const res = await fetch("http://localhost:8000/bookshelf/save-concept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isbns: selectedIsbns, meaning: text }),
      });
      if (res.ok) {
        setIsModalOpen(false);
        setMeaningInput("");
        setSelectedIsbns([]);
        // 意味づけが増えると発見と育ち具合が変わるので、右ペインに反映させる
        refreshDiscoveries();
        refreshGrowth();
      } else {
        const data = await res.json().catch(() => null);
        alert(`保存に失敗しました: ${data?.detail || res.status}`);
      }
    } catch (err) {
      console.error("Save meaning failed", err);
      alert("保存に失敗しました。通信エラーの可能性があります。");
    }
    finally { setIsSavingMeaning(false); }
  };

  const handleCloseMeaningModal = () => {
    setIsModalOpen(false);
    setMeaningInput("");
  };

  // ─────────────────────────────────────────────
  // D3 Rendering
  // ─────────────────────────────────────────────
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current)
      .attr("width", "100%")
      .attr("height", "100%")
      .attr("viewBox", `0 0 ${WIDTH} ${HEIGHT}`)
      .attr("preserveAspectRatio", "xMidYMid meet");

    // 背景・構造の初期化
    let staticLayer = svg.select(".static-layer");
    if (staticLayer.empty()) {
      staticLayer = svg.append("g").attr("class", "static-layer");
      const defs = svg.append("defs");

      const mkPattern = (id, url, size) => {
        defs.append("pattern").attr("id", id).attr("patternUnits", "userSpaceOnUse").attr("width", size).attr("height", size)
          .append("image").attr("href", url).attr("width", size).attr("height", size).attr("preserveAspectRatio", "xMidYMid slice");
      };
      mkPattern("woodPat", WOOD_URL, 300);
      mkPattern("darkWoodPat", DARK_WOOD_URL, 500);

      defs.append("filter").attr("id", "bookShadow").attr("x", "-20%").attr("y", "-10%").attr("width", "140%").attr("height", "130%")
        .append("feDropShadow").attr("dx", 3).attr("dy", 4).attr("stdDeviation", 3).attr("flood-color", "rgba(0,0,0,0.5)");
    }

    staticLayer.selectAll("*").remove();
    staticLayer.append("rect").attr("width", WIDTH).attr("height", HEIGHT).attr("fill", "url(#darkWoodPat)");
    staticLayer.append("rect").attr("width", WIDTH).attr("height", HEIGHT).attr("fill", "rgba(0,0,0,0.25)");

    for (let i = 0; i <= shelfCount; i++) {
      const y = i * (unitShelfHeight + FRAME);
      staticLayer.append("rect").attr("x", 0).attr("y", y).attr("width", WIDTH).attr("height", FRAME).attr("fill", "url(#woodPat)");
    }
    [0, WIDTH - FRAME].forEach(x => {
      staticLayer.append("rect").attr("x", x).attr("y", 0).attr("width", FRAME).attr("height", HEIGHT).attr("fill", "url(#woodPat)");
    });

    const guide = svg.selectAll(".drop-guide").data([0]).join("rect").attr("class", "drop-guide")
      .attr("width", 3).attr("height", MAX_BOOK_HEIGHT)
      .attr("fill", "rgba(100,180,255,0.8)")
      .style("visibility", "hidden");

    // ── Drag Logic（長押しで「移動」を開始する。それ未満はタップ扱い）──
    const beginMove = (el, d) => {
      d3.select(el).raise().attr("cursor", "grabbing");
      guide
        .attr("fill", "rgba(100,180,255,0.8)")
        .style("visibility", "visible");

      // ── 案C: gapベースで左右所属を記録 ──
      const shelfBooks = booksWithPosition.filter(b => b.gridRow === d.gridRow);
      const { left, right } = detectStacks(shelfBooks, FRAME, WIDTH - FRAME);
      stackOwnershipRef.current = {
        ...Object.fromEntries(left.map(b  => [b.isbn, "left"])),
        ...Object.fromEntries(right.map(b => [b.isbn, "right"])),
      };

      if (trashRef.current) {
        trashRef.current.style.opacity = "1";
        trashRef.current.style.transform = "translateX(-50%) scale(1)";
      }
    };

    const dragHandler = d3.drag()
      .on("start", function(e, d) {
        if (isModalOpen) return;
        const state = longPressRef.current;
        state.armed = false;
        state.inited = false;
        state.startX = e.x;
        state.startY = e.y;
        clearTimeout(state.timer);
        state.timer = setTimeout(() => { state.armed = true; }, LONG_PRESS_MS);
      })

      .on("drag", function(e, d) {
        if (isModalOpen) return;
        const state = longPressRef.current;
        if (!state.armed) return; // 長押し閾値未満の間は本を動かさない（タップ／範囲選択と衝突させないため）
        if (!state.inited) {
          state.inited = true;
          beginMove(this, d);
        }
        isDraggingBookRef.current = true;

        // ── drag中スペース・スタック判定 ──
        const movingWidth = resolveSpineWidth(d);
        const targetShelfForCheck = getShelfIndex(e.y + MAX_BOOK_HEIGHT / 2);
        const othersForCheck = booksWithPosition
          .filter(b => b.gridRow === targetShelfForCheck && b.isbn !== d.isbn);
        const totalOtherWidth = othersForCheck.reduce((sum, b) => sum + resolveSpineWidth(b), 0);
        const hasSpace = totalOtherWidth + movingWidth <= WIDTH - 2 * FRAME;

        // スペース状況に応じてガイドの色を切り替え
        guide.attr("fill", hasSpace ? "rgba(100,180,255,0.8)" : "rgba(255,80,80,0.8)");

        // トラッシュ判定（既存）
        if (trashRef.current && e.sourceEvent) {
          const { clientX, clientY } = e.sourceEvent;
          const rect = trashRef.current.getBoundingClientRect();
          const over = clientX >= rect.left && clientX <= rect.right &&
                       clientY >= rect.top  && clientY <= rect.bottom;
          if (over !== overTrashRef.current) {
            overTrashRef.current = over;
            trashRef.current.style.backgroundColor = over ? "rgba(220,50,50,0.15)" : "rgba(255,255,255,0.92)";
            trashRef.current.style.borderColor      = over ? "#e53935" : "#bbb";
            trashRef.current.style.color            = over ? "#e53935" : "#aaa";
            trashRef.current.style.transform        = over ? "translateX(-50%) scale(1.18)" : "translateX(-50%) scale(1)";
          }
        }

        // 棚の外（余白）までスライドしていかないよう、描画領域内に留める
        const nx = Math.max(FRAME, Math.min(snapX(e.x), WIDTH - FRAME - movingWidth));
        const ny = Math.max(0, Math.min(e.y, HEIGHT - MAX_BOOK_HEIGHT));
        const centerX = nx + movingWidth / 2;

        d3.select(this).attr("transform", `translate(${nx}, ${ny})`);

        // ガイドを現在位置に追従
        const guideShelf = getShelfIndex(ny + MAX_BOOK_HEIGHT / 2);
        guide
          .attr("x", nx - 1)
          .attr("y", FRAME + guideShelf * (unitShelfHeight + FRAME) + TOP_GAP);

        // 全体スペース不足なら本のアニメーションをスキップ
        if (!hasSpace) return;

        const targetShelf = getShelfIndex(ny + MAX_BOOK_HEIGHT / 2);
        const others = booksWithPosition
          .filter(b => b.gridRow === targetShelf && b.isbn !== d.isbn)
          .sort((a, b) => a.x - b.x);

        // 所属はドラッグ開始時点で固定（座標変化による誤分類を防ぐ）
        const leftBooks  = others.filter(b => (stackOwnershipRef.current[b.isbn] ?? (b.x + resolveSpineWidth(b) / 2 < WIDTH / 2 ? "left" : "right")) === "left");
        const rightBooks = others.filter(b => (stackOwnershipRef.current[b.isbn] ?? (b.x + resolveSpineWidth(b) / 2 < WIDTH / 2 ? "left" : "right")) === "right");

        let leftEdge = FRAME;
        let rightEdge = WIDTH - FRAME;
        leftBooks.forEach(b => { leftEdge = Math.max(leftEdge, b.x + resolveSpineWidth(b)); });
        rightBooks.forEach(b => { rightEdge = Math.min(rightEdge, b.x); });

        // 隙間より本が太い場合はアニメーションをスキップ
        const gap = rightEdge - leftEdge;
        if (movingWidth > gap) return;

        // 距離ベースでスタック側を判定（本の現在位置ではなく、どちらに近いかで決める）
        const distToLeft  = centerX - leftEdge;
        const distToRight = rightEdge - centerX;
        const stackSide   = distToLeft <= distToRight ? "left" : "right";

        if (stackSide === "left") {
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
          // 右スタックを詰める
          let rCursor = WIDTH - FRAME;
          [...rightBooks].reverse().forEach(b => {
            rCursor -= resolveSpineWidth(b);
            svg.selectAll(".spine-book")
              .filter(node => node.isbn === b.isbn)
              .transition().duration(100).ease(d3.easeCubicOut)
              .attr("transform", `translate(${rCursor}, ${b.y})`);
          });

        } else {
          // ── 右スタックだけ動かす ──
          let cursor = WIDTH - FRAME;
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
          // 左スタックを詰める
          let lCursor = FRAME;
          leftBooks.forEach(b => {
            svg.selectAll(".spine-book")
              .filter(node => node.isbn === b.isbn)
              .transition().duration(100).ease(d3.easeCubicOut)
              .attr("transform", `translate(${lCursor}, ${b.y})`);
            lCursor += resolveSpineWidth(b);
          });
        }

        // ── 元の棚（別棚へのドラッグ時）: 隙間を詰める ──
        if (d.gridRow !== targetShelf) {
          const origOthers = booksWithPosition
            .filter(b => b.gridRow === d.gridRow && b.isbn !== d.isbn)
            .sort((a, b) => a.x - b.x);
          const origLeftBooks  = origOthers.filter(b => (stackOwnershipRef.current[b.isbn] ?? (b.x + resolveSpineWidth(b) / 2 < WIDTH / 2 ? "left" : "right")) === "left");
          const origRightBooks = origOthers.filter(b => (stackOwnershipRef.current[b.isbn] ?? (b.x + resolveSpineWidth(b) / 2 < WIDTH / 2 ? "left" : "right")) === "right");

          let lCur = FRAME;
          origLeftBooks.forEach(b => {
            svg.selectAll(".spine-book")
              .filter(node => node.isbn === b.isbn)
              .transition().duration(100).ease(d3.easeCubicOut)
              .attr("transform", `translate(${lCur}, ${b.y})`);
            lCur += resolveSpineWidth(b);
          });
          let rCur = WIDTH - FRAME;
          [...origRightBooks].reverse().forEach(b => {
            rCur -= resolveSpineWidth(b);
            svg.selectAll(".spine-book")
              .filter(node => node.isbn === b.isbn)
              .transition().duration(100).ease(d3.easeCubicOut)
              .attr("transform", `translate(${rCur}, ${b.y})`);
          });
        }
      })

      // ─────────────────────────────────────────────
      // drag "end"
      // ─────────────────────────────────────────────
      .on("end", function(e, d) {
        const state = longPressRef.current;
        clearTimeout(state.timer);
        const wasInited = state.inited;
        const dist = Math.hypot(e.x - state.startX, e.y - state.startY);
        state.armed = false;
        state.inited = false;

        if (!wasInited) {
          // ── 長押しに至らなかった＝タップ ── 詳細パネルを開く
          isDraggingBookRef.current = false;
          if (!isModalOpen && dist < TAP_MOVE_THRESHOLD) {
            // 1冊タップ →「この本について」を右ペインに出す（設計書4章①）。
            // 選択（青枠）は範囲選択＝複数冊への意味づけ専用にして、ここでは触らない。
            // 両方付けると1冊に青とオレンジの枠が重なって読めなくなる。
            setFocusIsbn(d.isbn);
          }
          return;
        }

        isDraggingBookRef.current = false;
        guide.style("visibility", "hidden");
        if (trashRef.current) {
          trashRef.current.style.opacity         = "0";
          trashRef.current.style.backgroundColor = "rgba(255,255,255,0.92)";
          trashRef.current.style.borderColor     = "#bbb";
          trashRef.current.style.color           = "#aaa";
          trashRef.current.style.transform       = "translateX(-50%) scale(1)";
        }
        if (overTrashRef.current) {
          overTrashRef.current = false;
          d3.select(this).transition().duration(220).style("opacity", 0)
            .on("end", function() {
              d3.select(this).remove();
              setDeletedIsbns(prev => new Set([...prev, d.isbn]));
              if (removeBookRef.current) removeBookRef.current(d.isbn);
            });
          return;
        }
        overTrashRef.current = false;
        const tx = snapX(e.x);
        const ty = e.y;
        const targetShelfIdx = getShelfIndex(ty + MAX_BOOK_HEIGHT / 2);
        const movingWidth = resolveSpineWidth(d);
        const centerX = tx + movingWidth / 2;

        const otherBooks = booksWithPosition
          .filter(b => b.isbn !== d.isbn && b.gridRow === targetShelfIdx)
          .sort((a, b) => a.x - b.x);

        // スペースチェック: 収まらなければ全本を元の位置に戻す
        const totalOtherWidth = otherBooks.reduce((sum, b) => sum + resolveSpineWidth(b), 0);
        if (totalOtherWidth + movingWidth > WIDTH - 2 * FRAME) {
          svg.selectAll(".spine-book")
            .transition().duration(300).ease(d3.easeCubicOut)
            .attr("transform", b => `translate(${b.x}, ${b.y})`);
          return;
        }

        let leftEdge = FRAME;
        let rightEdge = WIDTH - FRAME;

        // 所属はドラッグ開始時点で固定
        const leftBooks  = otherBooks.filter(b => (stackOwnershipRef.current[b.isbn] ?? (b.x + resolveSpineWidth(b) / 2 < WIDTH / 2 ? "left" : "right")) === "left");
        const rightBooks = otherBooks.filter(b => (stackOwnershipRef.current[b.isbn] ?? (b.x + resolveSpineWidth(b) / 2 < WIDTH / 2 ? "left" : "right")) === "right");

        leftBooks.forEach(b => { leftEdge = Math.max(leftEdge, b.x + resolveSpineWidth(b)); });
        rightBooks.forEach(b => { rightEdge = Math.min(rightEdge, b.x); });

        const gapCenter = (leftEdge + rightEdge) / 2;
        const stackSide = centerX <= gapCenter ? "left" : "right";

        let nextLayout = [];

        const toMmPos = (pxX, sIdx, oIdx, isbn) => ({
          isbn,
          shelf_index: sIdx,
          x_pos: (pxX - FRAME) / PX_TO_MM_SCALE,
          order_index: oIdx,
        });

        if (stackSide === "left") {
          // ── 左スタックへの挿入 ──
          const insertInto = [...leftBooks];
          let insertIdx = insertInto.length;
          let cursor = FRAME;
          for (let i = 0; i < insertInto.length; i++) {
            const slotCenter = cursor + resolveSpineWidth(insertInto[i]) / 2;
            if (centerX < slotCenter) { insertIdx = i; break; }
            cursor += resolveSpineWidth(insertInto[i]);
          }
          insertInto.splice(insertIdx, 0, { ...d });

          let cur = FRAME;
          insertInto.forEach((b, i) => {
            nextLayout.push(toMmPos(cur, targetShelfIdx, i, b.isbn));
            cur += resolveSpineWidth(b);
          });

          let rCur = WIDTH - FRAME;
          [...rightBooks].reverse().forEach((b, i) => {
            rCur -= resolveSpineWidth(b);
            nextLayout.push(toMmPos(rCur, targetShelfIdx, insertInto.length + (rightBooks.length - 1 - i), b.isbn));
          });

        } else {
          // ── 右スタックへの挿入（左と対称に統一）──
          const insertInto = [...rightBooks];
          let insertIdx = 0;
          let cursor = WIDTH - FRAME;
          for (let i = insertInto.length - 1; i >= 0; i--) {
            cursor -= resolveSpineWidth(insertInto[i]);
            const slotCenter = cursor + resolveSpineWidth(insertInto[i]) / 2;
            if (centerX > slotCenter) { insertIdx = i + 1; break; }
          }
          insertInto.splice(insertIdx, 0, { ...d });

          // 左スタックをmmに変換
          let lCur = FRAME;
          leftBooks.forEach((b, i) => {
            nextLayout.push(toMmPos(lCur, targetShelfIdx, i, b.isbn));
            lCur += resolveSpineWidth(b);
          });

          // 右スタックを右端から詰める（order_index を i から直接計算）
          let rCur = WIDTH - FRAME;
          [...insertInto].reverse().forEach((b, i) => {
            rCur -= resolveSpineWidth(b);
            nextLayout.push(toMmPos(rCur, targetShelfIdx, leftBooks.length + i, b.isbn));
          });
        }

        // 他の棚のデータを維持
        for (let sIdx = 0; sIdx < shelfCount; sIdx++) {
          if (sIdx === targetShelfIdx) continue;
          const otherShelfBooks = localLayout.filter(l => l.shelf_index === sIdx && l.isbn !== d.isbn);
          nextLayout.push(...otherShelfBooks);
        }

        // 全ノードを確定座標へアニメーション移動
        nextLayout.forEach(({ isbn, shelf_index, x_pos }) => {
          const pxX = x_pos * PX_TO_MM_SCALE + FRAME;
          const pxY = FRAME + shelf_index * (unitShelfHeight + FRAME) + TOP_GAP;
          svg.selectAll(".spine-book")
            .filter(node => node.isbn === isbn)
            .transition().duration(200).ease(d3.easeCubicOut)
            .attr("transform", `translate(${pxX}, ${pxY})`);
        });

        setLocalLayout(nextLayout);
        if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
        syncTimerRef.current = setTimeout(() => handleSyncLayout(nextLayout), SYNC_DELAY_MS);
      });

    // ── Books Join ──
    const bookGroups = svg.selectAll(".spine-book")
      .data(booksWithPosition, d => d.isbn)
      .join(
        enter => enter.append("g")
          .attr("class", "spine-book")
          .attr("id", d => `spine-${d.isbn}`)
          .attr("transform", d => `translate(${d.x}, ${d.y})`),
        update => update,
        exit => exit.remove()
      )
      .call(dragHandler);

    bookGroups.each(function(d) {
      const g = d3.select(this);
      if (g.select("rect").empty()) {
        const p = getPalette(d.isbn);
        const sw = resolveSpineWidth(d);
        const sh = resolveSpineHeight(d);
        const offset = MAX_BOOK_HEIGHT - sh;

        g.append("rect").attr("y", offset).attr("width", sw).attr("height", sh).attr("rx", 2).attr("fill", p.bg).attr("filter", "url(#bookShadow)");

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

    // ── 強調の描き分け ─────────────────────────────
    //
    // 同時に何色も光ると意味が読めなくなるので、常にどれか1つだけを出す。
    // 優先順位は「今この瞬間ユーザーが指しているもの」が上。
    //
    //   1. 意味づけのホバー … 右ペインで意味づけにカーソルを合わせている“今”
    //   2. 範囲選択        … 複数冊への意味づけを待っている状態
    //   3. この本について  … 詳細を開いている1冊
    //   4. 対話・質問カード … 背景で進んでいる文脈
    //
    // 強調対象以外の本は沈めて、対象だけが浮かび上がるようにする。
    // 細い枠を足すだけでは、背表紙が密に並んだ棚では埋もれてしまう。
    svg.selectAll(".spine-hl").remove();
    svg.selectAll(".spine-hl-focus").remove();

    const hasSelection = selectedIsbns.length > 0;

    // [対象のISBN, 枠の色, 枠線, 沈めるかどうか] を先に決めてから1回だけ描く
    let markIsbns = [];
    let markColor = null;
    let markDashed = false;
    let markWidth = 3;
    let dimOthers = false;

    if (conceptHighlight) {
      markIsbns = conceptHighlight.isbns || [];
      markColor = conceptHighlight.color;
      dimOthers = true;
    } else if (hasSelection) {
      markIsbns = selectedIsbns;
      markColor = "#64b4ff";
      dimOthers = true;
    } else if (focusIsbn) {
      // 詳細を開いている間は、その1冊に軽く印を付けるだけにする。
      // ここで棚を沈めると、詳細を読んでいる間ずっと1冊しか見えなくなり、
      // 棚を眺めながら考えるという本来の使い方ができなくなる。
      markIsbns = [focusIsbn];
      markColor = "#ff9d3d";
      markWidth = 2;
    } else if (highlightIsbns.length) {
      markIsbns = highlightIsbns;
      markColor = "#ff9d3d";
      markDashed = true;
    }

    const markSet = new Set(markIsbns);
    bookGroups.attr("opacity", d => (!dimOthers || markSet.has(d.isbn) ? 1 : 0.22));

    markSet.forEach(isbn => {
      const b = booksWithPosition.find(x => x.isbn === isbn);
      if (!b) return;
      const top = b.y + (MAX_BOOK_HEIGHT - resolveSpineHeight(b));
      svg.append("rect").attr("class", "spine-hl-focus")
        .attr("x", b.x - 3).attr("y", top - 3)
        .attr("width", resolveSpineWidth(b) + 6).attr("height", resolveSpineHeight(b) + 6)
        .attr("fill", "none").attr("stroke", markColor).attr("stroke-width", markWidth).attr("rx", 5)
        .attr("stroke-dasharray", markDashed ? "6,3" : null)
        .style("filter", `drop-shadow(0 0 ${dimOthers ? 7 : 4}px ${markColor}${dimOthers ? "d9" : "99"})`)
        .style("pointer-events", "none");
    });

  }, [booksWithPosition, WIDTH, HEIGHT, selectedIsbns, isModalOpen, highlightIsbns, conceptHighlight, focusIsbn]);

  // ── ラバーバンド選択 ──
  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl) return;

    let startClient = null;
    let active = false;
    let startedOnBook = false;

    const isOnBook = (el) => {
      while (el) {
        if (el.classList?.contains("spine-book")) return true;
        el = el.parentNode;
      }
      return false;
    };

    const onMouseDown = (e) => {
      if (e.target.tagName === "BUTTON" || e.target.tagName === "INPUT") return;
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
      if (e.target.closest(".meaning-modal-overlay")) return;
      // 本棚の外（右ペイン・質問カード・上部のナビ）で押した場合は、
      // 範囲選択の対象にしない。ここを見落とすと、右ペインをクリックしただけで
      // 棚の選択が解除されてしまう。
      if (!e.target.closest(".shelf-surface")) return;
      startClient = { x: e.clientX, y: e.clientY };
      startedOnBook = isOnBook(e.target);
      active = true;
      isDraggingBookRef.current = false;
    };

    const onMouseMove = (e) => {
      if (!active || !startClient) return;
      if (isDraggingBookRef.current) {
        active = false;
        startClient = null;
        setRubberBand(null);
        return;
      }
      const x = Math.min(e.clientX, startClient.x);
      const y = Math.min(e.clientY, startClient.y);
      const w = Math.abs(e.clientX - startClient.x);
      const h = Math.abs(e.clientY - startClient.y);
      if (w > 3 || h > 3) setRubberBand({ x, y, w, h });
    };

    const onMouseUp = (e) => {
      if (!active || !startClient) return;
      active = false;

      const w = Math.abs(e.clientX - startClient.x);
      const h = Math.abs(e.clientY - startClient.y);

      if (w > 5 && h > 5 && !isDraggingBookRef.current) {
        const rect = svgEl.getBoundingClientRect();
        const scale = Math.min(rect.width / WIDTH, rect.height / HEIGHT);
        const ox = (rect.width - WIDTH * scale) / 2;
        const oy = (rect.height - HEIGHT * scale) / 2;
        const toSvg = (cx, cy) => ({
          x: (cx - rect.left - ox) / scale,
          y: (cy - rect.top - oy) / scale,
        });
        const tl = toSvg(Math.min(e.clientX, startClient.x), Math.min(e.clientY, startClient.y));
        const br = toSvg(Math.max(e.clientX, startClient.x), Math.max(e.clientY, startClient.y));
        const hits = booksWithPosition.filter(b =>
          b.x < br.x && b.x + resolveSpineWidth(b) > tl.x &&
          b.y < br.y && b.y + MAX_BOOK_HEIGHT > tl.y
        ).map(b => b.isbn);
        if (hits.length) setSelectedIsbns(hits);
      } else if (!startedOnBook && w < 5 && h < 5) {
        setSelectedIsbns([]);
      }

      startClient = null;
      setRubberBand(null);
    };

    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);

    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [booksWithPosition, WIDTH]);

  return (
    <div style={s.container}>
      {/* 見出しと育ち具合の表示は右ペイン（育成インジケータ）が担う。
          左ペインは本棚そのものだけに使う（設計書6.1）。 */}
      {/* shelf-surface は範囲選択の当たり判定に使う目印。
          ここより外（右ペインなど）で押しても選択は始まらない。 */}
      <div
        ref={containerRef}
        className="shelf-surface"
        style={{ width: "100%", height: "100%", minHeight: 0 }}
      >
        {/* 幅は常にこのペインいっぱい。段が増えて高さが伸びても幅は縮めず、
            はみ出た分は shelfPane 側の縦スクロールで見る（詳細パネルの
            開閉やレイアウトの幅にサイズ感を左右されないようにする）。 */}
        <svg ref={svgRef} style={{ width: "100%", height: "auto", display: "block" }} />
      </div>
      {rubberBand && (
        <div style={{
          position: "fixed",
          left: rubberBand.x,
          top: rubberBand.y,
          width: rubberBand.w,
          height: rubberBand.h,
          backgroundColor: "rgba(100,180,255,0.1)",
          border: "1px dashed #64b4ff",
          pointerEvents: "none",
          zIndex: 9999,
        }} />
      )}
      {/* 段の増減・本棚サイズの調整・表示切り替えは ShelfSettingsMenu（右下の
          設定ボタン）に集約した。Home.js側でSpineShelfView/OwnBookGridと並べて
          常に表示できるようにするため、ここでは持たない。 */}

      {selectedIsbns.length > 0 && !isModalOpen && (
        <div style={s.selectionBar}>
          <span style={s.selectionCount}>{selectedIsbns.length}冊選択中</span>
          <button style={s.btnPrimary} onClick={() => setIsModalOpen(true)}>意味付け</button>
          
          <button style={s.btnSecondary} onClick={() => setSelectedIsbns([])}>解除</button>
        </div>
      )}

      {/* ゴミ箱ゾーン */}
      <div
        ref={trashRef}
        style={{
          position: "fixed",
          bottom: "30px",
          left: "50%",
          transform: "translateX(-50%)",
          width: "64px",
          height: "64px",
          borderRadius: "50%",
          border: "2px dashed #bbb",
          backgroundColor: "rgba(255,255,255,0.92)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#aaa",
          transition: "background-color 0.15s, border-color 0.15s, transform 0.15s, color 0.15s",
          zIndex: 2000,
          pointerEvents: "none",
          backdropFilter: "blur(6px)",
          boxShadow: "0 4px 20px rgba(0,0,0,0.12)",
          opacity: 0,
        }}
      >
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
          <path d="M10 11v6M14 11v6"/>
          <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
        </svg>
      </div>

      {/* 本の詳細は右ペインの「この本について」が出す（重ねて表示しない） */}

      {isModalOpen && (
        <div style={s.overlay} className="meaning-modal-overlay">
          <div style={s.modal}>
            <h3 style={{ marginBottom: "6px", fontFamily: "serif", color: "#2a1f0e" }}>意味付け</h3>
            <p style={{ fontSize: "12px", color: "#999", marginBottom: "14px" }}>
              選択した{selectedIsbns.length}冊について、自分なりの意味を書き留めよう
            </p>

            <textarea
              autoFocus
              style={s.meaningTextarea}
              value={meaningInput}
              onChange={e => setMeaningInput(e.target.value)}
              placeholder="この本のテーマや意味は..."
              disabled={isSavingMeaning}
            />

            <div style={{ display: "flex", gap: "10px", marginTop: "14px", justifyContent: "flex-end" }}>
              <button onClick={handleCloseMeaningModal} style={s.btnSecondary}>キャンセル</button>
              <button
                onClick={handleSaveMeaning} style={s.btnPrimary}
                disabled={isSavingMeaning || !meaningInput.trim()}
              >
                {isSavingMeaning ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const s = {
  // Home.js の shelfPane（position: relative）にぴったり重ねる。
  // height:"100%" だとネストしたflex/percentage次第で親よりわずかに
  // 大きくなり、shelfPane側のスクロールが棚の外まで伸びてしまうことが
  // あったため、inset:0 で確実に親の範囲だけに固定する。
  // 棚が画面いっぱいで見づらいので、四方に少し余白を取る。
  container: {
    margin: 0, position: "absolute", inset: 0,
    boxSizing: "border-box", padding: "24px 28px",
  },
  btnPrimary: { padding: "8px 18px", backgroundColor: "#c9a84c", color: "#fff", border: "none", borderRadius: "12px", cursor: "pointer", fontWeight: "700" },
  btnSecondary: { padding: "8px 18px", backgroundColor: "transparent", color: "#c9a84c", border: "1px solid #c9a84c", borderRadius: "12px", cursor: "pointer" },
  overlay: { position: "fixed", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: "rgba(0,0,0,0.4)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000 },
  modal: { backgroundColor: "#fff", padding: "26px", borderRadius: "12px", width: "420px", maxWidth: "90vw", boxShadow: "0 20px 40px rgba(0,0,0,0.2)" },
  meaningTextarea: {
    width: "100%", minHeight: "140px", padding: "10px",
    borderRadius: "8px", border: "1px solid #ddd",
    fontSize: "14px", lineHeight: 1.6, fontFamily: "inherit",
    resize: "vertical", boxSizing: "border-box",
  },
  selectionBar: {
    position: "fixed",
    bottom: "90px",
    left: "50%",
    transform: "translateX(-50%)",
    backgroundColor: "#fff",
    padding: "10px 20px",
    borderRadius: "20px",
    boxShadow: "0 8px 30px rgba(0,0,0,0.2)",
    display: "flex",
    alignItems: "center",
    gap: "12px",
    zIndex: 1000,
    border: "1px solid #ede8da",
  },
  selectionCount: {
    fontSize: "13px",
    fontWeight: "600",
    color: "#2a1f0e",
  },
};

export default SpineShelfView;