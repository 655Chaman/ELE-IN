document.addEventListener("DOMContentLoaded", async () => {
  const syncKeyInput = document.getElementById("sync-key");
  const accountIdInput = document.getElementById("account-id");
  const saveBtn = document.getElementById("save-btn");
  const statusMsg = document.getElementById("status-message");

  // Load existing
  const data = await chrome.storage.local.get(["syncKey", "accountId"]);
  if (data.syncKey) syncKeyInput.value = data.syncKey;
  if (data.accountId) accountIdInput.value = data.accountId;

  if (data.syncKey) {
    statusMsg.innerText = "Connected and listening in background.";
    statusMsg.classList.add("success");
  }

  saveBtn.addEventListener("click", async () => {
    const syncKey = syncKeyInput.value.trim();
    const accountId = accountIdInput.value.trim();

    if (!syncKey) {
      statusMsg.innerText = "Error: Sync Key is required.";
      statusMsg.classList.remove("success");
      return;
    }

    await chrome.storage.local.set({ syncKey, accountId });
    statusMsg.innerText = "Settings saved successfully! You can close this popup.";
    statusMsg.classList.add("success");
    
    // Trigger an immediate heartbeat/poll so we don't have to wait 1 min
    chrome.alarms.create("pollBackendImmediate", { when: Date.now() + 1000 });
  });
});
