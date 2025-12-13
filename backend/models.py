from sqlalchemy import Column, Integer, String, DateTime
from database import Base

class MyHand(Base):
    __tablename__ = "myhand"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    book_id = Column(String, unique=True, index=True)  # Google Books API の ID
    title = Column(String)
    author = Column(String)
    cover = Column(String)

class MyBookshelf(Base):
    __tablename__ = "mybookshelf"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    book_id = Column(String, unique=True, index=True)  # Google Books API の ID
    title = Column(String)
    author = Column(String)
    cover = Column(String)