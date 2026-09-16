from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
from migrations import run_migrations
from graph.main_kg.neo4j_migrate import run_neo4j_migrations
from graph.style_projection.schema import ensure_style_projection_schema
from graph.experiment.schema import ensure_experiment_schema
from graph.placement_analysis.schema import ensure_placement_analysis_schema
from graph.uiab_experiment.schema import ensure_uiab_experiment_schema
import routers.myhand as myhand_router
import routers.knowledge_graph as knowledge_graph_router
import routers.bookshelf as bookshelf_router
import routers.search as search_router
import routers.register as register_router
import routers.participants as participants_router
import routers.style_projection as style_projection_router
import routers.experiment as experiment_router
import routers.placement_analysis as placement_analysis_router
import routers.intent_survey as intent_survey_router
import routers.uiab_experiment as uiab_experiment_router
from routers.search import lifespan

# DB初期化（未作成のテーブルを新スキーマで作る → 既存テーブルを移行する、の順）
Base.metadata.create_all(bind=engine)
run_migrations(engine)
run_neo4j_migrations()
try:
    ensure_style_projection_schema()
except Exception as e:
    # Neo4jが起動していなくてもAPIサーバは立ち上げたいので、警告に留める
    # （run_neo4j_migrationsと同じ方針）。
    import logging
    logging.getLogger(__name__).warning("投影スタイル分析システムのスキーマ初期化をスキップしました: %s", e)
try:
    ensure_experiment_schema()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning("実験運用システムのスキーマ初期化をスキップしました: %s", e)
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
    ensure_uiab_experiment_schema()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning("新旧UI比較実験のスキーマ初期化をスキップしました: %s", e)

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
app.include_router(participants_router.router)
app.include_router(style_projection_router.router)
app.include_router(experiment_router.router)
app.include_router(placement_analysis_router.router)
app.include_router(intent_survey_router.router)
app.include_router(uiab_experiment_router.router)

@app.get("/")
def root():
    return {"message": "Stable Mode Running"}