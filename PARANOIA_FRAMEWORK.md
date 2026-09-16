# The Paranoia Framework (Three-Layer Logic Architecture)

This document serves as the standard operating protocol for all core logic, AI integrations, and infrastructure development within this codebase. 

Every single piece of logic or bug fix **must rigorously pass through these three distinct layers** before it is considered complete. Do not dilute the quality of any layer; each is a massive architectural step.

---

### Layer 0: The Foundational Layer
**Goal:** Solve the core issue.
**Description:** This is the basic implementation. Get the fundamental mechanics working. This is the "happy path" code that assumes servers have infinite RAM, databases never lock, APIs never rate-limit, and users behave perfectly.
*   **Example (Worker Queue):** Write a `while True` loop that queries pending jobs and processes them.
*   **Example (API Keys):** Pass an API key to the LLM client and make the request.

---

### Layer 1: Environmental Failure Analysis
**Goal:** Protect the foundation from the machine environment.
**The Prompt:** *"In what situations or in what environments will this foundational logic fail?"*

You must generate a comprehensive list of edge cases, race conditions, system crashes, network drops, or environmental shifts where the code breaks, and build a robust architectural solution for *each and every* identified failure point.

*   **Example (Worker Queue):** What if the Python worker crashes mid-job due to an Out-Of-Memory (OOM) error? The job is forever stuck as `running`. 
    *   *Solution:* Build a zombie-recovery mechanism that automatically detects jobs running longer than 15 minutes and resets them to `pending`.
*   **Example (API Keys):** What if the NVIDIA API returns an `HTTP 429 Too Many Requests`?
    *   *Solution:* The script must catch the specific 429 error, quarantine that specific key in an in-memory cache for exactly 60 seconds, and instantly seamlessly failover to the next key in the round-robin pool without dropping the user's request.

---

### Layer 2: Human Paranoia (The Human Error Element)
**Goal:** Protect the system from the user (and the developer).
**The Prompt:** *"How can a human make a mistake in this section?"*

You must assume the human user will do the stupidest, most extreme thing possible (e.g., clicking 50 times in 3 seconds, typing the wrong format, leaving the app open in 10 tabs, misinterpreting the UI, doing exactly what they were told not to do). You must build a physically preventative solution to block the user from harming themselves or the system.

*   **Example (Worker Queue):** What if the UI lags, and an impatient user clicks the "Upload URL" button 50 times rapidly? The API will queue 50 identical scraping jobs and crash the background workers.
    *   *Solution:* The API endpoint must generate an MD5 hash of the uploaded payload. Before queuing, it checks if a pending job with the exact same hash already exists for that workspace. If it does, it silently returns the original asset and drops the 49 duplicates.
*   **Example (API Keys):** What if the user types `NVIDIA_API_KEY_SYNTHESIS=" key1,  , key2,, "` in the `.env` file with bad formatting and empty commas?
    *   *Solution:* The parser must aggressively strip whitespace, split by commas, and natively filter out any empty strings before passing the array to the LLM client, ensuring a typo in `.env` doesn't crash the server.
