from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class MyHand(Base):
    __tablename__ = "myhand"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    registered_book_id = Column(Integer, ForeignKey("registered_books.id"), unique=True, nullable=False)

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
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    isbn = Column(String, unique=True, index=True)  # Google Books API の ID

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
    cover          = Column(String)        # NDL/Google Books の書影URL
    description    = Column(String)
    registered_at  = Column(DateTime, server_default=func.now())


class ShelfDesign(Base):
    __tablename__ = "shelfdesign"
    id = Column(Integer, primary_key=True, index=True)
    shelf_size = Column(Integer)
    total_shelves = Column(Integer)