from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from participant import DEFAULT_PARTICIPANT_ID

class MyHand(Base):
    __tablename__ = "myhand"
    __table_args__ = (
        # 被験者ごとに手札を持つ。別の被験者が同じ本を手札に持てるようにする。
        UniqueConstraint("participant_id", "registered_book_id", name="uq_myhand_participant_book"),
    )

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    participant_id     = Column(String, nullable=False, index=True, default=DEFAULT_PARTICIPANT_ID)
    registered_book_id = Column(Integer, ForeignKey("registered_books.id"), nullable=False)

    book = relationship("RegisteredBook", lazy="joined")

    # RegisteredBook へのプロキシプロパティ（既存コードの互換性維持）
    @property
    def isbn(self):           return self.book.isbn if self.book else None
    @property
    def title(self):          return self.book.title if self.book else None
    @property
    def authors(self):        return self.book.authors if self.book else None
    @property
    def cover(self):          return self.book.cover if self.book else None
    @property
    def spine_image(self):    return self.book.spine_image if self.book else None
    @property
    def publisher(self):      return self.book.publisher if self.book else None
    @property
    def published_year(self): return self.book.published_year if self.book else None
    @property
    def ndc(self):            return self.book.ndc if self.book else None
    @property
    def height_mm(self):      return self.book.height_mm if self.book else None
    @property
    def pages(self):          return self.book.pages if self.book else None
    @property
    def size_label(self):     return self.book.size_label if self.book else None
    @property
    def description(self):    return self.book.description if self.book else None

class ShelfLayout(Base):
    __tablename__ = "shelflayout"
    __table_args__ = (
        # 本棚は被験者ごと。同じISBNを複数の被験者が自分の棚に並べられる。
        UniqueConstraint("participant_id", "isbn", name="uq_shelflayout_participant_isbn"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    participant_id = Column(String, nullable=False, index=True, default=DEFAULT_PARTICIPANT_ID)
    isbn = Column(String, index=True)  # Google Books API の ID

    shelf_index = Column(Integer, nullable=False)
    x_pos = Column(Integer, nullable=False, default=20)  # 左から何番目 (0, 1, 2...)

    # 背表紙描画用 (フロントがそのまま使える)
    height_mm = Column(Integer, default=180) # 本の高さ
    pages = Column(Integer, default=200)     # 厚みの計算用

    # メタ
    cover      = Column(String)
    size_label = Column(String)

    order_index = Column(Integer, nullable=False, default=0)

class RegisteredBook(Base):
    """背表紙画像とNDL書誌情報を紐づけて保存するテーブル"""
    __tablename__ = "registered_books"

    id             = Column(Integer, primary_key=True, index=True, autoincrement=True)
    isbn           = Column(String, unique=True, index=True, nullable=False)
    title          = Column(String)
    authors        = Column(String)        # カンマ区切り
    publisher      = Column(String)
    published_year = Column(String)
    ndc            = Column(String)
    pages          = Column(Integer, default=200)
    height_mm      = Column(Integer, default=180)
    size_label     = Column(String)
    spine_image    = Column(String)        # ローカル背表紙画像パス (/spine_image/{isbn}.jpg)
    spine_color    = Column(String)        # 背表紙の代表色 "R,G,B"
    spine_color_source = Column(String, default="auto_colorthief")  # "auto_colorthief" | "manual"
    height_source  = Column(String, default="ndl_extent")           # "ndl_extent" | "manual"
    cover          = Column(String)        # NDL/Google Books の書影URL
    description    = Column(String)
    registered_at  = Column(DateTime, server_default=func.now())


class GenreTag(Base):
    """本のジャンルタグ（フェーズ1・属性タグ基盤）。

    NDC分類コードは1冊1コードの単一値なので「複数ジャンルを許容する」という
    要件を満たせない。ここでは Concept と同じ思想で participant_id スコープの
    タグ付けにし、1冊に複数タグを持てるようにする。登録時に NDC 由来のラベルを
    origin="ndc_auto" として1件自動シードし、そのうえでユーザーが手動タグを
    追加できる（origin="manual"）。
    """
    __tablename__ = "genre_tag"
    __table_args__ = (
        UniqueConstraint("participant_id", "isbn", "tag", name="uq_genre_tag"),
    )

    id             = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(String, nullable=False, index=True, default=DEFAULT_PARTICIPANT_ID)
    isbn           = Column(String, ForeignKey("registered_books.isbn"), nullable=False, index=True)
    tag            = Column(String, nullable=False)
    origin         = Column(String, nullable=False, default="manual")  # "ndc_auto" | "manual"
    created_at     = Column(DateTime, server_default=func.now())


class ShelfDesign(Base):
    __tablename__ = "shelfdesign"
    id = Column(Integer, primary_key=True, index=True)
    # 棚の段数などの設定も被験者ごとに1行持つ
    participant_id = Column(String, nullable=False, unique=True, index=True, default=DEFAULT_PARTICIPANT_ID)
    shelf_size = Column(Integer)
    total_shelves = Column(Integer)
    last_forced_concept_count = Column(Integer, default=0)  # 前回「強制対話」を行った時点のConceptノード累計数


class ExperimentConfig(Base):
    """実験フロー制御の設定（4章）。常に1行のみ運用するグローバル設定
    （ShelfDesignのような参加者ごとの行ではない）。研究者がコード修正なしで
    試行数・条件配分・対照ペアの混入数を調整できるようにするための設定値。"""
    __tablename__ = "experiment_config"

    id = Column(Integer, primary_key=True, index=True)
    phase1_trial_count = Column(Integer, nullable=False, default=5)       # 4〜6件
    transfer_trial_count = Column(Integer, nullable=False, default=1)     # 1〜2件
    contrastive_pair_count = Column(Integer, nullable=False, default=1)   # phase1のうち対照ペアを何件混ぜるか
    # "participant": 参加者ごとに1回だけexperimental/controlを抽選しphase1全件に適用
    # "trial":       試行ごとに毎回抽選
    condition_assignment_mode = Column(String, nullable=False, default="participant")
    condition_ratio = Column(Float, nullable=False, default=0.5)          # experimentalになる確率
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TrialAssignment(Base):
    """参加者(viewer)ごとの試行割り当て（刺激本棚の持ち主・表示順・フェーズ・条件）。
    experiment.assignment.generate_assignments が生成する。"""
    __tablename__ = "trial_assignment"
    __table_args__ = (
        UniqueConstraint("participant_id", "owner_id", name="uq_trial_assignment_participant_owner"),
    )

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(String, nullable=False, index=True)  # viewer
    owner_id = Column(String, nullable=False)                    # 刺激本棚の持ち主
    trial_index = Column(Integer, nullable=False)                # 参加者内での表示順（0始まり）
    phase = Column(String, nullable=False)                       # "phase1" | "phase2"
    condition = Column(String, nullable=False)                   # "experimental" | "control" | "transfer"
    created_at = Column(DateTime, server_default=func.now())


# ============================================================
# フェーズ2: 意図を明示的に聞く機能（最小構成）
#
# (a)(b)(c) いずれも、暗黙の優先度推定(PlacementProfile/DesignEvidence)を
# 一切見せずに回答させる自己申告データ。participant_id で ShelfLayout・
# RegisteredBook・GenreTag と突き合わせられるようにする。
# ============================================================

class PriorityResponse(Base):
    """(a) 優先度質問。「一番意識したのは何か」の単一選択。
    PlacementProfile と同じく上書きせず追記保存し、最新の回答を
    routers.intent_survey が取り出す（回答し直した履歴も残せるように）。"""
    __tablename__ = "priority_response"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(String, nullable=False, index=True, default=DEFAULT_PARTICIPANT_ID)
    # "height" | "genre" | "color" | "author" | "interest" | "none"
    choice         = Column(String, nullable=False)
    created_at     = Column(DateTime, server_default=func.now())


class SectionBoundary(Base):
    """(b) 区切り確認。段(shelf_index)ではなく、本と本の「間」ごとに
    「ここは意識して区切った」をON/OFFでタップ選択する。自由な線引きはさせない。
    gap_index は、その段の中で左から数えた区切りの位置（0始まり。本Aと本Bの間なら0）。
    left_isbn/right_isbn は回答時点でその位置にあった本を記録しておき、後で配置が
    変わっても「どの本とどの本の間だったか」を追える形にする。"""
    __tablename__ = "section_boundary"
    __table_args__ = (
        UniqueConstraint("participant_id", "shelf_index", "gap_index", name="uq_section_boundary"),
    )

    id              = Column(Integer, primary_key=True, autoincrement=True)
    participant_id  = Column(String, nullable=False, index=True, default=DEFAULT_PARTICIPANT_ID)
    shelf_index     = Column(Integer, nullable=False)
    gap_index       = Column(Integer, nullable=False)
    left_isbn       = Column(String, nullable=False)
    right_isbn      = Column(String, nullable=False)
    is_intentional  = Column(Boolean, nullable=False, default=False)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())


class InterestTag(Base):
    """(c) 興味分野質問。配置画面とは完全に独立した画面でのみ回答させる
    （アンカリング防止のため、配置操作の前後どちらでも同時に見せない）。

    タグの選択肢は固定語彙ではなく、現在棚に並んでいる本のジャンルタグ
    （GenreTag、フェーズ1参照）から動的に作る。rank はタップした順番＝
    興味の強い順（1が最も興味が強い）。フルランキングを強制するのではなく、
    「興味がある分だけタップする」形にして負荷を抑える。"""
    __tablename__ = "interest_tag"
    __table_args__ = (
        UniqueConstraint("participant_id", "tag", name="uq_interest_tag"),
    )

    id             = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(String, nullable=False, index=True, default=DEFAULT_PARTICIPANT_ID)
    tag            = Column(String, nullable=False)
    rank           = Column(Integer, nullable=False)
    created_at     = Column(DateTime, server_default=func.now())