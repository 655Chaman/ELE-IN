// Ele-in LinkedIn Execution Engine (Chrome Extension Service Worker)
// Rigorously built under the Three-Layer Logic Architecture (Paranoia Framework)

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const EXTENSION_VERSION = "1.2.0";

async function getApiEndpoint(path = "") {
  const { apiBaseUrl } = await chrome.storage.local.get("apiBaseUrl");
  const base = (apiBaseUrl || DEFAULT_API_BASE).replace(/\/+$/, "");
  const cleanPath = path.replace(/^\/+/, "");
  return `${base}/api/extension${cleanPath ? "/" + cleanPath : ""}`;
}

// Poll every 1 minute
chrome.alarms.create("pollBackend", { periodInMinutes: 1 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "pollBackend") {
    executeBackgroundTick();
  }
});

async function executeBackgroundTick() {
  const { syncKey, accountId } = await chrome.storage.local.get(["syncKey", "accountId"]);
  
  if (!syncKey) {
    console.log("[Ele-in Extension] No sync key configured. Halting tick.");
    return;
  }

  try {
    const heartbeatUrl = await getApiEndpoint("heartbeat");
    // 1. Send Heartbeat with extension version & tab identifier
    await fetch(heartbeatUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": syncKey
      },
      body: JSON.stringify({
        account_id: accountId || null,
        version: EXTENSION_VERSION,
        tab_id: "ext-service-worker"
      })
    });

    // 2. Poll for Tasks
    const tasksUrl = await getApiEndpoint(`tasks?account_id=${encodeURIComponent(accountId || "")}&tab_id=ext-service-worker`);
    const response = await fetch(tasksUrl, {
      method: "GET",
      headers: {
        "x-api-key": syncKey
      }
    });
    
    if (!response.ok) {
      console.error("[Ele-in Extension] Failed to fetch tasks:", response.status);
      return;
    }

    const data = await response.json();
    const tasks = data.tasks || [];
    
    if (tasks.length > 0) {
      console.log(`[Ele-in Extension] Received ${tasks.length} tasks. Executing...`);
      for (const task of tasks) {
        await executeTask(task, syncKey);
      }
    } else {
      console.log("[Ele-in Extension] No tasks pending.");
    }
  } catch (err) {
    console.error("[Ele-in Extension] Error during background tick:", err);
  }
}

async function executeTask(task, syncKey) {
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

    // Paranoia Layer 2: Human-like delay (2 to 4 seconds) before outbound dispatch
    const jitterMs = 2000 + Math.floor(Math.random() * 2000);
    await new Promise(r => setTimeout(r, jitterMs));

    if (task.type === "linkedin_connect") {
      if (!task.linkedin_url) {
        throw new Error("Missing LinkedIn target profile URL for connection request.");
      }

      // Execute connection request via LinkedIn Voyager API
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

      if (!voyagerResp.ok) {
        const errorText = await voyagerResp.text().catch(() => "");
        if (voyagerResp.status === 429) {
          throw new Error("LinkedIn rate limit exceeded (HTTP 429).");
        } else if (voyagerResp.status === 999 || errorText.includes("checkpoint") || errorText.includes("challenge")) {
          throw new Error("LinkedIn security checkpoint / verification challenge detected.");
        } else {
          throw new Error(`LinkedIn Voyager returned HTTP ${voyagerResp.status}: ${errorText.substring(0, 150)}`);
        }
      }

      // Real execution succeeded: report verified success with lease_token
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
    } else {
      // Unknown or unsupported task type: NEVER fake success
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
