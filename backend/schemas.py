from pydantic import BaseModel
from typing import List


class AddFromHandRequest(BaseModel):
    isbns: List[str]
