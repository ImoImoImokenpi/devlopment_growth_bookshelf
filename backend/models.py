from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from participant import DEFAULT_PARTICIPANT_ID
from shelf_period import DEFAULT_PERIOD

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
    """本棚上の「1冊」。棚には同じISBNの本を複数冊（同じ本を2冊など）置けるため、
    (participant_id, period, isbn) を一意にはしない——1行=1冊の物理的な配置で、
    どの本の物理的な1冊かは行の id で区別する（isbnは「どの本か」を表すだけ）。"""
    __tablename__ = "shelflayout"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    participant_id = Column(String, nullable=False, index=True, default=DEFAULT_PARTICIPANT_ID)
    period = Column(String, nullable=False, index=True, default=DEFAULT_PERIOD)  # "past" | "present"
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
    __table_args__ = (
        # 棚の段数などの設定は被験者×時期ごとに1行持つ（過去/現在で段数が違ってよい）。
        UniqueConstraint("participant_id", "period", name="uq_shelfdesign_participant_period"),
    )
    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(String, nullable=False, index=True, default=DEFAULT_PARTICIPANT_ID)
    period = Column(String, nullable=False, index=True, default=DEFAULT_PERIOD)  # "past" | "present"
    shelf_size = Column(Integer)
    total_shelves = Column(Integer)
    last_forced_concept_count = Column(Integer, default=0)  # 前回「強制対話」を行った時点のConceptノード累計数
