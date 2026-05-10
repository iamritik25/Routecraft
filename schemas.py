"""
Pydantic v2 request/response schemas for RouteCraft API.
All incoming JSON is validated here before touching business logic.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

VALID_PREFERENCES = {"cheapest", "fastest", "balanced"}
VALID_WEATHERS = {"Clear", "Light Rain", "Rain", "Heavy Rain", "Fog", "Windy", "Overcast"}


class RouteRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=200, description="Origin location name or address")
    destination: str = Field(..., min_length=1, max_length=200, description="Destination location name or address")
    preference: str = Field("balanced", description="Route optimisation preference")
    weather: str = Field("Clear", description="Current weather condition")
    hour: int = Field(9, ge=0, le=23, description="Departure hour (0-23)")

    @field_validator("preference")
    @classmethod
    def validate_preference(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_PREFERENCES:
            raise ValueError(f"preference must be one of: {sorted(VALID_PREFERENCES)}")
        return v

    @field_validator("weather")
    @classmethod
    def validate_weather(cls, v: str) -> str:
        v = v.strip()
        if v not in VALID_WEATHERS:
            raise ValueError(f"weather must be one of: {sorted(VALID_WEATHERS)}")
        return v

    @field_validator("source", "destination")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class EdgeResponse(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    description: str
    time_min: float
    cost: float

    model_config = {"populate_by_name": True}


class RouteVariant(BaseModel):
    label: str
    path: List[str]
    condensed_path: List[str]
    modes: List[str]
    edges: List[Dict[str, Any]]
    total_cost: Optional[float]
    total_time: Optional[float]
    eta_p10: Optional[float] = None
    eta_p50: Optional[float] = None
    eta_p90: Optional[float] = None
    eta_confidence: Optional[str] = None


class MLSummary(BaseModel):
    used: bool
    hits: int
    heuristic_hits: int
    backend: Optional[str]
    areas: List[str]


class SurgeInfo(BaseModel):
    multiplier: float
    label: str


class RouteResponse(BaseModel):
    cheapest: RouteVariant
    fastest: RouteVariant
    balanced: RouteVariant
    cab_only: RouteVariant
    metro_only: RouteVariant
    metro_plus_cab: RouteVariant
    bus_only: RouteVariant
    preferred: str
    ml: MLSummary
    surge: SurgeInfo


class JobCreated(BaseModel):
    job_id: str
    status: str
    poll_url: str
    message: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    ml_model: str
    graph_cache_size: int
    cache_backend: str
    uptime_seconds: float


class MetricsResponse(BaseModel):
    total_requests: int
    cache_hits: int
    cache_misses: int
    avg_response_ms: float
    ml_hit_rate: float
    ab_backend_counts: Dict[str, int]
