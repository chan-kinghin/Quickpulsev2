"""Error response models for API."""

from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
