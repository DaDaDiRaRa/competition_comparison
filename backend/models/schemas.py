from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum


class FacilityType(str, Enum):
    public = "public"
    residential = "residential"
    office = "office"
    transport = "transport"
    commercial = "commercial"
    cultural = "cultural"
    hospitality = "hospitality"
    education = "education"
    masterplan = "masterplan"
    industrial = "industrial"
    medical = "medical"
    mixed_use = "mixed_use"


class SubmissionResult(str, Enum):
    win = "win"
    lose = "lose"


class PageClassification(BaseModel):
    page: int
    primary_type: str
    secondary_type: Optional[str] = None
    confidence: float = 0.0
    key_elements: list[str] = []
    error: Optional[str] = None


class SubmissionEntry(BaseModel):
    company: str
    result: SubmissionResult
    filename: str


class ProjectCreateRequest(BaseModel):
    competition_name: str
    facility_type: FacilityType
    year: int
    client: str
    location: str


class DiagnoseRequest(BaseModel):
    facility_type: FacilityType
    competition_name: Optional[str] = None


class ComparisonAxis(BaseModel):
    score: Optional[float] = None
    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendations: list[str] = []
    details: dict[str, Any] = {}


class DiagnosisResult(BaseModel):
    facility_type: str
    competition_name: Optional[str] = None
    total_pages: int
    page_distribution: dict[str, int] = {}
    brief_compliance: dict[str, Any] = {}
    pattern_deviation: dict[str, Any] = {}
    axes: dict[str, ComparisonAxis] = {}
    overall_score: Optional[float] = None
    summary: list[str] = []
    recommendations: list[str] = []
