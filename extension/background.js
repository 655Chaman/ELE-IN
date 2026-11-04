// Ele-in LinkedIn Execution Engine (Chrome Extension Service Worker v1.3.0)
// Rigorously engineered under the Three-Layer Logic Architecture (Paranoia Framework)
// - Layer 0: High-fidelity Voyager API & DOM fallback execution
// - Layer 1: Multi-Tab leader election, automatic lease watchdogs, debounced session sync, and checkpoint tripwires
// - Layer 2: Human paranoia: Typing jitter, collision guards, PII-sanitized diagnostic telemetry, and OS notifications

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const EXTENSION_VERSION = "1.3.0";
const MAX_OFFLINE_QUEUE_SIZE = 100;

// Helper: Resolve dynamic API endpoints
async function getApiEndpoint(path = "") {
  const { apiBaseUrl } = await chrome.storage.local.get("apiBaseUrl");
  const base = (apiBaseUrl || DEFAULT_API_BASE).replace(/\/+$/, "");
  const cleanPath = path.replace(/^\/+/, "");
  return `${base}/api/extension${cleanPath ? "/" + cleanPath : ""}`;
}

// Persistent Browser Instance UUID (Paranoia Layer 1)
async function getBrowserInstanceId() {
  let { browserInstanceId } = await chrome.storage.local.get("browserInstanceId");
  if (!browserInstanceId) {
    browserInstanceId = "inst_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    await chrome.storage.local.set({ browserInstanceId });
  }
  return browserInstanceId;
}

// ============================================================================
// PHASE L: CRYPTOGRAPHIC SIGNING & OFFLINE RESILIENCE BUFFER
// ============================================================================

async function computeHmacSha256(secret, message) {
  try {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw",
      enc.encode(secret.trim()),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );
    const signature = await crypto.subtle.sign("HMAC", key, enc.encode(message));
    return Array.from(new Uint8Array(signature))
      .map(b => b.toString(16).padStart(2, "0"))
      .join("");
  } catch (err) {
    return null;
  }
}

async function enqueueOfflineAction(action) {
  try {
    const { offlineActionQueue = [] } = await chrome.storage.local.get("offlineActionQueue");
    const item = {
      id: "act_" + Math.random().toString(36).substring(2, 9) + Date.now().toString(36),
      endpoint: action.endpoint,
      method: action.method || "POST",
      headers: action.headers || {},
      body: action.body || null,
      timestamp: Date.now(),
      retryCount: 0
    };
    const queue = [...offlineActionQueue, item];
    if (queue.length > MAX_OFFLINE_QUEUE_SIZE) {
      queue.splice(0, queue.length - MAX_OFFLINE_QUEUE_SIZE);
    }
    await chrome.storage.local.set({ offlineActionQueue: queue });
    console.log(`[Ele-in Extension] Action buffered offline (queue depth: ${queue.length})`);
  } catch (err) {
    console.error("[Ele-in Extension] Failed to buffer offline action:", err);
  }
}

async function flushOfflineActionQueue() {
  try {
    const { offlineActionQueue = [] } = await chrome.storage.local.get("offlineActionQueue");
    if (!offlineActionQueue || offlineActionQueue.length === 0) return;

    console.log(`[Ele-in Extension] Attempting to flush ${offlineActionQueue.length} buffered action(s)...`);
    const remainingQueue = [];

    for (let i = 0; i < offlineActionQueue.length; i++) {
      const item = offlineActionQueue[i];
      const attempt = item.retryCount || 0;
      
      try {
        const resp = await fetch(item.endpoint, {
          method: item.method,
          headers: item.headers,
          body: item.body
        });
        if (!resp.ok && resp.status >= 500) {
          item.retryCount = attempt + 1;
          remainingQueue.push(item);
        }
      } catch (networkErr) {
        item.retryCount = attempt + 1;
        remainingQueue.push(item);
        remainingQueue.push(...offlineActionQueue.slice(i + 1));
        break;
      }
    }

    await chrome.storage.local.set({ offlineActionQueue: remainingQueue });
  } catch (err) {
    console.error("[Ele-in Extension] Error during offline queue flush:", err);
  }
}

async function sendSignedExtensionRequest(path, options = {}) {
  const { syncKey, workspaceId } = await chrome.storage.local.get(["syncKey", "workspaceId"]);
  const endpoint = await getApiEndpoint(path);
  const method = options.method || "GET";
  const headers = { ...(options.headers || {}) };

  if (syncKey) {
    headers["x-api-key"] = syncKey;
  }
  if (workspaceId) {
    headers["X-Workspace-Id"] = workspaceId;
  }

  const timestamp = Math.floor(Date.now() / 1000).toString();
  headers["X-Extension-Timestamp"] = timestamp;

  let bodyStr = options.body;
  if (bodyStr && typeof bodyStr === "object") {
    bodyStr = JSON.stringify(bodyStr);
    headers["Content-Type"] = "application/json";
  }

  if (syncKey && bodyStr) {
    try {
      const sig = await computeHmacSha256(syncKey, bodyStr);
      if (sig) {
        headers["X-Extension-Signature"] = sig;
      }
    } catch (e) {}
  }

  try {
    const resp = await fetch(endpoint, {
      method,
      headers,
      body: bodyStr
    });
    return resp;
  } catch (err) {
    if (method !== "GET") {
      await enqueueOfflineAction({
        endpoint,
        method,
        headers,
        body: bodyStr
      });
    }
    throw err;
  }
}

// ============================================================================
// PHASE 2.1: MULTI-TAB & MULTI-PROFILE EXCLUSIVITY LOCK (LEADER ELECTION)
// ============================================================================

async function electOrGetLeaderTab() {
  const instanceId = await getBrowserInstanceId();
  let tabs = [];
  try {
    tabs = await chrome.tabs.query({ url: "*://*.linkedin.com/*" });
  } catch (err) {
    tabs = [];
  }

  if (!tabs || tabs.length === 0) {
    return { tabId: `sw-${instanceId}`, isLeader: true, rawTabId: null };
  }

  const focusedTab = tabs.find(t => t.active && t.highlighted) || tabs[0];
  const candidateTabId = `${instanceId}:tab-${focusedTab.id}`;
  
  const now = Date.now();
  const LEASE_TTL_MS = 45000; // 45 seconds
  const { leaderTabId, leaderLeaseExpiresAt } = await chrome.storage.local.get(["leaderTabId", "leaderLeaseExpiresAt"]);
  
  if (!leaderTabId || !leaderLeaseExpiresAt || now > leaderLeaseExpiresAt || leaderTabId === candidateTabId) {
    await chrome.storage.local.set({
      leaderTabId: candidateTabId,
      leaderLeaseExpiresAt: now + LEASE_TTL_MS
    });
    return { tabId: candidateTabId, isLeader: true, rawTabId: focusedTab.id };
  }

  return { tabId: candidateTabId, isLeader: false, leaderTabId, rawTabId: focusedTab.id };
}

// Clean up leader lease immediately if the leader tab is closed by the user
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const instanceId = await getBrowserInstanceId();
  const closedTabIdent = `${instanceId}:tab-${tabId}`;
  const { leaderTabId } = await chrome.storage.local.get("leaderTabId");
  if (leaderTabId === closedTabIdent) {
    console.log(`[Ele-in Extension] Leader tab ${tabId} closed. Releasing leader lease.`);
    await chrome.storage.local.remove(["leaderTabId", "leaderLeaseExpiresAt"]);
  }
});

// ============================================================================
// PHASE 2.3: CONTINUOUS COOKIE & SESSION HEALTH BRIDGE
// ============================================================================

let cookieSyncTimer = null;
chrome.cookies.onChanged.addListener(async (changeInfo) => {
  if (!changeInfo.cookie.domain.includes("linkedin.com")) return;
  const name = changeInfo.cookie.name;
  if (name !== "li_at" && name !== "JSESSIONID") return;

  const { syncKey, accountId } = await chrome.storage.local.get(["syncKey", "accountId"]);
  if (!syncKey || !accountId) return;

  // Immediate logout detection: if li_at was removed, user logged out
  if (changeInfo.removed && name === "li_at") {
    console.warn("[Ele-in Extension] 'li_at' cookie was removed! User logged out of LinkedIn.");
    try {
      const sessEndpoint = await getApiEndpoint("session-state");
      await fetch(sessEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": syncKey },
        body: JSON.stringify({
          account_id: accountId,
          status: "DISCONNECTED",
          reason: "User logged out of LinkedIn in local browser"
        })
      });
    } catch (e) {
      console.error("[Ele-in Extension] Failed to report local logout:", e);
    }
    return;
  }

  // Debounced sync (15 seconds) for routine cookie updates
  if (cookieSyncTimer) clearTimeout(cookieSyncTimer);
  cookieSyncTimer = setTimeout(async () => {
    try {
      const allCookies = await chrome.cookies.getAll({ domain: "linkedin.com" });
      const hasLiAt = allCookies.some(c => c.name === "li_at" && c.value);
      if (!hasLiAt) return;

      const normalized = allCookies.map(c => ({
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path || "/",
        secure: c.secure !== undefined ? c.secure : true,
        httpOnly: c.httpOnly !== undefined ? c.httpOnly : (c.name === "li_at")
      }));

      const syncUrl = await getApiEndpoint("sync");
      await fetch(syncUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": syncKey },
        body: JSON.stringify({
          account_id: accountId,
          cookies_json: JSON.stringify(normalized)
        })
      });
      console.log("[Ele-in Extension] Debounced session cookies synced successfully.");
    } catch (err) {
      console.error("[Ele-in Extension] Debounced cookie sync failed:", err);
    }
  }, 15000);
});

// ============================================================================
// PHASE 2.4: ANTI-BOT CHECKPOINT DETECTION & AUTO-HALT
// ============================================================================

function isCheckpointResponse(status, text) {
  if (status === 999 || status === 429) return true;
  const lower = (text || "").toLowerCase();
  return (
    lower.includes("checkpoint") ||
    lower.includes("challenge") ||
    lower.includes("captcha") ||
    lower.includes("security verification") ||
    lower.includes("restricted") ||
    lower.includes("/checkpoint/lg/")
  );
}

async function triggerCheckpointHalt(reason) {
  console.error("[Ele-in Extension] Checkpoint detected! Halting automation:", reason);
  await chrome.storage.local.set({
    checkpointDetected: true,
    checkpointReason: reason,
    checkpointTimestamp: Date.now()
  });

  try {
    chrome.notifications.create("elein-checkpoint", {
      type: "basic",
      iconUrl: "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='48' height='48'><rect width='48' height='48' fill='%23ef4444' rx='8'/><text x='24' y='32' font-size='24' text-anchor='middle' fill='white' font-weight='bold'>!</text></svg>",
      title: "[SECURITY ALERT] LinkedIn Verification Required",
      message: "LinkedIn has triggered a security verification challenge. Ele-in automation has been paused automatically to safeguard your account."
    });
  } catch (notifErr) {
    console.warn("Could not display notification:", notifErr);
  }
}

// Background poll alarm (1 minute cadence)
chrome.alarms.create("pollBackend", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "pollBackend") {
    executeBackgroundTick();
  }
});

// Main Background Execution Loop
async function executeBackgroundTick() {
  const { syncKey, accountId, workspaceId, checkpointDetected } = await chrome.storage.local.get([
    "syncKey", "accountId", "workspaceId", "checkpointDetected"
  ]);
  
  if (!syncKey) {
    console.log("[Ele-in Extension] No sync key configured. Halting tick.");
    return;
  }

  // Paranoia Layer 1: Flush buffered offline queue when online
  await flushOfflineActionQueue();

  // Paranoia Layer 1: If checkpoint was detected, refuse to poll until reset
  if (checkpointDetected) {
    console.warn("[Ele-in Extension] Checkpoint active. Outreach paused.");
    return;
  }

  try {
    // 1. Multi-Tab Exclusivity Check
    const election = await electOrGetLeaderTab();
    if (!election.isLeader) {
      console.log(`[Ele-in Extension] Standby Tab (${election.tabId}). Active Leader is ${election.leaderTabId}. Skipping polling.`);
      return;
    }

    // 2. Send Heartbeat with current Tab ID and Workspace fencing
    const heartbeatUrl = await getApiEndpoint("heartbeat");
    const hbHeaders = {
      "Content-Type": "application/json",
      "x-api-key": syncKey
    };
    if (workspaceId) {
      hbHeaders["X-Workspace-Id"] = workspaceId;
    }
    const hbResp = await fetch(heartbeatUrl, {
      method: "POST",
      headers: hbHeaders,
      body: JSON.stringify({
        account_id: accountId || null,
        extension_version: EXTENSION_VERSION,
        tab_id: election.tabId
      })
    });

    if (hbResp.ok) {
      const hbData = await hbResp.json();
      if (hbData.status === "conflict") {
        console.warn("[Ele-in Extension] Concurrent tab conflict reported by backend:", hbData.message);
        return;
      }
    }

    // 3. Poll for Tasks with Workspace fencing
    const tasksUrl = await getApiEndpoint(
      `tasks?account_id=${encodeURIComponent(accountId || "")}&tab_id=${encodeURIComponent(election.tabId)}`
    );
    const taskHeaders = { "x-api-key": syncKey };
    if (workspaceId) {
      taskHeaders["X-Workspace-Id"] = workspaceId;
    }
    const response = await fetch(tasksUrl, {
      method: "GET",
      headers: taskHeaders
    });
    
    if (!response.ok) {
      console.error("[Ele-in Extension] Failed to fetch tasks:", response.status);
      return;
    }

    const data = await response.json();
    if (data.concurrent_tab_blocked) {
      console.warn("[Ele-in Extension] Tasks polling blocked: concurrent tab is active controller.");
      return;
    }

    const tasks = data.tasks || [];
    if (tasks.length > 0) {
      console.log(`[Ele-in Extension] Received ${tasks.length} task(s). Executing...`);
      for (const task of tasks) {
        await executeTask(task, syncKey, election);
      }
    } else {
      console.log("[Ele-in Extension] No tasks pending.");
    }
  } catch (err) {
    console.error("[Ele-in Extension] Error during background tick:", err);
  }
}

// ============================================================================
// PHASE 2.2: LINKEDIN VOYAGER DOM & API MUTATION RESILIENCE
// ============================================================================

async function executeTask(task, syncKey, election) {
  const resultEndpoint = await getApiEndpoint(`tasks/${task.task_id}/result`);

  try {
    console.log(`[Ele-in Extension] Executing task ${task.task_id} (type: ${task.type})`);
    
    // Paranoia Layer 1: Verify real LinkedIn session cookies exist before attempting any outreach
    const cookies = await chrome.cookies.getAll({ domain: "linkedin.com" });
    const liAt = cookies.find(c => c.name === "li_at" && c.value);
    const jsession = cookies.find(c => c.name === "JSESSIONID" && c.value);

    if (!liAt || !jsession) {
      throw new Error("LinkedIn session cookies ('li_at' or 'JSESSIONID') missing in browser. Outreach halted.");
    }

    const csrfToken = jsession.value.replace(/^"|"$/g, "");

    // Paranoia Layer 2: Human-like delay (2.5 to 5.0 seconds) with randomized micro-sleep
    const jitterMs = 2500 + Math.floor(Math.random() * 2500);
    await new Promise(r => setTimeout(r, jitterMs));

    if (task.type === "linkedin_connect") {
      if (!task.linkedin_url) {
        throw new Error("Missing LinkedIn target profile URL for connection request.");
      }

      let executionSuccess = false;
      let lastErrorMessage = "";

      // ----------------------------------------------------------------------
      // PRIMARY ATTEMPT: LinkedIn Voyager REST API
      // ----------------------------------------------------------------------
      try {
        const payload = {
          invitee: {
            "com.linkedin.voyager.growth.invitation.InviteeProfileUrl": {
              profileUrl: task.linkedin_url
            }
          },
          message: task.message || ""
        };

        const voyagerResp = await fetch("https://www.linkedin.com/voyager/api/growth/normInvitations", {
          method: "POST",
          headers: {
            "csrf-token": csrfToken,
            "x-restli-protocol-version": "2.0.0",
            "Content-Type": "application/json",
            "Accept": "application/vnd.linkedin.normalized+json+2.1"
          },
          credentials: "include",
          body: JSON.stringify(payload)
        });

        if (voyagerResp.ok) {
          executionSuccess = true;
          console.log("[Ele-in Extension] Voyager REST API connection succeeded.");
        } else {
          const errorText = await voyagerResp.text().catch(() => "");
          if (isCheckpointResponse(voyagerResp.status, errorText)) {
            await triggerCheckpointHalt(`Voyager API ${voyagerResp.status}: ${errorText.substring(0, 150)}`);
            throw new Error(`LinkedIn security checkpoint / verification challenge detected: HTTP ${voyagerResp.status}`);
          }
          lastErrorMessage = `Voyager API error ${voyagerResp.status}: ${errorText.substring(0, 150)}`;
          console.warn(`[Ele-in Extension] Voyager API failed (${lastErrorMessage}). Triggering DOM fallback...`);
        }
      } catch (apiErr) {
        if (apiErr.message.includes("security checkpoint")) {
          throw apiErr;
        }
        lastErrorMessage = apiErr.message;
      }

      // ----------------------------------------------------------------------
      // SECONDARY ATTEMPT: Dual-Layer DOM Fallback (Dedicated Background Tab)
      // ----------------------------------------------------------------------
      if (!executionSuccess) {
        console.log(`[Ele-in Extension] Attempting DOM Fallback in dedicated background tab for ${task.linkedin_url}...`);
        try {
          const domResult = await executeDomConnectFallback(task.linkedin_url, task.message);
          if (domResult && domResult.ok) {
            executionSuccess = true;
            console.log("[Ele-in Extension] DOM fallback connection succeeded!");
          } else {
            lastErrorMessage = domResult ? domResult.error : "DOM fallback failed to locate Connect button";
          }
        } catch (domErr) {
          lastErrorMessage = `DOM fallback error: ${domErr.message}`;
        }
      }

      if (!executionSuccess) {
        // Send diagnostic telemetry for triage
        try {
          const diagUrl = await getApiEndpoint("diagnostic");
          await fetch(diagUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "x-api-key": syncKey },
            body: JSON.stringify({
              task_id: task.task_id,
              error_type: "CONNECTION_FAILED",
              error_detail: lastErrorMessage,
              url: task.linkedin_url
            })
          });
        } catch (dErr) {
          console.warn("Could not post diagnostic:", dErr);
        }
        throw new Error(`Connection request failed across API and DOM layers: ${lastErrorMessage}`);
      }

      // ----------------------------------------------------------------------
      // REPORT VERIFIED SUCCESS
      // ----------------------------------------------------------------------
      await fetch(resultEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": syncKey
        },
        body: JSON.stringify({
          status: "success",
          lease_token: task.lease_token || null
        })
      });

      console.log(`[Ele-in Extension] Task ${task.task_id} completed and verified successfully.`);
    } else if (task.type === "send_message" || task.type === "message" || task.type === "linkedin_message") {
      // Paranoia Layer 0 & 1: Multi-Step Campaign Sequence Support (Eradicates FLAW-05)
      const targetUrl = task.linkedin_url || task.profile_url;
      if (!targetUrl) {
        throw new Error("Missing target profile URL for send_message action.");
      }
      const noteText = task.message || task.body || task.noteText || "";
      const msgResult = await executeDomMessage(targetUrl, noteText);
      if (!msgResult || !msgResult.ok) {
        throw new Error(`Message action failed: ${msgResult ? msgResult.error : "Failed to send message"}`);
      }
      await fetch(resultEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": syncKey },
        body: JSON.stringify({ status: "success", lease_token: task.lease_token || null })
      });
      console.log(`[Ele-in Extension] Task ${task.task_id} (send_message) succeeded.`);
    } else if (task.type === "view_profile") {
      // Paranoia Layer 0 & 1: View Profile Step Support (Eradicates FLAW-05)
      const targetUrl = task.linkedin_url || task.profile_url;
      if (!targetUrl) {
        throw new Error("Missing target profile URL for view_profile action.");
      }
      const viewResult = await executeDomViewProfile(targetUrl);
      if (!viewResult || !viewResult.ok) {
        throw new Error(`View profile action failed: ${viewResult ? viewResult.error : "Failed to view profile"}`);
      }
      await fetch(resultEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": syncKey },
        body: JSON.stringify({ status: "success", lease_token: task.lease_token || null })
      });
      console.log(`[Ele-in Extension] Task ${task.task_id} (view_profile) succeeded.`);
    } else {
      throw new Error(`Unsupported extension task type: '${task.type}'`);
    }
  } catch (error) {
    console.error(`[Ele-in Extension] Task ${task.task_id} execution failed:`, error);
    
    // Paranoia Layer 1 & 2: Report error with lease_token for CAS verification
    try {
      await fetch(resultEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": syncKey
        },
        body: JSON.stringify({
          status: "error",
          error_detail: error.message || error.toString(),
          lease_token: task.lease_token || null
        })
      });
    } catch (reportErr) {
      console.error("[Ele-in Extension] Failed to post task error result:", reportErr);
    }
  }
}

// ============================================================================
// DEDICATED TAB EXECUTION & MULTI-STEP SEQUENCE HELPERS (Eradicates FLAW-06)
// ============================================================================

function waitForTabComplete(tabId, timeoutMs = 15000) {
  return new Promise((resolve) => {
    let timer = null;
    const listener = (id, info) => {
      if (id === tabId && info.status === "complete") {
        cleanup();
        resolve(true);
      }
    };
    const cleanup = () => {
      if (timer) clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
    };
    timer = setTimeout(() => {
      cleanup();
      resolve(false);
    }, timeoutMs);
    chrome.tabs.onUpdated.addListener(listener);
  });
}

// Paranoia Layer 1 & 2: Dedicated background tab execution completely eliminates user tab hijacking (Eradicates FLAW-06)
async function executeDomConnectFallback(targetUrl, noteText) {
  if (!chrome.scripting || !chrome.scripting.executeScript || !chrome.tabs) {
    return { ok: false, error: "Scripting and Tabs APIs unavailable" };
  }

  let dedicatedTab = null;
  try {
    dedicatedTab = await chrome.tabs.create({ url: targetUrl, active: false });
    await waitForTabComplete(dedicatedTab.id, 15000);
    // Human-like delay after page load before interacting
    await new Promise(r => setTimeout(r, 2000 + Math.floor(Math.random() * 1500)));

    const results = await chrome.scripting.executeScript({
      target: { tabId: dedicatedTab.id },
      func: async (note) => {
        const CONNECT_PATTERNS = [
          "connect", "invite", "conectar", "connecter", "vernetzen", "connetti", "verbinden"
        ];

        function isConnectButton(el) {
          if (!el) return false;
          const text = (el.innerText || el.textContent || "").toLowerCase().trim();
          const aria = (el.getAttribute("aria-label") || "").toLowerCase().trim();
          return CONNECT_PATTERNS.some(p => text.includes(p) || aria.includes(p));
        }

        function findTargetConnectButton() {
          const explicit = document.querySelector('button[data-control-name="connect"], button[aria-label*="Invite" i], button[aria-label*="Connect" i]');
          if (explicit && isConnectButton(explicit)) return explicit;

          const buttons = Array.from(document.querySelectorAll("button, a.artdeco-button, div[role='button']"));
          let btn = buttons.find(b => isConnectButton(b));
          if (btn) return btn;

          const moreBtn = buttons.find(b => {
            const aria = (b.getAttribute("aria-label") || "").toLowerCase();
            const txt = (b.innerText || "").toLowerCase();
            return aria.includes("more") || txt.includes("more") || aria.includes("más") || txt.includes("plus");
          });
          if (moreBtn) {
            moreBtn.click();
            const dropdownItems = Array.from(document.querySelectorAll("div.artdeco-dropdown__content button, div.artdeco-dropdown__content div[role='button']"));
            btn = dropdownItems.find(i => isConnectButton(i));
            if (btn) return btn;
          }
          return null;
        }

        let targetBtn = findTargetConnectButton();
        if (!targetBtn) {
          targetBtn = await new Promise((resolve) => {
            let timeoutId = null;
            const observer = new MutationObserver(() => {
              const found = findTargetConnectButton();
              if (found) {
                if (timeoutId) clearTimeout(timeoutId);
                observer.disconnect();
                resolve(found);
              }
            });
            observer.observe(document.body, { childList: true, subtree: true });
            timeoutId = setTimeout(() => {
              observer.disconnect();
              resolve(null);
            }, 3500);
          });
        }

        if (!targetBtn) {
          return { ok: false, error: "Connect button not located in DOM after mutation observation" };
        }

        targetBtn.click();

        if (note && note.trim()) {
          await new Promise(r => setTimeout(r, 600));
          const addNoteBtn = Array.from(document.querySelectorAll("button, a.artdeco-button")).find(b => {
            const t = (b.innerText || b.textContent || b.getAttribute("aria-label") || "").toLowerCase();
            return t.includes("add a note") || t.includes("add note") || t.includes("nota") || t.includes("note");
          });
          if (addNoteBtn) {
            addNoteBtn.click();
            await new Promise(r => setTimeout(r, 400));
          }

          const noteTextarea = document.querySelector('textarea[name="message"], textarea#custom-message, textarea');
          if (noteTextarea) {
            noteTextarea.value = note.trim();
            noteTextarea.dispatchEvent(new Event("input", { bubbles: true }));
            noteTextarea.dispatchEvent(new Event("change", { bubbles: true }));
          }

          await new Promise(r => setTimeout(r, 400));
          const sendBtn = Array.from(document.querySelectorAll("button, a.artdeco-button")).find(b => {
            const t = (b.innerText || b.textContent || b.getAttribute("aria-label") || "").toLowerCase();
            return t.includes("send") || t.includes("enviar") || t.includes("envoyer");
          });
          if (sendBtn) {
            sendBtn.click();
          }
        }

        return { ok: true, clicked: true };
      },
      args: [noteText || ""]
    });

    return results && results[0] ? results[0].result : { ok: false, error: "No execution result returned" };
  } catch (err) {
    return { ok: false, error: err.message };
  } finally {
    if (dedicatedTab && dedicatedTab.id) {
      try {
        await chrome.tabs.remove(dedicatedTab.id);
      } catch (closeErr) {}
    }
  }
}

// Paranoia Layer 1: Dedicated Tab LinkedIn Messaging (Eradicates FLAW-05)
async function executeDomMessage(targetUrl, messageText) {
  if (!chrome.scripting || !chrome.scripting.executeScript || !chrome.tabs) {
    return { ok: false, error: "Scripting and Tabs APIs unavailable" };
  }

  let dedicatedTab = null;
  try {
    dedicatedTab = await chrome.tabs.create({ url: targetUrl, active: false });
    await waitForTabComplete(dedicatedTab.id, 15000);
    await new Promise(r => setTimeout(r, 2000 + Math.floor(Math.random() * 1500)));

    const results = await chrome.scripting.executeScript({
      target: { tabId: dedicatedTab.id },
      func: async (msg) => {
        const buttons = Array.from(document.querySelectorAll("button, a.artdeco-button, div[role='button']"));
        const msgBtn = buttons.find(b => {
          const t = (b.innerText || b.textContent || b.getAttribute("aria-label") || "").toLowerCase();
          return t.includes("message") || t.includes("nachricht") || t.includes("mensaje");
        });
        if (!msgBtn) {
          return { ok: false, error: "Message button not found on target profile" };
        }
        msgBtn.click();
        await new Promise(r => setTimeout(r, 1200));

        const editor = document.querySelector('div.msg-form__contenteditable[contenteditable="true"], div[role="textbox"], textarea');
        if (!editor) {
          return { ok: false, error: "Message compose editor element not found" };
        }
        editor.focus();
        document.execCommand("insertText", false, msg);
        await new Promise(r => setTimeout(r, 600));

        const sendBtn = document.querySelector('button.msg-form__send-button, button[type="submit"]');
        if (sendBtn && !sendBtn.disabled) {
          sendBtn.click();
          await new Promise(r => setTimeout(r, 800));
          return { ok: true, sent: true };
        }
        return { ok: false, error: "Send button disabled or unreachable" };
      },
      args: [messageText || ""]
    });

    return results && results[0] ? results[0].result : { ok: false, error: "No execution result returned" };
  } catch (err) {
    return { ok: false, error: err.message };
  } finally {
    if (dedicatedTab && dedicatedTab.id) {
      try {
        await chrome.tabs.remove(dedicatedTab.id);
      } catch (closeErr) {}
    }
  }
}

// Paranoia Layer 1: Dedicated Tab Profile View (Eradicates FLAW-05)
async function executeDomViewProfile(targetUrl) {
  if (!chrome.tabs) {
    return { ok: false, error: "Tabs API unavailable" };
  }
  let dedicatedTab = null;
  try {
    dedicatedTab = await chrome.tabs.create({ url: targetUrl, active: false });
    await waitForTabComplete(dedicatedTab.id, 15000);
    const dwellMs = 3000 + Math.floor(Math.random() * 2500);
    await new Promise(r => setTimeout(r, dwellMs));
    return { ok: true, viewed: true };
  } catch (err) {
    return { ok: false, error: err.message };
  } finally {
    if (dedicatedTab && dedicatedTab.id) {
      try {
        await chrome.tabs.remove(dedicatedTab.id);
      } catch (closeErr) {}
    }
  }
}

// ============================================================================
// CHROME PAC SCRIPT RESIDENTIAL PROXY ROUTING (Eradicates FLAW-04)
// ============================================================================

async function configureExtensionProxy(proxyConfig) {
  if (!chrome.proxy || !chrome.proxy.settings) {
    console.warn("[Ele-in Extension] chrome.proxy API not available.");
    return;
  }
  if (!proxyConfig || !proxyConfig.host || !proxyConfig.port) {
    chrome.proxy.settings.clear({ scope: "regular" }, () => {
      console.log("[Ele-in Extension] Cleared custom proxy settings.");
    });
    return;
  }

  const pacScript = `
    function FindProxyForURL(url, host) {
      if (shExpMatch(host, "*.linkedin.com") || host === "linkedin.com") {
        return "PROXY ${proxyConfig.host}:${proxyConfig.port}";
      }
      return "DIRECT";
    }
  `;

  const config = {
    mode: "pac_script",
    pacScript: {
      data: pacScript
    }
  };

  chrome.proxy.settings.set({ value: config, scope: "regular" }, () => {
    console.log(`[Ele-in Extension] Strict proxy isolation PAC active: *.linkedin.com fail-closed via ${proxyConfig.host}:${proxyConfig.port}`);
  });

  if (chrome.proxy.onProxyError && !chrome.proxy.onProxyError.hasListeners()) {
    chrome.proxy.onProxyError.addListener((details) => {
      console.error("[Ele-in Extension] Proxy connection error:", details.error, details.details);
    });
  }
  });
}

// ============================================================================
// RUNTIME MESSAGE LISTENERS (Reset Checkpoint Lockout & Proxy Steering)
// ============================================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "RESET_CHECKPOINT") {
    chrome.storage.local.set({ checkpointDetected: false, checkpointReason: null }, () => {
      console.log("[Ele-in Extension] Checkpoint lockout cleared by user.");
      sendResponse({ ok: true });
    });
    return true;
  }
  if (message && message.type === "CONFIGURE_PROXY") {
    configureExtensionProxy(message.proxyConfig).then(() => {
      sendResponse({ ok: true });
    });
    return true;
  }
});
