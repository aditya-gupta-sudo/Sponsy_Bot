
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Event(BaseModel):
    event_name: str
    college: str
    city: str
    state: str
    event_date: date
    expected_participants: int = Field(gt=0)
    event_type: str
    description: str
    sponsorship_requirements: list[str] = Field(default_factory=list)

    # Audience profile
    age_groups: list[str] = Field(default_factory=list)
    audience_types: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)

    geographic_reach: str | None = None

    spending_profile: Literal[
        "unknown", "low", "moderate", "high"
    ] = "unknown"

    event_format: Literal[
        "on-campus", "off-campus", "online", "hybrid"
    ] | None = None
