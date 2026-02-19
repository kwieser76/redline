/* Redline – Defektmeldesystem – main.js */

// Auto-dismiss flash messages after 5 seconds
document.addEventListener("DOMContentLoaded", function () {
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = "opacity .4s";
      alert.style.opacity = "0";
      setTimeout(function () { alert.remove(); }, 400);
    }, 5000);
  });

  // Confirm destructive actions
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      if (!confirm(el.dataset.confirm)) {
        e.preventDefault();
      }
    });
  });
});
