/**
 * Turbo Drive compatibility shim.
 *
 * Lets the existing page templates work with Turbo navigation WITHOUT
 * having to rewrite their inline <script> blocks. Must be loaded in <head>
 * BEFORE the Turbo library and before any page scripts.
 *
 * It solves three problems that appear when the browser stops doing full
 * page loads:
 *
 *   1. Page scripts register `DOMContentLoaded` handlers, but that event
 *      only fires once per real page load — never on Turbo visits.
 *      => If the DOM is already ready when a handler is registered, run it
 *         immediately (async), like jQuery's $(document).ready does.
 *
 *   2. Inline scripts with top-level `const`/`let` throw
 *      "Identifier has already been declared" when a page is visited twice,
 *      because Turbo keeps the same JavaScript context alive.
 *      => Re-route inline body scripts through indirect eval on Turbo
 *         renders: `let`/`const` stay scoped to that eval call, while
 *         `function` and `var` declarations still become globals (so
 *         inline onclick="..." handlers keep working).
 *
 *   3. Intervals started by a page (e.g. the dashboard clock) keep running
 *      after navigating away.
 *      => Track interval ids and clear them right before Turbo swaps in
 *         the next page.
 */
(function () {
  'use strict';

  if (window.__hesTurboShim) return;
  window.__hesTurboShim = true;

  /* ------------------------------------------------------------------ *
   * 1. Late DOMContentLoaded registration support                       *
   * ------------------------------------------------------------------ */
  function patchReadyListener(target) {
    var originalAdd = target.addEventListener.bind(target);
    target.addEventListener = function (type, listener, options) {
      var isReadyEvent =
        type === 'DOMContentLoaded' || (target === window && type === 'load');
      if (
        isReadyEvent &&
        document.readyState !== 'loading' &&
        typeof listener === 'function'
      ) {
        // DOM is already ready: native registration would never fire.
        // Run the handler asynchronously so the rest of the current
        // script finishes first (mirrors native event timing).
        setTimeout(function () {
          listener.call(target, new Event(type));
        }, 0);
        return;
      }
      return originalAdd(type, listener, options);
    };
  }
  patchReadyListener(document);
  patchReadyListener(window);

  /* ------------------------------------------------------------------ *
   * 2. Safe re-execution of inline body scripts on Turbo renders        *
   * ------------------------------------------------------------------ */
  document.addEventListener('turbo:before-render', function (event) {
    var newBody = event.detail && event.detail.newBody;
    if (!newBody) return;

    newBody.querySelectorAll('script:not([src])').forEach(function (script) {
      var type = (script.getAttribute('type') || '').trim().toLowerCase();
      if (type && type !== 'text/javascript' && type !== 'application/javascript') {
        return; // JSON payloads, templates, modules — leave untouched
      }
      var code = script.textContent;
      if (!code || script.dataset.turboShimmed) return;
      script.dataset.turboShimmed = 'true';
      // Indirect eval: runs in global scope, but top-level let/const are
      // confined to this eval call, so revisiting a page can't throw
      // "Identifier has already been declared".
      script.textContent = '(0,eval)(' + JSON.stringify(code) + ');';
    });
  });

  /* ------------------------------------------------------------------ *
   * 3. Clear page-scoped intervals on navigation                        *
   * ------------------------------------------------------------------ */
  var trackedIntervals = [];
  var originalSetInterval = window.setInterval.bind(window);
  var originalClearInterval = window.clearInterval.bind(window);

  window.setInterval = function () {
    var id = originalSetInterval.apply(null, arguments);
    trackedIntervals.push(id);
    return id;
  };
  window.clearInterval = function (id) {
    var idx = trackedIntervals.indexOf(id);
    if (idx !== -1) trackedIntervals.splice(idx, 1);
    return originalClearInterval(id);
  };

  document.addEventListener('turbo:before-render', function () {
    trackedIntervals.forEach(function (id) {
      originalClearInterval(id);
    });
    trackedIntervals.length = 0;
  });
})();
