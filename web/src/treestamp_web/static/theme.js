// Run before the stylesheet so the first paint uses the selected theme.
(() => {
  const storageKey = 'treestamp-theme';
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = null;
  let button = null;

  try {
    const saved = window.localStorage.getItem(storageKey);
    if (saved === 'light' || saved === 'dark') preference = saved;
  } catch {
    // The theme remains usable when browser storage is unavailable.
  }

  function applyTheme() {
    const theme = preference || (systemTheme.matches ? 'dark' : 'light');
    document.documentElement.dataset.theme = theme;
    if (button) {
      const target = theme === 'dark' ? 'Light' : 'Dark';
      button.textContent = `${target} mode`;
      button.setAttribute('aria-label', `Switch to ${target.toLowerCase()} mode`);
      button.setAttribute('aria-pressed', String(theme === 'dark'));
    }
  }

  function bindToggle() {
    button = document.getElementById('theme-toggle');
    if (!button) return;
    applyTheme();
    button.addEventListener('click', () => {
      preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      try {
        window.localStorage.setItem(storageKey, preference);
      } catch {
        // Keep the choice for this page even when it cannot be saved.
      }
      applyTheme();
    });
  }

  applyTheme();
  systemTheme.addEventListener('change', applyTheme);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindToggle, {once: true});
  } else {
    bindToggle();
  }
})();
