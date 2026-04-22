from sqlalchemy import Column, Integer, String, Float, JSON
from database import Base

class MyHand(Base):
    __tablename__ = "myhand"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    isbn = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    authors = Column(String)  # カンマ区切りの文字列として保存
    cover = Column(String)    # 画像URL
    
    # --- 追加項目: 詳細データ ---
    publisher = Column(String)      # 出版社
    published_year = Column(String) # 出版年
    ndc = Column(String)            # 日本十進分類法 (NDC) のコード
    
    # --- 追加項目: 物理サイズ (本棚の描画に必須) ---
    height_mm = Column(Integer, default=180) # 本の高さ
    pages = Column(Integer, default=200)     # 厚みの計算用
    size_label = Column(String)              # 「A5」「文庫」などの名称

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

class ShelfDesign(Base):
    __tablename__ = "shelfdesign"
    id = Column(Integer, primary_key=True, index=True)
    shelf_size = Column(Integer)
    total_shelves = Column(Integer)