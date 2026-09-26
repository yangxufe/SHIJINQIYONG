const panel = document.querySelector('[data-generation-status]');
if (panel) {
  let timer;
  const check = async () => {
    if (document.hidden) return;
    try {
      const response = await fetch(panel.dataset.generationStatus, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) return;
      const state = await response.json();
      if (!['queued', 'running', 'validating'].includes(state.status)) {
        window.location.reload();
        return;
      }
    } catch (_) {
      // A temporary network failure does not change the server task state.
    }
    timer = window.setTimeout(check, 5000);
  };
  document.addEventListener('visibilitychange', () => {
    window.clearTimeout(timer);
    if (!document.hidden) check();
  });
  timer = window.setTimeout(check, 5000);
}
