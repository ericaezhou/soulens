from pydantic import BaseModel
from typing import Optional, Any


class AnalyzeRequest(BaseModel):
    instagram_url: str


class JobStatus(BaseModel):
    job_id: str
    status: str  # processing | completed | error
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class EditRequest(BaseModel):
    job_id: str  # ID of the analyzed reel to replicate style from
    footage_job_id: str  # ID of uploaded footage job
