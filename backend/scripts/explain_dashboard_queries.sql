-- Run these in Supabase SQL editor with a real workspace_id substituted
-- Replace 'YOUR-WORKSPACE-UUID' with an actual workspace_id from your database

EXPLAIN ANALYZE
SELECT * FROM daily_campaign_stats
WHERE workspace_id = 'YOUR-WORKSPACE-UUID'
  AND stat_date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE
ORDER BY stat_date;

EXPLAIN ANALYZE  
SELECT * FROM daily_workspace_stats
WHERE workspace_id = 'YOUR-WORKSPACE-UUID'
  AND stat_date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE;

-- These should show Index Scan or Index Only Scan, NOT Seq Scan
-- If you see Seq Scan, the indexes are not being used.
