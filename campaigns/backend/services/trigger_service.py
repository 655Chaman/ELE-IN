"""
Trigger Service
Manages incoming webhooks and schedule-based triggers for workflows.
"""

from typing import Optional, Any

import structlog

from core.backend.services.workflow_executor import execute_workflow_sync
from core.backend.services.workflow_service import get_workflow

logger = structlog.get_logger()

def trigger_workflow_by_webhook(workflow_id: str, payload: dict[str, Any]) ->Optional[ str ]:
    """
    Trigger a workflow from an inbound webhook payload.
    The payload becomes the initial seed context.
    """
    wf = get_workflow(workflow_id)
    if not wf:
        logger.warning("trigger.webhook.workflow_not_found", workflow_id=workflow_id)
        return None

    # Check if this workflow actually has a webhook trigger node
    has_webhook_trigger = any(node.type == "trigger_webhook" for node in wf.definition.nodes)
    if not has_webhook_trigger:
        logger.warning("trigger.webhook.no_webhook_node", workflow_id=workflow_id)
        return None

    # Seed context contains the payload under "webhook" key
    # so downstream nodes can use {{webhook.body}} or similar
    seed_context = {
        "webhook": {
            "payload": payload
        }
    }

    run_id = execute_workflow_sync(workflow_id, seed_context)
    logger.info("trigger.webhook.started", workflow_id=workflow_id, run_id=run_id)
    return run_id
