from fastapi import FastAPI
from pydantic import BaseModel
import networkx as nx

app = FastAPI()
G = nx.Graph()

class Book(BaseModel):
    title: str
    authors: list[str] | None = None
    description: str | None = None

@app.post("/add_book")
def add_book(book: Book):
    G.add_node(book.title, type="book")
    if book.authors:
        for a in book.authors:
            G.add_node(a, type="author")
            G.add_edge(book.title, a, relation="writtenBy")

    return {"message": f"{book.title} added"}
