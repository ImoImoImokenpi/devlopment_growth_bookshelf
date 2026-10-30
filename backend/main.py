from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
from migrations import run_migrations
from graph.main_kg.neo4j_migrate import run_neo4j_migrations
from graph.placement_analysis.schema import ensure_placement_analysis_schema
from graph.dialogue.schema import ensure_dialogue_schema
import routers.myhand as myhand_router
import routers.knowledge_graph as knowledge_graph_router
import routers.bookshelf as bookshelf_router
import routers.register as register_router
import routers.dialogue as dialogue_router
from routers.search import lifespan

# DB初期化（未作成のテーブルを新スキーマで作る → 既存テーブルを移行する、の順）
Base.metadata.create_all(bind=engine)
run_migrations(engine)
run_neo4j_migrations()
# Neo4jが起動していなくてもAPIサーバは立ち上げたいので、スキーマ初期化の失敗は警告に留める
# （run_neo4j_migrationsと同じ方針）。
try:
    ensure_placement_analysis_schema()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning("本棚配置分析システムのスキーマ初期化をスキップしました: %s", e)
try:
    from database import SessionLocal
    from routers.register import backfill_genre_tags_from_ndc
    _db = SessionLocal()
    try:
        backfill_genre_tags_from_ndc(_db)
    finally:
        _db.close()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning("ジャンルタグの穴埋めをスキップしました: %s", e)
try:
    ensure_dialogue_schema()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning("本棚対話のスキーマ初期化をスキップしました: %s", e)

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
app.include_router(dialogue_router.router)
app.include_router(bookshelf_router.router)
app.include_router(register_router.router)

@app.get("/")
def root():
    return {"message": "Stable Mode Running"}