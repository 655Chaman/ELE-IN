# Ele-in MCP Server

A standalone Python Model Context Protocol (MCP) server that exposes Ele-in's outreach engine capabilities to AI agents.

## Features
- **Stateless & Database-Anchored**: Every call reads/writes directly to Supabase. No shared mutable state.
- **Secure**: All tool calls require an active Ele-in API key validated via SHA-256 hash matching.
- **Paranoia-driven**: Built with 3-layer security framework (Layer 1 timeout/fallback protection, Layer 2 abuse mitigation).

## Available Tools

1. **`elein_list_campaigns`**
   - **Input:** `{ "status": "active|paused|draft" }` (optional)
   - **Output:** Array of campaign objects.
   - **Security:** Hard-filtered by workspace ID. Agents cannot see other workspaces.

2. **`elein_enroll_leads`**
   - **Input:** `{ "campaign_id": "uuid", "leads": [{"email": "...", "linkedin_url": "...", "first_name": "..."}] }`
   - **Output:** `{ "enrolled": int, "skipped": int, "collision_skipped": int }`
   - **Security:** Rate limited to 500 leads per call. Validates global workspace collisions natively.

3. **`elein_get_campaign_analytics`**
   - **Input:** `{ "campaign_id": "uuid" }`
   - **Output:** Aggregated engagement stats (enrolled, sent, replies). Safe fallback to zeroes.

4. **`elein_pause_campaign` / `elein_resume_campaign`**
   - **Input:** `{ "campaign_id": "uuid" }`
   - **Output:** `{ "status": "success", "new_state": "..." }`

5. **`elein_get_lead_status`**
   - **Input:** `{ "lead_id": "...", "email": "...", "linkedin_url": "..." }` (at least one)
   - **Output:** Array of enrollments for this lead.

6. **`elein_score_lead_icp`**
   - **Input:** `{ "profile": { ... } }` (LinkedIn profile JSON)
   - **Output:** `{ "score": "...", "reasoning": "..." }`
   - **Security:** 10-second timeout bound to prevent AI service hangs.

## Installation & Setup

1. Install dependencies:
   ```bash
   cd /Users/krdeeksha/Ele-in
   python3 -m pip install -r requirements.txt
   ```

2. Generate an API Key:
   In your browser or via API, hit `/api/integrations/api-keys` (handled in `integrations/backend/routers/api_keys.py`) to generate a new key.

3. Configure Claude Desktop (or other MCP Client):
   Add the following to your `claude_desktop_config.json`:
   
   ```json
   {
     "mcpServers": {
       "elein-engine": {
         "command": "/bin/bash",
         "args": [
           "/Users/krdeeksha/Ele-in/mcp/start.sh"
         ],
         "env": {
           "SUPABASE_URL": "your_supabase_url",
           "SUPABASE_SERVICE_ROLE_KEY": "your_service_role_key",
           "ELEIN_API_KEY": "el_live_..."
         }
       }
     }
   }
   ```
