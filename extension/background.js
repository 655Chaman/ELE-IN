const API_BASE_URL = "http://127.0.0.1:8000/api/extension";

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
    console.log("No sync key found. Halting tick.");
    return;
  }

  try {
    // 1. Send Heartbeat
    await fetch(`${API_BASE_URL}/heartbeat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': syncKey
      },
      body: JSON.stringify({ account_id: accountId || null })
    });

    // 2. Poll for Tasks
    const response = await fetch(`${API_BASE_URL}/tasks?account_id=${accountId || ''}`, {
      method: 'GET',
      headers: {
        'x-api-key': syncKey
      }
    });
    
    if (!response.ok) {
        console.error("Failed to fetch tasks", response.status);
        return;
    }

    const data = await response.json();
    const tasks = data.tasks || [];
    
    if (tasks.length > 0) {
      console.log(`Found ${tasks.length} tasks. Executing...`);
      for (const task of tasks) {
        await executeTask(task, syncKey);
      }
    } else {
      console.log("No tasks pending.");
    }
  } catch (err) {
    console.error("Error during background tick:", err);
  }
}

async function executeTask(task, syncKey) {
  try {
    console.log("Executing task:", task);
    
    // In a real implementation, we would extract the JSESSIONID CSRF token
    // using chrome.cookies.get, and use fetch() to call the Voyager API.
    
    // Fake 2 second delay to simulate network request
    await new Promise(r => setTimeout(r, 2000));
    
    // Report success
    await fetch(`${API_BASE_URL}/tasks/${task.task_id}/result`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': syncKey
      },
      body: JSON.stringify({ status: "success" })
    });
    
    console.log(`Task ${task.task_id} completed successfully.`);
  } catch (error) {
    console.error(`Task ${task.task_id} failed:`, error);
    
    // Report failure
    await fetch(`${API_BASE_URL}/tasks/${task.task_id}/result`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': syncKey
      },
      body: JSON.stringify({ status: "error", error_detail: error.toString() })
    });
  }
}
