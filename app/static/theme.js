let theme = "light";
try {
  if (localStorage.getItem("quorum-theme") === "dark") theme = "dark";
} catch { /* The theme still works when browser storage is unavailable. */ }
document.documentElement.dataset.theme = theme;

document.addEventListener("DOMContentLoaded", () => {
  const button = document.querySelector("#theme-toggle");
  button.setAttribute("aria-checked", String(theme === "dark"));
  button.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    button.setAttribute("aria-checked", String(theme === "dark"));
    try {
      localStorage.setItem("quorum-theme", theme);
    } catch { /* Keep the choice for this page even if storage is blocked. */ }
  });
});
