# routers/knowledge_graph.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.manifold import MDS
from sklearn.metrics.pairwise import cosine_similarity
from models import MyBookshelf
import numpy as np
import requests

router = APIRouter(prefix="/knowledge-graph")

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
# DBPEDIA_ENDPOINT = "https://dbpedia.org/sparql"

# def fetch_dbpedia_subjects(label: str, limit=5):
#     clean_label = label.split('（')[0].split('(')[0].strip()

#     query = f"""
#     SELECT DISTINCT ?subjectLabel WHERE {{
#         ?s rdfs:label ?label .
#         FILTER (contains(?label, "{clean_label}")) 
#         FILTER (lang(?label)="ja")
        
#         ?s dct:subject ?subject .
#         ?subject rdfs:label ?subjectLabel .
#         FILTER(lang(?subjectLabel)="ja")
#     }} LIMIT {limit}
#     """

#     try:
#         r = requests.get(
#             DBPEDIA_ENDPOINT,
#             params={"query": query, "format": "json"},
#             timeout=5
#         )
#         if r.status_code != 200:
#             return []

#         data = r.json()
#         return [
#             b["subjectLabel"]["value"]
#             for b in data["results"]["bindings"]
#         ]
#     except Exception:
#         return []

def rebuild_knowledge_graph(db: Session):
    books = db.query(MyBookshelf).all()

    if len(books) < 2:
        # 1冊だけなら原点に置く（NULL防止）
        if len(books) == 1:
            books[0].x = 0.0
            books[0].y = 0.0
            db.commit()
        return

    # =========================
    # 1. テキスト構築 & ジャンル取得
    # =========================
    texts = []
    for b in books:
        desc = ""
        categories = [] # カテゴリ用
        try:
            r = requests.get(f"{GOOGLE_BOOKS_API}/{b.book_id}", timeout=5)
            if r.status_code == 200:
                volume_info = r.json().get("volumeInfo", {})
                desc = volume_info.get("description", "") or ""
                # Google Books からカテゴリ（ジャンル）を取得
                categories = volume_info.get("categories", [])
        except Exception:
            pass

        texts.append(f"{b.title or ''} {b.author or ''} {desc}")

        # DBpediaがダメでも、Googleのカテゴリがあればそれを使う
        if categories:
            b.concepts = categories
        else:
            if b.concepts is None:
                b.concepts = []
    # =========================
    # 2. TF-IDF → 距離行列
    # =========================
    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words="english"
    )
    X = vectorizer.fit_transform(texts)

    dist = 1.0 - cosine_similarity(X)

    # 数値安定性（まれに負になるのを防ぐ）
    dist = np.clip(dist, 0.0, 1.0)

    # =========================
    # 3. MDS（init は文字列のみ）
    # =========================
    mds = MDS(
        n_components=2,
        metric=True,
        random_state=42,
        n_init=4,
        max_iter=300
    )

    coords = mds.fit_transform(dist)

    # =========================
    # 4. DBへ保存（必ず float）
    # =========================
    for i, b in enumerate(books):
        b.x = float(coords[i, 0])
        b.y = float(coords[i, 1])

    db.commit()

@router.get("/")
def knowledge_graph(db: Session = Depends(get_db)):
    books = db.query(MyBookshelf).all()

    nodes = []
    for b in books:
        if b.x is None or b.y is None:
            continue
        nodes.append({
            "id": b.book_id,
            "label": b.title,
            "author": b.author,
            "cover": b.cover,
            "x": b.x,
            "y": b.y,
            "concepts": b.concepts or []
        })

    # --- 距離計算 ---
    K = 3
    neighbors = {}

    for i, bi in enumerate(books):
        if bi.x is None or bi.y is None:
            continue

        dists = []
        for j, bj in enumerate(books):
            if i == j or bj.x is None or bj.y is None:
                continue

            dx = bi.x - bj.x
            dy = bi.y - bj.y
            dist = (dx**2 + dy**2) ** 0.5
            dists.append((dist, j))

        neighbors[i] = [j for _, j in sorted(dists)[:K]]

    # --- 相互近傍のみエッジ化 ---
    edges = []
    added = set()

    for i, js in neighbors.items():
        for j in js:
            if i in neighbors.get(j, []):
                key = tuple(sorted((books[i].book_id, books[j].book_id)))
                if key in added:
                    continue

                dx = books[i].x - books[j].x
                dy = books[i].y - books[j].y
                dist = (dx**2 + dy**2) ** 0.5

                edges.append({
                    "source": books[i].book_id,
                    "target": books[j].book_id,
                    "weight": float(1 / (dist + 1e-6)),
                    "type": "knn",
                })
                added.add(key)
        
        concept_map = {}
        for b in books:
            if not b.concepts:
                continue
            for c in b.concepts:
                concept_map.setdefault(c, []).append(b)

        for concept, bs in concept_map.items():
            if len(bs) < 2:
                continue
            for i in range(len(bs)):
                for j in range(i + 1, len(bs)):
                    edges.append({
                        "source": bs[i].book_id,
                        "target": bs[j].book_id,
                        "type": "same_concept",
                        "label": concept,
                        "weight": 0.5
                    })

    return {"nodes": nodes, "edges": edges}
