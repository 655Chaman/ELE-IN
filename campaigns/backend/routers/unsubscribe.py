import html
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from campaigns.backend.services.unsubscribe_service import (
    verify_unsubscribe_token,
    process_one_click_unsubscribe,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["unsubscribe"])


def _render_unsubscribe_confirmation_html(email: Optional[str] = None) -> str:
    """
    Paranoia Layer 2: Clean, responsive, dark-mode-ready confirmation card.
    Zero tracking scripts, zero cookies, zero external network fonts or CSS.
    """
    display_email = html.escape(str(email or "").strip().lower())
    email_line = (
        f'<p class="email-badge">{display_email}</p>'
        if display_email
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unsubscribed — Ele-in</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --border: #e2e8f0;
      --text: #0f172a;
      --text-muted: #64748b;
      --success: #10b981;
      --success-bg: #ecfdf5;
      --badge-bg: #f1f5f9;
      --badge-border: #cbd5e1;
      --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.05);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #090d16;
        --card-bg: #111827;
        --border: #1f2937;
        --text: #f9fafb;
        --text-muted: #9ca3af;
        --success: #34d399;
        --success-bg: rgba(16, 185, 129, 0.12);
        --badge-bg: #1e293b;
        --badge-border: #334155;
        --shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
      }}
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1.5rem;
      transition: background-color 0.2s ease, color 0.2s ease;
    }}
    .card {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 1rem;
      box-shadow: var(--shadow);
      max-width: 480px;
      width: 100%;
      padding: 2.5rem 2rem;
      text-align: center;
      animation: fadeIn 0.3s ease-out;
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .icon-wrapper {{
      width: 64px;
      height: 64px;
      border-radius: 50%;
      background-color: var(--success-bg);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 1.5rem;
    }}
    .icon-wrapper svg {{
      width: 32px;
      height: 32px;
      color: var(--success);
    }}
    h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: -0.025em;
      margin-bottom: 0.75rem;
    }}
    p.message {{
      font-size: 1rem;
      line-height: 1.5;
      color: var(--text);
      margin-bottom: 1rem;
    }}
    p.email-badge {{
      display: inline-block;
      font-size: 0.875rem;
      font-weight: 500;
      color: var(--text-muted);
      background-color: var(--badge-bg);
      border: 1px solid var(--badge-border);
      padding: 0.25rem 0.75rem;
      border-radius: 0.375rem;
      margin-bottom: 1.25rem;
      word-break: break-all;
    }}
    p.subtext {{
      font-size: 0.875rem;
      line-height: 1.4;
      color: var(--text-muted);
      margin-bottom: 1.75rem;
    }}
    .footer-pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      border: 1px solid var(--border);
      padding: 0.4rem 0.85rem;
      border-radius: 9999px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon-wrapper">
      <svg fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
      </svg>
    </div>
    <h1>Unsubscribed</h1>
    <p class="message">You have been successfully unsubscribed from this campaign.</p>
    {email_line}
    <p class="subtext">You will no longer receive sequence emails or automated follow-ups for this campaign.</p>
    <div class="footer-pill">
      <span>Ele-in &bull; RFC 8058 One-Click Compliant</span>
    </div>
  </div>
</body>
</html>"""


@router.post("/unsubscribe", summary="RFC 8058 One-Click Unsubscribe (POST)")
async def rfc8058_unsubscribe_post(
    request: Request,
    token: Optional[str] = Query(None),
):
    """
    RFC 8058 One-Click Unsubscribe POST endpoint.
    Invoked by Mail User Agents (Gmail, Yahoo, Apple Mail) upon clicking Unsubscribe.
    MUA sends POST with form data 'List-Unsubscribe=One-Click'.
    Validates cryptographic token and executes immediate unsubscription with zero confirmation friction.
    """
    resolved_token = token
    if not resolved_token:
        resolved_token = request.query_params.get("token")

    if not resolved_token:
        try:
            content_type = request.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                body_json = await request.json()
                if isinstance(body_json, dict):
                    resolved_token = body_json.get("token")
            elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                form = await request.form()
                resolved_token = form.get("token")
        except Exception:
            pass

    if not resolved_token or not isinstance(resolved_token, str):
        raise HTTPException(
            status_code=400,
            detail="Invalid or missing unsubscribe token.",
        )

    verified = verify_unsubscribe_token(resolved_token)
    if not verified:
        raise HTTPException(
            status_code=400,
            detail="Invalid or tampered unsubscribe token.",
        )

    try:
        process_one_click_unsubscribe(
            workspace_id=verified["workspace_id"],
            lead_id=verified["lead_id"],
            email=verified["email"],
        )
    except Exception as exc:
        logger.error(f"[UnsubscribeRouter] POST unsubscribe execution failed: {exc}")

    return {"status": "success", "message": "Successfully unsubscribed"}


@router.get("/unsubscribe", summary="RFC 8058 Unsubscribe Confirmation (GET)", response_class=HTMLResponse)
async def rfc8058_unsubscribe_get(
    request: Request,
    token: Optional[str] = Query(None),
):
    """
    Unsubscribe GET endpoint for human clickers navigating from email footers or browsers.
    Validates cryptographic token, processes unsubscription, and displays an accessible,
    responsive confirmation card.
    """
    resolved_token = token or request.query_params.get("token")

    if not resolved_token or not isinstance(resolved_token, str):
        raise HTTPException(
            status_code=400,
            detail="Invalid or missing unsubscribe token.",
        )

    verified = verify_unsubscribe_token(resolved_token)
    if not verified:
        raise HTTPException(
            status_code=400,
            detail="Invalid or tampered unsubscribe token.",
        )

    # Paranoia Layer 1: Anti-Scanner / Pre-fetch Defense
    # Security scanners (Proofpoint, Defender, Mimecast) send GET prefetch probes.
    # If a pre-fetch header is detected, render confirmation without mutating state.
    is_prefetch = any(
        request.headers.get(h, "").lower() in ("prefetch", "preview")
        for h in ("purpose", "sec-purpose", "x-purpose", "x-moz")
    )
    if is_prefetch:
        logger.info(f"[UnsubscribeRouter] Pre-fetch scanner header detected for {verified.get('email')}; skipping unsubscribe execution.")
        html_content = _render_unsubscribe_confirmation_html(verified.get("email"))
        return HTMLResponse(content=html_content, status_code=200)

    try:
        process_one_click_unsubscribe(
            workspace_id=verified["workspace_id"],
            lead_id=verified["lead_id"],
            email=verified["email"],
        )
    except Exception as exc:
        logger.error(f"[UnsubscribeRouter] GET unsubscribe execution failed: {exc}")

    html_content = _render_unsubscribe_confirmation_html(verified.get("email"))
    return HTMLResponse(content=html_content, status_code=200)
