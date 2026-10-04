// Reveal one password briefly, without reading, storing or sending its value.
const controls = [];
document.querySelectorAll('[data-password-peek]').forEach((button) => {
  const input = document.getElementById(button.dataset.passwordPeek);
  if (!input || input.type !== 'password') return;
  let timer;
  const hide = () => {
    window.clearTimeout(timer);
    input.type = 'password';
    button.setAttribute('aria-pressed', 'false');
  };
  controls.push(hide);
  button.addEventListener('click', () => {
    controls.forEach((reset) => reset());
    input.type = 'text';
    button.setAttribute('aria-pressed', 'true');
    timer = window.setTimeout(hide, 1000);
  });
  button.addEventListener('blur', hide);
  button.hidden = false;
});
const hideAll = () => controls.forEach((hide) => hide());
document.addEventListener('visibilitychange', () => {
  if (document.hidden) hideAll();
});
window.addEventListener('blur', hideAll);
window.addEventListener('pagehide', hideAll);
