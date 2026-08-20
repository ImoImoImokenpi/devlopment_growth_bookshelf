import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import * as d3 from "d3";
import { NODE_CFG, ndcR } from "../utils/graphConfig";

// ============================================================
// 本棚(SpineShelfView)→知識グラフ(KnowledgeGraph)への画面遷移だけに
// 割り込んで演出を挟む「橋渡し」レイヤー。
// 既存コンポーネントは一切変更せず、document のクリックキャプチャで
// 「知識グラフ」リンクのナビゲーションだけを横取りする。
// 気に入らなければこのファイルと App.js の2行を消せば元に戻る。
// ============================================================

const API = "http://localhost:8000";
const FLY_MS = 1300;
const NODE_STAGGER_MS = 500;
const FADE_OUT_MS = 450;
const BOOK_TARGET_R = (NODE_CFG.Book?.r ?? 7);

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export default function ShelfToGraphBridge() {
  const navigate = useNavigate();
  const location = useLocation();
  const pathRef = useRef(location.pathname);
  useEffect(() => { pathRef.current = location.pathname; }, [location]);

  const [active, setActive] = useState(false);
  const canvasRef = useRef(null);
  const runningRef = useRef(false);

  const runTransition = useCallback(async () => {
    if (runningRef.current) return;

    const bookEls = Array.from(document.querySelectorAll(".spine-book"));
    if (bookEls.length === 0) {
      navigate("/KnowledgeGraph");
      return;
    }
    runningRef.current = true;

    const bookRects = bookEls.map(el => {
      const r = el.getBoundingClientRect();
      return { isbn: el.id.replace("spine-", ""), x: r.left, y: r.top, w: r.width, h: r.height };
    });

    let graph = null;
    try {
      const res = await fetch(`${API}/knowledge_graph/`);
      graph = await res.json();
    } catch {
      graph = null;
    }

    setActive(true);
    // canvas がDOMにマウントされるのを待つ
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

    const canvas = canvasRef.current;
    if (!canvas) {
      navigate("/KnowledgeGraph");
      runningRef.current = false;
      setActive(false);
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    const W = window.innerWidth, H = window.innerHeight;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const fadeAndGo = () => {
      navigate("/KnowledgeGraph");
      const fadeStart = performance.now();
      const fadeFrame = (now) => {
        const t = Math.min(1, (now - fadeStart) / FADE_OUT_MS);
        if (canvasRef.current) canvasRef.current.style.opacity = String(1 - t);
        if (t < 1) requestAnimationFrame(fadeFrame);
        else {
          setActive(false);
          runningRef.current = false;
        }
      };
      requestAnimationFrame(fadeFrame);
    };

    if (!graph || !graph.nodes?.length) {
      fadeAndGo();
      return;
    }

    const nodes = graph.nodes.map(n => ({ ...n }));
    const links = graph.links.map(l => ({ ...l }));

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(d => d.id).distance(38).strength(0.25))
      .force("charge", d3.forceManyBody().strength(-45))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force("collide", d3.forceCollide(9))
      .stop();
    for (let i = 0; i < 150; i++) sim.tick();

    const nodeById = new Map(nodes.map(n => [n.id, n]));

    // 本棚のISBN → 対応するグラフ上のBookノードへ飛ばす
    const flying = [];
    bookRects.forEach(b => {
      const match = nodes.find(n => n.type === "Book" && n.isbn === b.isbn);
      if (match) flying.push({ ...b, target: match });
    });
    const flyingTargetIds = new Set(flying.map(f => f.target.id));
    const others = nodes.filter(n => !flyingTargetIds.has(n.id));

    const resolvedLinks = links.filter(l => {
      const s = typeof l.source === "object" ? l.source.id : l.source;
      const t = typeof l.target === "object" ? l.target.id : l.target;
      return nodeById.has(s) && nodeById.has(t);
    });

    const start = performance.now();
    const totalMs = FLY_MS + NODE_STAGGER_MS + 300;

    const frame = (now) => {
      const elapsed = now - start;
      const bgT = Math.min(1, elapsed / 400);
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = `rgba(13,17,23,${bgT})`;
      ctx.fillRect(0, 0, W, H);

      const flyT = easeOutCubic(Math.min(1, elapsed / FLY_MS));

      // エッジ(両端が到着に近づいてからフェードイン)
      const edgeT = Math.max(0, Math.min(1, (elapsed - FLY_MS * 0.7) / 500));
      if (edgeT > 0) {
        ctx.strokeStyle = `rgba(140,150,170,${0.35 * edgeT})`;
        ctx.lineWidth = 1;
        resolvedLinks.forEach(l => {
          const s = nodeById.get(typeof l.source === "object" ? l.source.id : l.source);
          const t = nodeById.get(typeof l.target === "object" ? l.target.id : l.target);
          if (!s || !t) return;
          ctx.beginPath();
          ctx.moveTo(s.x, s.y);
          ctx.lineTo(t.x, t.y);
          ctx.stroke();
        });
      }

      // 著者・出版社・NDC・コンセプトなどは遅れてフェード+拡大
      const otherT = Math.max(0, Math.min(1, (elapsed - NODE_STAGGER_MS) / 500));
      if (otherT > 0) {
        others.forEach(n => {
          const cfg = NODE_CFG[n.type] ?? { color: "#aaa", r: 5 };
          const targetR = n.type === "NDC" ? ndcR(n.level) : (cfg.r ?? 5);
          const r = targetR * easeOutCubic(otherT);
          ctx.globalAlpha = otherT;
          ctx.beginPath();
          ctx.arc(n.x, n.y, Math.max(0.1, r), 0, Math.PI * 2);
          ctx.fillStyle = cfg.color;
          ctx.fill();
          ctx.globalAlpha = 1;
        });
      }

      // 本: 棚の実座標→グラフ上の位置へ飛びながら円形に収束
      flying.forEach(f => {
        const cx0 = f.x + f.w / 2, cy0 = f.y + f.h / 2;
        const x = cx0 + (f.target.x - cx0) * flyT;
        const y = cy0 + (f.target.y - cy0) * flyT;
        const w = f.w + (BOOK_TARGET_R * 2 - f.w) * flyT;
        const h = f.h + (BOOK_TARGET_R * 2 - f.h) * flyT;
        const rad = 2 + (BOOK_TARGET_R - 2) * flyT;
        roundRect(ctx, x - w / 2, y - h / 2, Math.max(1, w), Math.max(1, h), Math.max(0.5, rad));
        ctx.fillStyle = NODE_CFG.Book?.color ?? "#5b9bd5";
        ctx.fill();
      });

      if (elapsed < totalMs) {
        requestAnimationFrame(frame);
      } else {
        fadeAndGo();
      }
    };

    requestAnimationFrame(frame);
  }, [navigate]);

  useEffect(() => {
    const onClick = (e) => {
      if (pathRef.current !== "/") return;
      const a = e.target.closest?.("a[href='/KnowledgeGraph']");
      if (!a) return;
      e.preventDefault();
      e.stopPropagation();
      runTransition();
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [runTransition]);

  if (!active) return null;

  return (
    <canvas
      ref={canvasRef}
      style={{ position: "fixed", inset: 0, zIndex: 99999, pointerEvents: "auto" }}
    />
  );
}
