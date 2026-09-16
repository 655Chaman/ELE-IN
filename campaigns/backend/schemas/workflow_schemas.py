from typing import Optional, Any

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────
# Node & Edge primitives (mirrors React Flow format)
# ─────────────────────────────────────────────────

class NodePosition(BaseModel):
    x: float
    y: float


class WorkflowNode(BaseModel):
    id: str
    type: str                          # matches NODE_REGISTRY key
    position: NodePosition
    data: dict[str, Any] = Field(default_factory=dict)  # node-specific config


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle:Optional[ str ] = None
    targetHandle:Optional[ str ] = None
    label:Optional[ str ] = None


# ─────────────────────────────────────────────────
# Full workflow definition (stored as JSON in DB)
# ─────────────────────────────────────────────────

class WorkflowDefinition(BaseModel):
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


# ─────────────────────────────────────────────────
# REST payloads
# ─────────────────────────────────────────────────

class CreateWorkflowRequest(BaseModel):
    name: str
    description:Optional[ str ] = ""
    definition: WorkflowDefinition = Field(default_factory=WorkflowDefinition)


class UpdateWorkflowRequest(BaseModel):
    name:Optional[ str ] = None
    description:Optional[ str ] = None
    definition:Optional[ WorkflowDefinition ] = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    definition: WorkflowDefinition
    version: int
    is_active: bool
    created_at: str
    updated_at: str


# ─────────────────────────────────────────────────
# Workflow Run payloads
# ─────────────────────────────────────────────────

class RunWorkflowRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)   # optional seed data


class WorkflowRunResponse(BaseModel):
    run_id: str
    workflow_id: str
    status: str
    started_at:Optional[ str ] = None
    finished_at:Optional[ str ] = None
    node_states: dict[str, Any] = Field(default_factory=dict)
    error:Optional[ str ] = None
