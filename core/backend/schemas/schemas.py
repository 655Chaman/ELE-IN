from typing import Optional, Any

from pydantic import BaseModel, Field


# Pipeline requests and responses
class RunPipelineRequest(BaseModel):
    targetLocations: list[str] = Field(default_factory=list, description="List of target locations")
    numLeads: int = Field(default=1000, description="Number of leads to extract/enrich")
    pipelineId: int = Field(default=1, description="The ID of the pipeline instance")

class RunPipelineResponse(BaseModel):
    success: bool
    message: str
    task_id: str

class ErrorResponse(BaseModel):
    error: dict[str, Any]

class StatusResponse(BaseModel):
    status: str
    started_at:Optional[ float ] = None
    completed_at:Optional[ float ] = None
    elapsed_seconds:Optional[ float ] = None

class LogsResponse(BaseModel):
    logs: str

class StatsResponse(BaseModel):
    market: str
    side: str
    raw_count: int
    enriched_count: int

# Keys schemas
class SaveKeyRequest(BaseModel):
    name: str = Field(..., description="The name of the key (e.g. API_KEY)")
    value: str = Field(..., description="The value of the key")

class GenericResponse(BaseModel):
    success: bool
    message: str
