
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataQualityIssueStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["OPEN", "INVESTIGATING", "RESOLVED", "IGNORED"]
    note: str | None = Field(default=None, max_length=2000)
