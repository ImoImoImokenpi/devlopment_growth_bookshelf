// 「他の参加者の本棚を観察する」画面の左ペイン（フェーズ1）。
//
//   1. 全体推測: 本棚を一通り眺めた後（一定時間の経過を合図に）、
//      「この人はどんな人だと思いますか？」の自由記述欄が出現する。
//      送信した時点の条件（experimental/control/transfer）がこの試行全体に適用される。
//   2. 部分推測: システム側が選んだ2〜3個の候補グループ（面白い差分が出やすい
//      組み合わせ）から1つを選んでもらい、その共通点を推測してもらう。
//      候補は自由選択ではなくシステム選定にすることで、閲覧者ごとに推測対象が
//      バラバラになるのを防ぎ、差分の質を横並びで比較できるようにしている。
//      候補にはグループ名を含めない（名前は答えそのものなので見せない）。
//   3. 差分提示（experimental/controlのみ。transferでは丸ごとスキップ）：
//      「あなたとこの人の整理の仕方を比べてみると」カードが出る。
//      中身はStyleProfileの差分をLLMが断定を避けた自然文に翻訳したもの（experimental）、
//      またはパーソナライズしない固定ヒント（control）。
//   4. 事後推測: 全体・部分それぞれの推測を、pre_textを残したまま編集できる形で
//      再提示し、送信するとpost_textとして記録される。
//
// 条件はバックエンド（全体推測の送信時）で決まり、このコンポーネントはそれに従うだけ。
import { useEffect, useMemo, useRef, useState } from "react";

const API = "http://localhost:8000";
const WAIT_MS = 20_000;

export default function PreGuessPanel({ otherId, onHighlight }) {
  // loading | waiting | whole | partial | cards | postguess | done
  const [phase, setPhase] = useState("loading");
  const [condition, setCondition] = useState(null); // "experimental" | "control" | "transfer"

  const [wholeText, setWholeText] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [partialText, setPartialText] = useState("");
  const [structuralCards, setStructuralCards] = useState([]);
  const [semanticCard, setSemanticCard] = useState(null);
  const [hintCards, setHintCards] = useState([]);

  const [postWholeText, setPostWholeText] = useState("");
  const [postPartialText, setPostPartialText] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  // いま選ばれている候補グループの本（部分推測・比較カードのフェーズで
  // 質問が指している対象として本棚側に常時ハイライトさせる）。
  const selectedGroupIsbns = useMemo(() => {
    const group = candidates.find(c => c.group_id === selectedGroupId);
    return group ? group.books.map(b => b.isbn) : [];
  }, [candidates, selectedGroupId]);

  // 全体推測・事後推測など「特定の本の話ではない」フェーズではハイライトを消す。
  useEffect(() => {
    if (phase === "partial" || phase === "cards") {
      onHighlight?.(selectedGroupIsbns);
    } else {
      onHighlight?.([]);
    }
  }, [phase, selectedGroupIsbns, onHighlight]);

  useEffect(() => {
    return () => onHighlight?.([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    setPhase("loading");
    setCondition(null);
    setWholeText("");
    setCandidates([]);
    setSelectedGroupId(null);
    setPartialText("");
    setStructuralCards([]);
    setSemanticCard(null);
    setHintCards([]);
    setPostWholeText("");
    setPostPartialText("");
    setError(null);
    clearTimeout(timerRef.current);

    const loadCandidates = async () => {
      try {
        const res = await fetch(`${API}/knowledge_graph/compare/${otherId}/group-candidates`);
        const json = await res.json().catch(() => null);
        if (cancelled) return;
        if (res.ok) {
          setCandidates(json?.candidates || []);
          setPhase("partial");
        } else {
          setError(json?.detail || "候補の取得に失敗しました");
          setPhase("partial");
        }
      } catch {
        if (!cancelled) { setError("候補の取得に失敗しました"); setPhase("partial"); }
      }
    };

    const applyDiffCardsResponse = (json) => {
      setCondition(json?.condition || null);
      setStructuralCards(json?.structural_cards || []);
      setSemanticCard(json?.semantic_card || null);
      setHintCards(json?.cards || []);
    };

    const loadCards = async (cond) => {
      if (cond === "transfer") {
        // 転移試行では差分提示自体を行わない。事後推測にそのまま進む。
        setPhase("postguess");
        return;
      }
      setPhase("cards");
      try {
        const res = await fetch(`${API}/knowledge_graph/compare/${otherId}/diff-cards`);
        const json = await res.json().catch(() => null);
        if (cancelled) return;
        if (res.ok) applyDiffCardsResponse(json);
        else setError(json?.detail || "比較カードの取得に失敗しました");
      } catch {
        if (!cancelled) setError("比較カードの取得に失敗しました");
      }
    };

    (async () => {
      try {
        const [wholeRes, partialRes] = await Promise.all([
          fetch(`${API}/knowledge_graph/compare/${otherId}/pre-guess`).then(r => (r.ok ? r.json() : { submitted: false })),
          fetch(`${API}/knowledge_graph/compare/${otherId}/partial-guess`).then(r => (r.ok ? r.json() : { submitted: false })),
        ]);
        if (cancelled) return;

        if (wholeRes.submitted) setCondition(wholeRes.condition || null);
        if (partialRes.submitted) setSelectedGroupId(partialRes.chosen_group_id || null);
        if (partialRes.submitted) setPartialText(partialRes.text || "");
        if (wholeRes.submitted) setWholeText(wholeRes.text || "");

        if (wholeRes.submitted && partialRes.submitted) {
          const [postWholeRes, postPartialRes] = await Promise.all([
            fetch(`${API}/knowledge_graph/compare/${otherId}/post-guess?target_type=overall`).then(r => (r.ok ? r.json() : { submitted: false })),
            fetch(`${API}/knowledge_graph/compare/${otherId}/post-guess?target_type=partial`).then(r => (r.ok ? r.json() : { submitted: false })),
          ]);
          if (cancelled) return;

          if (postWholeRes.submitted && postPartialRes.submitted) {
            setPostWholeText(postWholeRes.text || "");
            setPostPartialText(postPartialRes.text || "");
            setPhase("done");
            return;
          }

          setPostWholeText(postWholeRes.text || wholeRes.text || "");
          setPostPartialText(postPartialRes.text || partialRes.text || "");
          loadCards(wholeRes.condition);
        } else if (wholeRes.submitted) {
          loadCandidates();
        } else {
          setPhase("waiting");
          timerRef.current = setTimeout(() => { if (!cancelled) setPhase("whole"); }, WAIT_MS);
        }
      } catch {
        if (cancelled) return;
        setPhase("waiting");
        timerRef.current = setTimeout(() => { if (!cancelled) setPhase("whole"); }, WAIT_MS);
      }
    })();

    return () => { cancelled = true; clearTimeout(timerRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [otherId]);

  const submitWholeGuess = async () => {
    const text = wholeText.trim();
    if (!text || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API}/knowledge_graph/compare/${otherId}/pre-guess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || "送信に失敗しました");
      }

      const res2 = await fetch(`${API}/knowledge_graph/compare/${otherId}/group-candidates`);
      const json2 = await res2.json().catch(() => null);
      if (res2.ok) setCandidates(json2?.candidates || []);
      else setError(json2?.detail || "候補の取得に失敗しました");
      setPhase("partial");
    } catch (err) {
      setError(err.message || "送信に失敗しました");
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitPartialGuess = async () => {
    const text = partialText.trim();
    if (!text || !selectedGroupId || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API}/knowledge_graph/compare/${otherId}/partial-guess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_group_ids: candidates.map(c => c.group_id),
          chosen_group_id: selectedGroupId,
          text,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || "送信に失敗しました");
      }

      setPostWholeText(wholeText);
      setPostPartialText(text);

      if (condition === "transfer") {
        setPhase("postguess");
        setIsSubmitting(false);
        return;
      }

      setPhase("cards");
      const cardsRes = await fetch(`${API}/knowledge_graph/compare/${otherId}/diff-cards`);
      const cardsJson = await cardsRes.json().catch(() => null);
      if (cardsRes.ok) {
        setCondition(cardsJson?.condition || condition);
        setStructuralCards(cardsJson?.structural_cards || []);
        setSemanticCard(cardsJson?.semantic_card || null);
        setHintCards(cardsJson?.cards || []);
      } else {
        setError(cardsJson?.detail || "比較カードの取得に失敗しました");
      }
    } catch (err) {
      setError(err.message || "送信に失敗しました");
      setPhase("partial");
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitPostGuess = async () => {
    const overallText = postWholeText.trim();
    const partialTextTrimmed = postPartialText.trim();
    if (!overallText || !partialTextTrimmed || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await Promise.all([
        fetch(`${API}/knowledge_graph/compare/${otherId}/post-guess`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_type: "overall", text: overallText }),
        }),
        fetch(`${API}/knowledge_graph/compare/${otherId}/post-guess`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_type: "partial", text: partialTextTrimmed }),
        }),
      ]);
      setPhase("done");
    } catch (err) {
      setError(err.message || "送信に失敗しました");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={s.wrap}>
      <div style={s.head}>
        <span style={s.headTitle}>{otherId}の本棚</span>
      </div>

      {(phase === "loading" || phase === "waiting") && (
        <div style={s.hint}>しばらく本棚を眺めてみてください。</div>
      )}

      {phase === "whole" && (
        <div style={s.section}>
          <div style={s.question}>この人はどんな人だと思いますか？</div>
          <textarea
            style={s.textarea}
            value={wholeText}
            onChange={e => setWholeText(e.target.value)}
            placeholder="思ったことを自由に書いてください"
            disabled={isSubmitting}
          />
          <button style={s.submitBtn} onClick={submitWholeGuess} disabled={isSubmitting || !wholeText.trim()}>
            {isSubmitting ? "送信中…" : "送信する"}
          </button>
          {error && <div style={s.error}>{error}</div>}
        </div>
      )}

      {phase === "partial" && (
        <div style={s.section}>
          <div style={s.question}>
            気になる本の組み合わせを1つ選んで、共通点を推測してみてください
          </div>
          {candidates.length > 0 && (
            <div style={s.hint}>カードにカーソルを合わせると、本棚のどの本のことか光って示されます</div>
          )}

          {candidates.length === 0 && !error && <div style={s.hint}>候補を選んでいます…</div>}

          <div style={s.candidateList}>
            {candidates.map(c => (
              <button
                key={c.group_id}
                style={{
                  ...s.candidateCard,
                  ...(selectedGroupId === c.group_id ? s.candidateCardSelected : {}),
                }}
                onClick={() => setSelectedGroupId(c.group_id)}
                onMouseEnter={() => onHighlight?.(c.books.map(b => b.isbn))}
                onMouseLeave={() => onHighlight?.(selectedGroupIsbns)}
                disabled={isSubmitting}
              >
                <div style={s.candidateCovers}>
                  {c.books.slice(0, 5).map(b => (
                    b.cover ? (
                      <img
                        key={b.isbn}
                        src={b.cover}
                        alt=""
                        style={s.candidateCover}
                        onError={e => { e.target.style.display = "none"; }}
                      />
                    ) : (
                      <span key={b.isbn} style={s.candidateTitleChip}>{b.title || b.isbn}</span>
                    )
                  ))}
                </div>
                <div style={s.candidateMeta}>{c.size}冊のグループ</div>
              </button>
            ))}
          </div>

          {selectedGroupId && (
            <>
              <textarea
                style={s.textarea}
                value={partialText}
                onChange={e => setPartialText(e.target.value)}
                placeholder="この本たちに共通することは何だと思いますか？"
                disabled={isSubmitting}
              />
              <button
                style={s.submitBtn}
                onClick={submitPartialGuess}
                disabled={isSubmitting || !partialText.trim()}
              >
                {isSubmitting ? "送信中…" : "送信する"}
              </button>
            </>
          )}
          {error && <div style={s.error}>{error}</div>}
        </div>
      )}

      {phase === "cards" && (
        <div style={s.section}>
          <div style={s.cardsTitle}>あなたとこの人の整理の仕方を比べてみると</div>
          {selectedGroupIsbns.length > 0 && (
            <div style={s.hint}>本棚で光っているのが、ここで話題にしている本たちです</div>
          )}
          {structuralCards.length === 0 && semanticCard === null && hintCards.length === 0 && !error && (
            <div style={s.hint}>読み込んでいます…</div>
          )}

          {condition === "control" && hintCards.map((c, i) => (
            <div key={`hint-${i}`} style={s.card}>{c}</div>
          ))}

          {condition === "experimental" && structuralCards.map((c, i) => (
            <div key={`structural-${i}`} style={s.card}>{c}</div>
          ))}
          {condition === "experimental" && semanticCard?.gap_summary && (
            <div style={s.card}>{semanticCard.gap_summary}</div>
          )}

          {(structuralCards.length > 0 || semanticCard || hintCards.length > 0) && (
            <button style={s.submitBtn} onClick={() => setPhase("postguess")} disabled={isSubmitting}>
              次へ
            </button>
          )}
          {error && <div style={s.error}>{error}</div>}
        </div>
      )}

      {phase === "postguess" && (
        <div style={s.section}>
          <div style={s.question}>あらためて、この人はどんな人だと思いますか？</div>
          <textarea
            style={s.textarea}
            value={postWholeText}
            onChange={e => setPostWholeText(e.target.value)}
            disabled={isSubmitting}
          />
          <div style={s.question}>選んだ本の組み合わせについても、あらためて書いてみてください</div>
          <textarea
            style={s.textarea}
            value={postPartialText}
            onChange={e => setPostPartialText(e.target.value)}
            disabled={isSubmitting}
          />
          <button
            style={s.submitBtn}
            onClick={submitPostGuess}
            disabled={isSubmitting || !postWholeText.trim() || !postPartialText.trim()}
          >
            {isSubmitting ? "送信中…" : "送信する"}
          </button>
          {error && <div style={s.error}>{error}</div>}
        </div>
      )}

      {phase === "done" && (
        <div style={s.section}>
          <div style={s.cardsTitle}>回答ありがとうございました</div>
          <div style={s.hint}>この本棚についての推測は記録されました。</div>
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: {
    display: "flex", flexDirection: "column",
    width: "100%", height: "100%",
    background: "#fdfcf8", borderRight: "1px solid #ede8da",
    overflow: "hidden",
  },
  head: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "12px 14px 8px", flexShrink: 0,
  },
  headTitle: { fontSize: 12.5, fontWeight: 700, color: "#2a1f0e", fontFamily: "serif" },
  hint: { fontSize: 12, color: "#9a8b76", padding: "8px 14px", lineHeight: 1.7 },

  section: { padding: "4px 14px 14px", display: "flex", flexDirection: "column", gap: 10, overflowY: "auto" },
  question: { fontSize: 13, fontWeight: 700, color: "#2a1f0e", lineHeight: 1.6 },
  textarea: {
    minHeight: 80, padding: "10px 12px", borderRadius: 10,
    border: "1px solid #e5ded0", fontSize: 12.5, lineHeight: 1.6,
    fontFamily: "inherit", resize: "vertical",
  },
  submitBtn: {
    alignSelf: "flex-end", padding: "8px 16px", background: "#ff9d3d", color: "#fff",
    border: "none", borderRadius: 10, cursor: "pointer",
    fontSize: 12.5, fontWeight: 600,
  },

  candidateList: { display: "flex", flexDirection: "column", gap: 8 },
  candidateCard: {
    display: "flex", flexDirection: "column", gap: 6,
    padding: "10px 12px", borderRadius: 12, border: "1px solid #ede8da",
    background: "#fff", cursor: "pointer", textAlign: "left",
  },
  candidateCardSelected: { border: "2px solid #ff9d3d", background: "#fff8ef" },
  candidateCovers: { display: "flex", gap: 5, flexWrap: "wrap" },
  candidateCover: { width: 30, height: 44, objectFit: "cover", borderRadius: 3, background: "#eee", flexShrink: 0 },
  candidateTitleChip: {
    fontSize: 10.5, color: "#4a3728", background: "#f3ede0", borderRadius: 6,
    padding: "3px 6px", maxWidth: 90, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  candidateMeta: { fontSize: 10.5, color: "#9a8b76" },

  cardsTitle: { fontSize: 12.5, fontWeight: 700, color: "#2a1f0e", lineHeight: 1.6 },
  card: {
    padding: "10px 12px", borderRadius: "14px 14px 14px 2px", background: "#fff",
    border: "1px solid #ede8da", color: "#4a3728", fontSize: 12.5, lineHeight: 1.7,
  },

  error: {
    fontSize: 11.5, color: "#c9506a", padding: "8px 12px", borderRadius: 10, background: "#fff0f2",
  },
};
