/* Shared behaviour for all three Smart Mentor Connect sites.
   - CSRF: adds the token to every POST form and every same-origin fetch()
   - stops double submits (button shows a spinner while the form is sent)
   - nice confirm dialog for anything marked data-confirm="..."
   - POST links:  <a href="/x" data-post>  (used for delete actions)
   - toasts, table scroll wrappers and live table filters
*/
(function () {
  "use strict";

  var meta = document.querySelector('meta[name="csrf-token"]');
  var TOKEN = meta ? meta.content : "";

  /* ---------- CSRF ---------- */
  function addToken(form) {
    if (!TOKEN || (form.method || "").toLowerCase() !== "post") return;
    if (form.querySelector('input[name="csrf_token"]')) return;
    var input = document.createElement("input");
    input.type = "hidden";
    input.name = "csrf_token";
    input.value = TOKEN;
    form.appendChild(input);
  }

  var nativeFetch = window.fetch;
  if (nativeFetch) {
    window.fetch = function (input, init) {
      init = init || {};
      var method = (init.method || (input && input.method) || "GET").toUpperCase();
      var url = typeof input === "string" ? input : (input && input.url) || "";
      var sameOrigin = url.charAt(0) === "/" || url.indexOf(location.origin) === 0;
      if (TOKEN && sameOrigin && method !== "GET" && method !== "HEAD") {
        var headers = new Headers(init.headers || (input && input.headers) || {});
        if (!headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", TOKEN);
        init.headers = headers;
      }
      return nativeFetch.call(window, input, init);
    };
  }

  /* ---------- Toasts ---------- */
  function toastStack() {
    var stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("role", "status");
      stack.setAttribute("aria-live", "polite");
      document.body.appendChild(stack);
    }
    return stack;
  }

  function toast(message, type, ms) {
    var el = document.createElement("div");
    el.className = "toast toast-" + (type || "info");
    var icon = { success: "fa-circle-check", error: "fa-circle-exclamation", info: "fa-circle-info" }[type || "info"];
    el.innerHTML = '<i class="fa-solid ' + icon + '" aria-hidden="true"></i><span></span>' +
      '<button type="button" class="toast-close" aria-label="Dismiss">&times;</button>';
    el.querySelector("span").textContent = message;
    function close() { el.classList.add("is-leaving"); setTimeout(function () { el.remove(); }, 250); }
    el.querySelector(".toast-close").addEventListener("click", close);
    toastStack().appendChild(el);
    setTimeout(close, ms || 5000);
  }

  /* ---------- Confirm dialog ---------- */
  function confirmDialog(message, okLabel, onYes, danger) {
    var overlay = document.createElement("div");
    overlay.className = "smc-modal-overlay";
    overlay.innerHTML =
      '<div class="smc-modal" role="alertdialog" aria-modal="true" aria-labelledby="smcModalMsg">' +
      '<div class="smc-modal-icon"><i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i></div>' +
      '<p id="smcModalMsg"></p>' +
      '<div class="smc-modal-actions">' +
      '<button type="button" class="btn-secondary" data-act="no">Cancel</button>' +
      '<button type="button" class="' + (danger === false ? "" : "btn-danger") + '" data-act="yes"></button>' +
      "</div></div>";
    overlay.querySelector("p").textContent = message;
    overlay.querySelector('[data-act="yes"]').textContent = okLabel || "Yes, continue";
    var previous = document.activeElement;
    function close() { overlay.remove(); document.removeEventListener("keydown", onKey); if (previous) previous.focus(); }
    function onKey(e) { if (e.key === "Escape") close(); }
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay || e.target.getAttribute("data-act") === "no") close();
      else if (e.target.getAttribute("data-act") === "yes") { close(); onYes(); }
    });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    overlay.querySelector('[data-act="no"]').focus();
  }

  function postTo(url, fields) {
    var form = document.createElement("form");
    form.method = "post";
    form.action = url;
    form.style.display = "none";
    Object.keys(fields || {}).forEach(function (k) {
      var i = document.createElement("input");
      i.type = "hidden"; i.name = k; i.value = fields[k];
      form.appendChild(i);
    });
    document.body.appendChild(form);
    addToken(form);
    form.submit();
  }

  /* ---------- Submit lock ---------- */
  function lockForm(form, submitter) {
    var buttons = form.querySelectorAll('button[type="submit"], button:not([type]), input[type="submit"]');
    buttons.forEach(function (b) {
      b.classList.add("is-loading");
      b.setAttribute("aria-busy", "true");
      // disabling in a timeout keeps the clicked button's name/value in the request
      setTimeout(function () { b.disabled = true; }, 0);
    });
    if (submitter && submitter.dataset && submitter.dataset.loadingText) {
      submitter.dataset.originalText = submitter.textContent;
      submitter.textContent = submitter.dataset.loadingText;
    }
  }

  function unlockAll() {
    document.querySelectorAll("button.is-loading, input.is-loading").forEach(function (b) {
      b.classList.remove("is-loading");
      b.removeAttribute("aria-busy");
      b.disabled = false;
      if (b.dataset && b.dataset.originalText) { b.textContent = b.dataset.originalText; }
    });
  }
  window.addEventListener("pageshow", unlockAll);   // back button / bfcache

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    addToken(form);

    var submitter = e.submitter;
    var message = (submitter && submitter.getAttribute("data-confirm")) || form.getAttribute("data-confirm");
    if (message && !form.__confirmed) {
      e.preventDefault();
      confirmDialog(message, (submitter && submitter.getAttribute("data-confirm-label")) || form.getAttribute("data-confirm-label"), function () {
        form.__confirmed = true;
        if (form.requestSubmit) form.requestSubmit(submitter || undefined); else form.submit();
      });
      return;
    }
    // Let the page's own handlers run first; only lock if they did not cancel the submit.
    setTimeout(function () {
      if (!e.defaultPrevented && !form.hasAttribute("data-no-lock")) lockForm(form, submitter);
    }, 0);
  }, false);

  /* ---------- data-post links / data-confirm on links and buttons ---------- */
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-post], a[data-confirm], button[data-confirm][type='button']");
    if (!el) return;
    var isPost = el.hasAttribute("data-post");
    var message = el.getAttribute("data-confirm");
    var url = el.getAttribute("data-post") || el.getAttribute("href");
    if (el.tagName === "BUTTON" && !isPost) return; // handled by form submit
    e.preventDefault();
    function go() { if (isPost) postTo(url); else if (url) window.location.href = url; }
    if (message) confirmDialog(message, el.getAttribute("data-confirm-label"), go); else go();
  });

  /* ---------- Tables: scroll wrapper + live filter ---------- */
  function enhanceTables() {
    document.querySelectorAll("table").forEach(function (table) {
      if (table.closest(".table-wrap") || table.closest(".no-wrap") || table.hasAttribute("data-no-wrap")) return;
      var wrap = document.createElement("div");
      wrap.className = "table-wrap";
      table.parentNode.insertBefore(wrap, table);
      wrap.appendChild(table);
      if (table.tBodies[0] && table.tBodies[0].rows.length > 18) wrap.classList.add("is-tall");
    });

    document.querySelectorAll("table[data-filterable]").forEach(function (table) {
      if (table.__filter) return;
      var wrap = table.closest(".table-wrap") || table;
      var bar = document.createElement("div");
      bar.className = "table-filter";
      bar.innerHTML = '<i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>' +
        '<input type="search" placeholder="' + (table.getAttribute("data-filterable") || "Filter rows") + '" aria-label="Filter table rows">' +
        '<span class="table-filter-count" aria-live="polite"></span>';
      wrap.parentNode.insertBefore(bar, wrap);
      var input = bar.querySelector("input"), count = bar.querySelector(".table-filter-count");
      table.__filter = true;
      input.addEventListener("input", function () {
        var q = input.value.trim().toLowerCase(), shown = 0, rows = table.tBodies[0].rows;
        Array.prototype.forEach.call(rows, function (row) {
          var hit = !q || row.textContent.toLowerCase().indexOf(q) !== -1;
          row.style.display = hit ? "" : "none";
          if (hit) shown++;
        });
        count.textContent = q ? shown + " of " + rows.length : "";
      });
    });
  }

  /* ---------- Misc ---------- */
  function markCurrentNav() {
    document.querySelectorAll(".sidebar-item.active, .dock-item.active").forEach(function (a) {
      a.setAttribute("aria-current", "page");
    });
  }

  function showFlashed() {
    document.querySelectorAll("[data-flash]").forEach(function (el) {
      toast(el.textContent.trim(), el.getAttribute("data-flash"));
      el.remove();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(addToken);
    enhanceTables();
    markCurrentNav();
    showFlashed();
  });

  window.SMC = { toast: toast, confirm: confirmDialog, postTo: postTo, csrfToken: TOKEN };
})();
