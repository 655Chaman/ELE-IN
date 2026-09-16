# Phase B Deployment Sequence

1. Run **Migration A**
2. Run **Migration B**
3. **Deploy writer version** of the application
4. **Independently verify writer** is deployed and writing workspace_id (Do NOT infer merely from repository code; perform operational verification on the running application).
5. **Pre-backfill SQL readiness check**: Verify campaign_enrollments has no NULL workspace_id records:
   ```sql
   SELECT count(*)
   FROM public.campaign_enrollments
   WHERE workspace_id IS NULL;
   -- Must return 0
   ```
6. Run bounded backfill (`python3 backend/scripts/phase_b_backfill.py`)
7. **Post-backfill verification 1**: Verify campaign_execution_states has no NULL workspace_id records:
   ```sql
   SELECT count(*)
   FROM public.campaign_execution_states
   WHERE workspace_id IS NULL;
   -- Must return 0
   ```
8. **Post-backfill verification 2**: Verify every CES workspace_id exactly matches its enrollment workspace_id:
   ```sql
   SELECT count(*)
   FROM public.campaign_execution_states ces
   JOIN public.campaign_enrollments ce ON ces.enrollment_id = ce.id
   WHERE ces.workspace_id != ce.workspace_id;
   -- Must return 0
   ```
9. Run **Migration C**
10. Run **Migration D**
11. Run **Migration E**
12. Run **Migration F1/F2**
