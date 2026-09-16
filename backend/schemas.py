from pydantic import BaseModel
from typing import List


class AddFromHandRequest(BaseModel):
    isbns: List[str]


class HeightUpdateRequest(BaseModel):
    height_mm: int


class ColorUpdateRequest(BaseModel):
    spine_color: str  # "R,G,B" 形式


class GenreTagRequest(BaseModel):
    tag: str


class PriorityRequest(BaseModel):
    choice: str  # "height" | "genre" | "color" | "author" | "interest" | "none"


class SectionAwarenessRequest(BaseModel):
    is_intentional: bool


class InterestTagRequest(BaseModel):
    tag: str
