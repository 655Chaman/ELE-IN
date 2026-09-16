window.addEventListener('error', (e) => {
  fetch('/api/elein/log_error', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: e.message, filename: e.filename, lineno: e.lineno, colno: e.colno, error: e.error?.stack })
  }).catch(() => {});
});
