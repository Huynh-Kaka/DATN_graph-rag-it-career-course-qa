const THEME_KEY = 'career-chat-theme';

function syncThemeIcons(isDark) {
  ['moonIco', 'sunIco', 'moonIco2', 'sunIco2'].forEach((id, i) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.display =
      i % 2 === 0 ? (isDark ? 'none' : 'inline-block') : isDark ? 'inline-block' : 'none';
  });
}

function themeRoot() {
  return document.documentElement;
}

function applyThemeFromStorage() {
  const dark = localStorage.getItem(THEME_KEY) === 'dark';
  themeRoot().classList.toggle('dark-mode', dark);
  syncThemeIcons(dark);
}

function toggleTheme() {
  const root = themeRoot();
  const next = !root.classList.contains('dark-mode');
  root.classList.toggle('dark-mode', next);
  localStorage.setItem(THEME_KEY, next ? 'dark' : 'light');
  syncThemeIcons(next);
}

document.addEventListener('DOMContentLoaded', applyThemeFromStorage);
