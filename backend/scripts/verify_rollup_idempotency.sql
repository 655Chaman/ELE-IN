-- Save this as /Users/krdeeksha/Ele-in/backend/scripts/verify_rollup_idempotency.sql
SELECT campaign_id, stat_date, COUNT(*) as row_count
FROM daily_campaign_stats
GROUP BY campaign_id, stat_date
HAVING COUNT(*) > 1;
-- If this returns rows, idempotency is broken.

SELECT workspace_id, stat_date, COUNT(*) as row_count  
FROM daily_workspace_stats
GROUP BY workspace_id, stat_date
HAVING COUNT(*) > 1;
-- If this returns rows, idempotency is broken.
