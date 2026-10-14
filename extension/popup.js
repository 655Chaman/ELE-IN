document.addEventListener("DOMContentLoaded", async () => {
  const syncKeyInput = document.getElementById("sync-key");
  const accountNameInput = document.getElementById("account-name");
  const accountIdInput = document.getElementById("account-id");
  const apiBaseUrlInput = document.getElementById("api-base-url");
  const syncBtn = document.getElementById("sync-btn");
  const statusMsg = document.getElementById("status-message");
  const sessionBadge = document.getElementById("session-badge");
  const sessionText = document.getElementById("session-text");
  const advancedToggle = document.getElementById("advanced-toggle");
  const advancedSection = document.getElementById("advanced-section");

  // Default API URL
  const DEFAULT_API_URL = "http://127.0.0.1:8000";

  // Load saved preferences
  const stored = await chrome.storage.local.get(["syncKey", "accountName", "accountId", "apiBaseUrl"]);
  if (stored.syncKey) syncKeyInput.value = stored.syncKey;
  if (stored.accountName) accountNameInput.value = stored.accountName;
  if (stored.accountId) accountIdInput.value = stored.accountId;
  apiBaseUrlInput.value = stored.apiBaseUrl || DEFAULT_API_URL;

  // Toggle Advanced Settings
  advancedToggle.addEventListener("click", () => {
    advancedSection.classList.toggle("open");
  });

  // Check active LinkedIn Session
  let activeLinkedInCookies = [];
  try {
    const cookies = await chrome.cookies.getAll({ domain: "linkedin.com" });
    const liAt = cookies.find(c => c.name === "li_at" && c.value);
    
    if (liAt) {
      activeLinkedInCookies = cookies;
      sessionBadge.className = "session-badge active";
      sessionText.innerText = `● LinkedIn Logged In (${cookies.length} session cookies detected)`;
    } else {
      sessionBadge.className = "session-badge inactive";
      sessionText.innerText = "○ Not Logged Into LinkedIn (li_at missing)";
    }
  } catch (err) {
    sessionBadge.className = "session-badge inactive";
    sessionText.innerText = "○ Cannot access LinkedIn cookies";
  }

  // 1-Click Sync Handler
  syncBtn.addEventListener("click", async () => {
    const syncKey = syncKeyInput.value.trim();
    const accountName = accountNameInput.value.trim();
    const accountId = accountIdInput.value.trim();
    const apiBaseUrl = (apiBaseUrlInput.value.trim() || DEFAULT_API_URL).replace(/\/$/, "");

    if (!syncKey) {
      statusMsg.className = "status error";
      statusMsg.innerText = "Please enter your Ele-in Workspace Sync Key.";
      return;
    }

    syncBtn.disabled = true;
    statusMsg.className = "status";
    statusMsg.innerText = "Extracting and validating LinkedIn session...";

    try {
      // Re-fetch latest cookies
      const cookies = await chrome.cookies.getAll({ domain: "linkedin.com" });
      const liAt = cookies.find(c => c.name === "li_at" && c.value);

      if (!liAt) {
        throw new Error("Missing 'li_at' cookie. Please log into LinkedIn in this browser and try again.");
      }

      // Normalize cookies for Playwright / backend crypto
      const normalizedCookies = cookies.map(c => ({
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path || "/",
        secure: c.secure !== undefined ? c.secure : true,
        httpOnly: c.httpOnly !== undefined ? c.httpOnly : (c.name === "li_at")
      }));

      statusMsg.innerText = "Encrypting and syncing with Ele-in server...";

      // Save credentials locally
      await chrome.storage.local.set({
        syncKey,
        accountName,
        accountId: accountId || null,
        apiBaseUrl
      });

      const endpoint = `${apiBaseUrl}/api/extension/sync`;
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": syncKey
        },
        body: JSON.stringify({
          account_id: accountId || null,
          account_name: accountName || "LinkedIn Sender",
          cookies_json: JSON.stringify(normalizedCookies)
        })
      });

      const json = await res.json().catch(() => null);

      if (!res.ok) {
        throw new Error(json?.detail || json?.error || `Server returned HTTP ${res.status}`);
      }

      const assignedAccountId = json.account_id || accountId;
      if (assignedAccountId) {
        await chrome.storage.local.set({ accountId: assignedAccountId });
        accountIdInput.value = assignedAccountId;
      }

      statusMsg.className = "status success";
      statusMsg.innerText = "✓ LinkedIn account successfully connected & encrypted in your Ele-in workspace!";

      // Trigger background alarm tick
      chrome.alarms.create("pollBackend", { when: Date.now() + 1000 });

    } catch (e) {
      statusMsg.className = "status error";
      statusMsg.innerText = `Sync failed: ${e.message}`;
    } finally {
      syncBtn.disabled = false;
    }
  });
});
