from pydantic import BaseModel
from typing import TypeVar, Generic, List

T = TypeVar("T")


class ErrorResponse(BaseModel):
    error: dict[str, str | None]


class PaginatedResponse(BaseModel, Generic[T]):
    data: List[T]
    pagination: dict


class HealthResponse(BaseModel):
    status: str
    name: str
    version: str
    git_sha: str
