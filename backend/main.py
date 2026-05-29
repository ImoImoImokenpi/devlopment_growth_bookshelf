from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import Base, engine
import routers.myhand as myhand_router
import routers.knowledge_graph as knowledge_graph_router
import routers.bookshelf as bookshelf_router
import routers.search as search_router
import routers.register as register_router
from routers.search import lifespan

# DB初期化
Base.metadata.create_all(bind=engine)

# spine_color カラムが存在しない場合に追加（既存DB向けマイグレーション）
with engine.connect() as _conn:
    try:
        _conn.execute(text("ALTER TABLE registered_books ADD COLUMN spine_color VARCHAR"))
        _conn.commit()
    except Exception:
        pass  # カラムが既に存在する場合は無視

app = FastAPI(lifespan=lifespan)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルータ登録
app.include_router(myhand_router.router)
app.include_router(knowledge_graph_router.router)
app.include_router(bookshelf_router.router)
app.include_router(search_router.router)
app.include_router(register_router.router)

@app.get("/")
def root():
    return {"message": "Stable Mode Running"}