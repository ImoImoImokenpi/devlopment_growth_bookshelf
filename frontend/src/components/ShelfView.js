import React, { useEffect, useRef, useContext, useMemo, useState, useCallback } from "react";
import * as d3 from "d3";
import { MyBookshelfContext } from "../context/MyBookshelfContext";

// ─────────────────────────────────────────────
// 【修正①】押し出しロジックを純粋関数として外部化
//   drag中・end時の両方からこの関数を呼ぶことで重複を解消する。
//
//   引数:
//     positions  : Map<isbn, {x: row, y: col}>  (変更対象。呼び出し元が用意する)
//     targetIsbn : ドラッグ中の本のisbn（押し出し対象から除外）
//     targetRow  : 移動先 row
//     targetCol  : 移動先 col
//     dragDx     : ドラッグのx方向変位（正=右優先、負=左優先）
//     booksPerShelf : 最大列数
//
//   戻り値: 押し出し成功なら true、失敗なら false
// ─────────────────────────────────────────────
function applyPushLogic(positions, targetIsbn, targetRow, targetCol, dragDx, booksPerShelf) {
  const findIntruder = (row, col) => {
    for (const [isbn, pos] of positions.entries()) {
      if (isbn !== targetIsbn && pos.x === row && pos.y === col) return [isbn, pos];
    }
    return null;
  };

  const pushRight = (row, col) => {
    const intruder = findIntruder(row, col);
    if (!intruder) return true;
    const [isbn, pos] = intruder;
    if (pos.y + 1 >= booksPerShelf) return false;
    if (pushRight(row, pos.y + 1)) {
      positions.set(isbn, { x: pos.x, y: pos.y + 1 });
      return true;
    }
    return false;
  };

  const pushLeft = (row, col) => {
    const intruder = findIntruder(row, col);
    if (!intruder) return true;
    const [isbn, pos] = intruder;
    if (pos.y - 1 < 0) return false;
    if (pushLeft(row, pos.y - 1)) {
      positions.set(isbn, { x: pos.x, y: pos.y - 1 });
      return true;
    }
    return false;
  };

  return dragDx >= 0
    ? pushRight(targetRow, targetCol) || pushLeft(targetRow, targetCol)
    : pushLeft(targetRow, targetCol) || pushRight(targetRow, targetCol);
}

// ─────────────────────────────────────────────

function ShelfView() {
  const { myBookshelf, fetchBookshelf, updateShelfLayout, addShelfRow, removeShelfRow } =
    useContext(MyBookshelfContext);
  const svgRef = useRef();

  // タイマー管理用のRef
  const syncTimerRef = useRef(null);

  // --- 1. 定数設定 ---
  const BOOK_WIDTH = 80;
  const BOOK_HEIGHT = 120;
  const TOP_GAP = 30;
  const FRAME_THICKNESS = 18;
  const WOOD_URL = "/sources/wood_texture.jpg";
  const DARK_WOOD_URL = "/sources/dark_wood_texture.jpg";

  // --- 2. State管理 ---
  const [inputValue, setInputValue] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedIsbns, setSelectedIsbns] = useState([]);
  const [meaning, setMeaning] = useState("");

  // 【修正②】localLayout を「唯一の配置状態」として扱う
  //   - books（サーバー由来）が変わった時だけ初期化
  //   - drag終了時にここを更新し、保存APIにも localLayout を渡す
  //   - D3の描画依存配列にも localLayout を使うことで
  //     fetchBookshelf() 後に自動的に再描画される
  const [localLayout, setLocalLayout] = useState([]);
  

  const books = myBookshelf?.books || [];
  const currentBooksPerShelf = myBookshelf?.books_per_shelf || 5;
  const shelfCount = myBookshelf?.total_shelves || 3;

  // --- 3. 座標計算ロジック ---
  const unitShelfHeight = TOP_GAP + BOOK_HEIGHT;
  const WIDTH = currentBooksPerShelf * BOOK_WIDTH + FRAME_THICKNESS * 2;
  const HEIGHT = unitShelfHeight * shelfCount + FRAME_THICKNESS * (shelfCount + 1);
  const modalTopOffset = Math.max(100, HEIGHT / 2 + 100);

  const getPhysPos = useCallback(
    (row, col) => ({
      x: FRAME_THICKNESS + col * BOOK_WIDTH,
      y: FRAME_THICKNESS + row * (unitShelfHeight + FRAME_THICKNESS) + TOP_GAP,
    }),
    [unitShelfHeight]
  );

  const getGridPos = useCallback(
    (pxX, pxY) => ({
      row: Math.max(
        0,
        Math.min(
          Math.floor((pxY - FRAME_THICKNESS) / (unitShelfHeight + FRAME_THICKNESS)),
          shelfCount - 1
        )
      ),
      col: Math.max(
        0,
        Math.min(Math.floor((pxX - FRAME_THICKNESS) / BOOK_WIDTH), currentBooksPerShelf - 1)
      ),
    }),
    [unitShelfHeight, shelfCount, currentBooksPerShelf]
  );

  // booksWithPosition: localLayout の row/col からピクセル座標を計算して付加する
  // 【修正③】books ではなく localLayout を使うことで、
  //   サーバーからの更新と drag後のローカル更新が一本化される
  const booksWithPosition = useMemo(() => {
    return books.map((book) => {
      const layout = localLayout.find((l) => l.isbn === book.isbn);
      const row = layout?.x ?? book.x ?? 0;
      const col = layout?.y ?? book.y ?? 0;
      const phys = getPhysPos(row, col);
      return { ...book, gridRow: row, gridCol: col, x: phys.x, y: phys.y };
    });
  }, [books, localLayout, getPhysPos]);

  // --- 4. ライフサイクル ---
  useEffect(() => {
    fetchBookshelf();
  }, []);

  // サーバーから books が変わった時だけ localLayout を初期化
  useEffect(() => {
    if (!books.length) return;
    setLocalLayout(books.map((b) => ({ isbn: b.isbn, x: b.x, y: b.y })));
  }, [books]);

  useEffect(() => {
    setInputValue(currentBooksPerShelf);
  }, [currentBooksPerShelf]);

  // --- 5. ハンドラ ---
  const handleCancelSelection = useCallback(() => {
    setIsModalOpen(false);
    setMeaning("");
    setSelectedIsbns([]);
    // ハイライトは D3 の再描画（selectedIsbns → [] → useEffect）でクリアされる
  }, []);

  const handleRemoveRow = async () => {
    try {
      await removeShelfRow();
    } catch (err) {
      alert(err.message || "その段には本があるため削除できません");
    }
  };

  const handleSaveMeaning = async () => {
    if (!meaning.trim()) return alert("意味を入力してください");
    try {
      const res = await fetch("http://localhost:8000/bookshelf/save-concept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ meaning, isbns: selectedIsbns }),
      });
      if (res.ok) handleCancelSelection();
    } catch (err) {
      console.error("Save Error:", err);
    }
  };

  const handleSyncLayout = useCallback(async (layoutData) => {
    console.log("Saving layout to server...", layoutData);
    try {
      await fetch("http://localhost:8000/bookshelf/sync-layout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(layoutData),
      });
      // 保存完了後に最新の状態を取得（任意）
      // fetchBookshelf(); 
    } catch (err) {
      console.error("Layout sync failed:", err);
    }
  }, []);

  // 【追加】アンマウント時にタイマーをクリアするクリーンアップ
  useEffect(() => {
    return () => {
      if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    };
  }, []);

  // --- 6. D3 描画ロジック ---
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current).attr("width", WIDTH).attr("height", HEIGHT);
    svg.selectAll("*").remove();

    // 背景・パターン
    const defs = svg.append("defs");
    const createPattern = (id, url, size) => {
      defs
        .append("pattern")
        .attr("id", id)
        .attr("patternUnits", "userSpaceOnUse")
        .attr("width", size)
        .attr("height", size)
        .append("image")
        .attr("href", url)
        .attr("width", size)
        .attr("height", size)
        .attr("preserveAspectRatio", "xMidYMid slice");
    };
    createPattern("woodPattern", WOOD_URL, 300);
    createPattern("darkWoodPattern", DARK_WOOD_URL, 500);
    svg.append("rect").attr("width", WIDTH).attr("height", HEIGHT).attr("fill", "url(#darkWoodPattern)");
    svg.append("rect").attr("width", WIDTH).attr("height", HEIGHT).attr("fill", "rgba(0,0,0,0.2)");

    // 棚板
    for (let i = 0; i <= shelfCount; i++) {
      const yPos = i * (unitShelfHeight + FRAME_THICKNESS);
      svg
        .append("rect")
        .attr("x", 0)
        .attr("y", yPos)
        .attr("width", WIDTH)
        .attr("height", FRAME_THICKNESS)
        .attr("fill", "url(#woodPattern)");
    }
    [0, WIDTH - FRAME_THICKNESS].forEach((x) => {
      svg
        .append("rect")
        .attr("x", x)
        .attr("y", 0)
        .attr("width", FRAME_THICKNESS)
        .attr("height", HEIGHT)
        .attr("fill", "url(#woodPattern)");
    });

    const guide = svg
      .append("rect")
      .attr("width", BOOK_WIDTH)
      .attr("height", BOOK_HEIGHT)
      .attr("fill", "rgba(255, 255, 255, 0.2)")
      .attr("stroke", "#fff")
      .attr("stroke-width", 2)
      .attr("stroke-dasharray", "8,4")
      .style("visibility", "hidden")
      .attr("rx", 6);

    // ─────────────────────────────────────────────
    // ラバーバンド選択ロジック
    //
    // SVG上の「本以外のエリア」でマウスダウン → ドラッグ中は点線矩形を表示
    // マウスアップ時に矩形と重なる本を selectedIsbns に設定してモーダルを開く
    //
    // 本の上でのドラッグと区別するため、dragHandler 側の start で
    // "dragging-book" フラグを svg に立て、rubberband 側はそれを見て無視する
    // ─────────────────────────────────────────────

    // ラバーバンド矩形（点線）
    const rubberband = svg
      .append("rect")
      .attr("fill", "rgba(100, 180, 255, 0.15)")
      .attr("stroke", "#64b4ff")
      .attr("stroke-width", 1.5)
      .attr("stroke-dasharray", "6,3")
      .attr("rx", 4)
      .style("visibility", "hidden")
      .style("pointer-events", "none");

    // 選択ハイライト用レイヤー（本の上に薄い青を重ねる）
    const updateHighlights = (isbns) => {
      svg.selectAll(".book-highlight").remove();
      if (!isbns.length) return;
      booksWithPosition
        .filter((b) => isbns.includes(b.isbn))
        .forEach((b) => {
          svg
            .append("rect")
            .attr("class", "book-highlight")
            .attr("x", b.x)
            .attr("y", b.y)
            .attr("width", BOOK_WIDTH)
            .attr("height", BOOK_HEIGHT)
            .attr("rx", 4)
            .attr("fill", "rgba(100, 180, 255, 0.35)")
            .attr("stroke", "#64b4ff")
            .attr("stroke-width", 2)
            .style("pointer-events", "none");
        });
    };

    // SVG全体にラバーバンド用ドラッグを設定
    let rbStartX = 0;
    let rbStartY = 0;
    let isDraggingBook = false;

    const rubberbandDrag = d3
      .drag()
      .filter((event) => {
        // 本の上でのクリックは除外（book-group は自分の dragHandler を持つ）
        return !event.target.classList.contains("book-group");
      })
      .on("start", function (event) {
        if (isModalOpen) return;
        isDraggingBook = false;
        const [mx, my] = d3.pointer(event, svgRef.current);
        rbStartX = mx;
        rbStartY = my;
        rubberband
          .attr("x", mx)
          .attr("y", my)
          .attr("width", 0)
          .attr("height", 0)
          .style("visibility", "visible");
      })
      .on("drag", function (event) {
        if (isModalOpen) return;
        const [mx, my] = d3.pointer(event, svgRef.current);
        const rx = Math.min(mx, rbStartX);
        const ry = Math.min(my, rbStartY);
        const rw = Math.abs(mx - rbStartX);
        const rh = Math.abs(my - rbStartY);
        rubberband.attr("x", rx).attr("y", ry).attr("width", rw).attr("height", rh);

        // ドラッグ中もリアルタイムでハイライト更新
        const hit = booksWithPosition
          .filter((b) => {
            return (
              b.x < rx + rw &&
              b.x + BOOK_WIDTH > rx &&
              b.y < ry + rh &&
              b.y + BOOK_HEIGHT > ry
            );
          })
          .map((b) => b.isbn);
        updateHighlights(hit);
      })
      .on("end", function (event) {
        rubberband.style("visibility", "hidden");
        if (isModalOpen) return;

        const [mx, my] = d3.pointer(event, svgRef.current);
        const rx = Math.min(mx, rbStartX);
        const ry = Math.min(my, rbStartY);
        const rw = Math.abs(mx - rbStartX);
        const rh = Math.abs(my - rbStartY);

        // 5px未満の動きはクリックとみなして選択解除
        if (rw < 5 && rh < 5) {
          updateHighlights([]);
          return;
        }

        const hit = booksWithPosition
          .filter((b) => {
            return (
              b.x < rx + rw &&
              b.x + BOOK_WIDTH > rx &&
              b.y < ry + rh &&
              b.y + BOOK_HEIGHT > ry
            );
          })
          .map((b) => b.isbn);

        if (hit.length > 0) {
          setSelectedIsbns(hit);
          setIsModalOpen(true);
        } else {
          updateHighlights([]);
        }
      });

    svg.call(rubberbandDrag);

    // ─────────────────────────────────────────────
    // ドラッグハンドラー
    // 【修正①】押し出しロジックは applyPushLogic() を呼ぶだけ
    // ─────────────────────────────────────────────
    const dragHandler = d3
      .drag()
      .on("start", function (event) {
        if (isModalOpen) return;
        const me = d3.select(this);
        me.attr("data-offsetX", event.x - parseFloat(me.attr("x"))).attr(
          "data-offsetY",
          event.y - parseFloat(me.attr("y"))
        );
        me.raise().transition().duration(200).attr("width", BOOK_WIDTH * 1.05);
        guide.style("visibility", "visible");
      })
      .on("drag", function (event, d) {
        if (isModalOpen) return;
        const me = d3.select(this);
        const newX = event.x - +me.attr("data-offsetX");
        const newY = event.y - +me.attr("data-offsetY");
        me.attr("x", newX).attr("y", newY);

        const target = getGridPos(newX + BOOK_WIDTH / 2, newY + BOOK_HEIGHT / 2);

        // 【修正①】drag中のプレビュー用 Map を作り applyPushLogic に渡す
        const virtualPositions = new Map(
          booksWithPosition
            .filter((b) => b.isbn !== d.isbn)
            .map((b) => [b.isbn, { x: b.gridRow, y: b.gridCol }])
        );

        const canPush = applyPushLogic(
          virtualPositions,
          d.isbn,
          target.row,
          target.col,
          event.dx,
          currentBooksPerShelf
        );

        if (canPush) {
          const snap = getPhysPos(target.row, target.col);
          guide.attr("x", snap.x).attr("y", snap.y).style("visibility", "visible");

          svg
            .selectAll(".book-group")
            .filter((other) => other.isbn !== d.isbn)
            .each(function (other) {
              const vPos = virtualPositions.get(other.isbn);
              const phys = getPhysPos(vPos.x, vPos.y);
              d3.select(this)
                .interrupt()
                .transition()
                .duration(200)
                .ease(d3.easeCubicOut)
                .attr("x", phys.x)
                .attr("y", phys.y);
            });
        } else {
          guide.style("visibility", "hidden");
        }
      })
      .on("end", async function (event, d) {
        const me = d3.select(this);
        const target = getGridPos(+me.attr("x") + BOOK_WIDTH / 2, +me.attr("y") + BOOK_HEIGHT / 2);

        const positionMap = new Map(
          booksWithPosition.map((b) => [b.isbn, { x: b.gridRow, y: b.gridCol }])
        );

        const pushed = applyPushLogic(
          positionMap,
          d.isbn,
          target.row,
          target.col,
          event.dx,
          currentBooksPerShelf
        );

        if (pushed) {
          positionMap.set(d.isbn, { x: target.row, y: target.col });
        }

        const nextLayout = Array.from(positionMap.entries()).map(([isbn, pos]) => ({
          isbn,
          x: pos.x,
          y: pos.y,
        }));

        // UI（localLayout）は即座に反映して快適な操作感を維持
        setLocalLayout(nextLayout);

        // アニメーション実行
        const finalPos = positionMap.get(d.isbn);
        const finalPhys = getPhysPos(finalPos.x, finalPos.y);
        me.transition()
          .duration(500)
          .ease(d3.easeElasticOut.amplitude(0.8))
          .attr("x", finalPhys.x)
          .attr("y", finalPhys.y)
          .attr("width", BOOK_WIDTH);

        guide.style("visibility", "hidden");

        // ─────────────────────────────────────────────
        // 【修正】10秒間のデバウンス処理
        // ─────────────────────────────────────────────
        // 1. 既存のタイマーがあれば破棄（操作が続く限り保存を先延ばしする）
        if (syncTimerRef.current) {
          clearTimeout(syncTimerRef.current);
        }

        // 2. 10秒（10000ms）後に保存を実行する予約
        syncTimerRef.current = setTimeout(() => {
          handleSyncLayout(nextLayout);
        }, 10000); 
        // ─────────────────────────────────────────────
      });

    // 本の初期配置
    svg
      .selectAll(".book-group")
      .data(booksWithPosition, (d) => d.isbn)
      .join("image")
      .attr("class", "book-group")
      .attr("href", (d) => d.cover)
      .attr("x", (d) => d.x)
      .attr("y", (d) => d.y)
      .attr("width", BOOK_WIDTH)
      .attr("height", BOOK_HEIGHT)
      .attr("preserveAspectRatio", "xMidYMid slice")
      .style("cursor", "grab")
      .call(dragHandler);

    // 再描画時（モーダルclose後など）に選択状態を復元
    updateHighlights(selectedIsbns);
  }, [
    booksWithPosition,
    WIDTH,
    HEIGHT,
    shelfCount,
    getGridPos,
    getPhysPos,
    isModalOpen,
    currentBooksPerShelf,
    fetchBookshelf,
    localLayout,
    selectedIsbns, // ラバーバンド選択・モーダルclose時にハイライトを再描画
  ]);

  return (
    <div style={containerStyle}>
      <div style={toolbarStyle}>
        <div style={toolGroupStyle}>
          <label style={labelStyle}>段の収容数</label>
          <div style={{ display: "flex", gap: "8px" }}>
            <input
              type="number"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              style={inputStyle}
            />
            <button onClick={() => updateShelfLayout(parseInt(inputValue))} style={primaryButtonStyle}>
              適用
            </button>
          </div>
        </div>
        <div style={dividerStyle} />
        <div style={toolGroupStyle}>
          <label style={labelStyle}>棚の管理</label>
          <div style={{ display: "flex", gap: "10px" }}>
            <button onClick={addShelfRow} style={secondaryButtonStyle}>
              + 段を追加
            </button>
            <button onClick={handleRemoveRow} style={dangerButtonStyle}>
              − 段を削除
            </button>
          </div>
        </div>
      </div>

      <div style={shelfWrapperStyle}>
        <svg ref={svgRef} style={svgStyle} />
      </div>

      {isModalOpen && (
        <div style={{ ...modalOverlayStyle, alignItems: "flex-start", paddingTop: `${modalTopOffset}px` }}>
          <div style={modalContentStyle}>
            <h3 style={{ margin: "0 0 10px 0" }}>{selectedIsbns.length} 冊を選択中</h3>
            <p style={{ color: "#666", fontSize: "14px", marginBottom: "20px" }}>
              本の「意味」を入力してください。
            </p>
            <input
              autoFocus
              type="text"
              value={meaning}
              onChange={(e) => setMeaning(e.target.value)}
              placeholder="例: プログラミングの基礎"
              style={modalInputStyle}
            />
            <div style={{ display: "flex", gap: "12px", marginTop: "25px", justifyContent: "flex-end" }}>
              <button onClick={handleCancelSelection} style={secondaryButtonStyle}>
                キャンセル
              </button>
              <button onClick={handleSaveMeaning} style={primaryButtonStyle}>
                保存する
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Styles ---
const containerStyle = {
  padding: "60px 20px",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  backgroundColor: "#f4f1ea",
  minHeight: "100vh",
  fontFamily: "'Inter', sans-serif",
};
const toolbarStyle = {
  display: "flex",
  alignItems: "center",
  gap: "30px",
  padding: "15px 30px",
  backgroundColor: "rgba(255, 255, 255, 0.8)",
  backdropFilter: "blur(10px)",
  borderRadius: "20px",
  boxShadow: "0 10px 30px rgba(0,0,0,0.05)",
  marginBottom: "40px",
  border: "1px solid rgba(255,255,255,0.3)",
};
const toolGroupStyle = { display: "flex", flexDirection: "column", gap: "6px" };
const labelStyle = { fontSize: "12px", fontWeight: "bold", color: "#888", textTransform: "uppercase" };
const inputStyle = {
  width: "60px",
  padding: "8px",
  borderRadius: "8px",
  border: "1px solid #ddd",
  textAlign: "center",
  fontSize: "16px",
  fontWeight: "600",
};
const primaryButtonStyle = {
  padding: "10px 20px",
  backgroundColor: "#2c3e50",
  color: "#fff",
  border: "none",
  borderRadius: "10px",
  cursor: "pointer",
  fontWeight: "600",
};
const secondaryButtonStyle = { ...primaryButtonStyle, backgroundColor: "#fff", color: "#2c3e50", border: "1px solid #ddd" };
const dangerButtonStyle = { ...secondaryButtonStyle, color: "#e53935" };
const dividerStyle = { width: "1px", height: "40px", backgroundColor: "#eee" };
const shelfWrapperStyle = { perspective: "1000px" };
const svgStyle = { boxShadow: "0 50px 100px rgba(0,0,0,0.2), 0 15px 35px rgba(0,0,0,0.1)", borderRadius: "4px" };
const modalOverlayStyle = {
  position: "fixed",
  top: 0,
  left: 0,
  width: "100vw",
  height: "100vh",
  backgroundColor: "rgba(0,0,0,0.4)",
  backdropFilter: "blur(4px)",
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  zIndex: 9999,
};
const modalContentStyle = { backgroundColor: "#fff", padding: "30px", borderRadius: "24px", width: "420px", boxShadow: "0 25px 50px rgba(0,0,0,0.3)" };
const modalInputStyle = {
  width: "100%",
  padding: "15px",
  borderRadius: "12px",
  border: "2px solid #eee",
  fontSize: "16px",
  outline: "none",
  boxSizing: "border-box",
};

export default ShelfView;