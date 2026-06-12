from typing import Any, Optional

from pydantic import BaseModel, Field


class CitizenProfile(BaseModel):
    age: Optional[int] = Field(default=None, ge=0)
    state: Optional[str] = None
    occupation: Optional[str] = None
    income: Optional[int] = Field(default=None, ge=0)
    category: Optional[str] = None
    gender: Optional[str] = None


class AskRequest(BaseModel):
    question: str = Field(min_length=2)
    profile: CitizenProfile = Field(default_factory=CitizenProfile)
    top_k: int = Field(default=3, ge=1, le=5)
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class Scheme(BaseModel):
    id: str
    name: str
    category: str
    states: list[str]
    summary: str
    benefits: list[str]
    eligibility: dict[str, Any]
    documents: list[str]
    apply_steps: list[str]
    source_title: str
    source_url: str
    official_sources: list[str] = Field(default_factory=list)
    official_excerpt: str = ""
