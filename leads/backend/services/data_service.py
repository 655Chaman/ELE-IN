import os
from typing import Optional, Any

import pandas as pd
import structlog

from core.backend.services.pipeline_service import get_pipeline_csv_path

logger = structlog.get_logger()

def get_live_csv_data(market: str, side: str, stage: int, limit: int = 50) -> list[dict[str, Any]]:
    enriched = (stage == 2)
    # Defaulting to pipeline_id=1 for now, as that's what the current dashboard runs
    file_path = get_pipeline_csv_path(market, side, enriched=enriched, pipeline_id=1)
    
    if not file_path or not os.path.exists(file_path):
        return []

    try:
        df = pd.read_csv(file_path, on_bad_lines='skip')
        # Get the last `limit` rows so the user sees the newest appended data
        tail_df = df.tail(limit).fillna("")
        
        # Reverse to show newest on top (optional, but good for "live" feel)
        tail_df = tail_df.iloc[::-1]
        
        return tail_df.to_dict(orient="records")
    except Exception as e:
        logger.error("live_csv_read_failed", error=str(e), path=file_path)
        return []
