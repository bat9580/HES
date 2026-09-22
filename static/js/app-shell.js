/**
 * HES application shell.
 *
 * Layout behavior shared by every page: sidebar, top bar, toasts, global
 * search, logout, modal-backdrop cleanup. Loaded once per full page load
 * from <head> (with defer); on Turbo navigations the sidebar/topbar are
 * `data-turbo-permanent`, so one-time listeners survive, while initPage()
 * re-runs for each rendered page via the `turbo:load` event.
 */
(function () {
  'use strict';

  /* ------------------------------------------------------------------ *
   * Global functions referenced by inline onclick="" handlers           *
   * ------------------------------------------------------------------ */

  window.toggleSidebar = function () {
    var sidebar = document.getElementById('sidebar');
    var toggleBtn = document.querySelector('.toggle-btn');
    var body = document.body;
    if (!sidebar) return;

    // Mark "animating" so child element transitions are frozen for the
    // duration of the collapse — only sidebar width + content margin animate.
    body.classList.add('sidebar-animating');

    var isCollapsed = sidebar.classList.toggle('collapsed');

    if (toggleBtn) {
      toggleBtn.setAttribute('aria-expanded', (!isCollapsed).toString());
      sidebar.dataset.state = isCollapsed ? 'collapsed' : 'expanded';
    }

    body.classList.toggle('sidebar-collapsed', isCollapsed);

    var cleanup = function () {
      body.classList.remove('sidebar-animating');
      sidebar.removeEventListener('transitionend', onEnd);
    };
    var onEnd = function (e) {
      if (e.target === sidebar && (e.propertyName === 'width' || e.propertyName === 'transform')) {
        cleanup();
      }
    };
    sidebar.addEventListener('transitionend', onEnd);
    setTimeout(cleanup, 320); // duration (200ms) + slack
  };

  window.toggleMenu = function (menuId) {
    // Inline handlers expose the click event as window.event; stop the
    // href="#" default so Turbo / the browser never navigates.
    if (window.event && typeof window.event.preventDefault === 'function') {
      window.event.preventDefault();
    }

    var menu = document.getElementById(menuId);
    if (!menu) return;

    var isOpen = menu.classList.toggle('open');
    menu.setAttribute('aria-hidden', (!isOpen).toString());

    var trigger = document.querySelector('[data-menu-target="' + menuId + '"]');
    if (trigger) {
      trigger.setAttribute('aria-expanded', isOpen.toString());
    }
  };

  // Toast notifications (global)
  window.showToast = function (message, type, duration) {
    type = type || 'success';
    duration = duration === undefined ? 4000 : duration;

    var container = document.getElementById('toastContainer');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'toast-notification toast-' + type;

    var iconClass = 'bi-check-circle-fill';
    if (type === 'error') iconClass = 'bi-x-circle-fill';
    else if (type === 'warning') iconClass = 'bi-exclamation-triangle-fill';
    else if (type === 'info') iconClass = 'bi-info-circle-fill';

    toast.innerHTML =
      '<div class="toast-icon"><i class="bi ' + iconClass + '"></i></div>' +
      '<div class="toast-content"><p class="toast-message">' + message + '</p></div>' +
      '<button class="toast-close" aria-label="Close"><i class="bi bi-x-lg"></i></button>';

    container.appendChild(toast);

    setTimeout(function () {
      toast.classList.add('show');
    }, 10);

    toast.querySelector('.toast-close').addEventListener('click', function () {
      window.hideToast(toast);
    });

    if (duration > 0) {
      setTimeout(function () {
        window.hideToast(toast);
      }, duration);
    }
  };

  window.hideToast = function (toast) {
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 300);
  };

  /* ------------------------------------------------------------------ *
   * Helpers                                                             *
   * ------------------------------------------------------------------ */

  function applyResponsiveSidebar() {
    var sb = document.getElementById('sidebar');
    if (!sb) return;
    if (window.innerWidth <= 992 && !sb.classList.contains('collapsed')) {
      sb.classList.add('collapsed');
      sb.dataset.state = 'collapsed';
      document.body.classList.add('sidebar-collapsed');
    }
  }

  // Top-bar global search: pure-DOM table row filter
  function applySearchFilter() {
    var search = document.getElementById('globalPageSearch');
    if (!search) return;
    var q = search.value.trim().toLowerCase();
    document.querySelectorAll('table tbody').forEach(function (tbody) {
      tbody.querySelectorAll('tr').forEach(function (tr) {
        if (!q) {
          tr.removeAttribute('data-topbar-hidden');
          tr.style.display = '';
          return;
        }
        var text = (tr.textContent || '').toLowerCase();
        var match = text.indexOf(q) !== -1;
        tr.style.display = match ? '' : 'none';
        if (match) tr.removeAttribute('data-topbar-hidden');
        else tr.setAttribute('data-topbar-hidden', 'true');
      });
    });
  }

  // Modal backdrop safety net: sweep up state that can be left behind when
  // callers create modal instances unsafely (per-click instances, races on
  // rapid open/close, stacked modals). Prevents the page staying "shadowed"
  // by an orphaned .modal-backdrop and clicks being blocked.
  function cleanupOrphanedModalState() {
    var stillOpen = document.querySelector('.modal.show');
    if (stillOpen) return;

    document.querySelectorAll('.modal-backdrop').forEach(function (b) { b.remove(); });
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');
  }

  function submitLogout(ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }
    var f = document.getElementById('globalLogoutForm');
    if (!f) return;
    try {
      if (typeof f.requestSubmit === 'function') f.requestSubmit();
      else f.submit();
    } catch (e) {
      f.submit();
    }
  }

  /* ------------------------------------------------------------------ *
   * One-time setup: document/window level listeners.                    *
   * Registered once per full page load — Turbo keeps the same window,   *
   * so these survive every smooth navigation.                           *
   * ------------------------------------------------------------------ */
  function setupOnce() {
    window.addEventListener('resize', applyResponsiveSidebar);

    // Marks Turbo navigations so CSS can fade the new content in
    // (no animation on the initial full page load).
    document.addEventListener('turbo:visit', function () {
      document.documentElement.setAttribute('data-turbo-visited', '');
    });

    // Search/filter form submissions: the header and filter bar re-render
    // with identical HTML, so by suppressing the content animation and
    // restoring the scroll position the swap looks like only the table
    // updated.
    var formNavScroll = null;
    document.addEventListener('turbo:submit-start', function () {
      formNavScroll = window.scrollY;
      document.documentElement.setAttribute('data-turbo-form-nav', '');
    });
    document.addEventListener('turbo:load', function () {
      if (formNavScroll !== null) {
        window.scrollTo(0, formNavScroll);
        formNavScroll = null;
      }
      // Clear after this tick so the next regular link click animates again.
      setTimeout(function () {
        document.documentElement.removeAttribute('data-turbo-form-nav');
      }, 0);
    });

    // Logout: any [data-logout-trigger] submits the global hidden form.
    // Delegated so it works for elements inside the permanent topbar and
    // any future page content.
    document.addEventListener('click', function (ev) {
      var trigger = ev.target.closest('[data-logout-trigger]');
      if (trigger) submitLogout(ev);
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var trigger = ev.target.closest && ev.target.closest('[data-logout-trigger]');
      if (trigger) submitLogout(ev);
    });

    // Run cleanup AFTER Bootstrap's own hide animation to avoid racing
    // its internal backdrop removal logic.
    document.addEventListener('hidden.bs.modal', function () {
      setTimeout(cleanupOrphanedModalState, 50);
    });
    window.addEventListener('pageshow', cleanupOrphanedModalState);

    // Global search box lives in the permanent topbar: bind once.
    var search = document.getElementById('globalPageSearch');
    if (search) {
      var timer = null;
      search.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(applySearchFilter, 120);
      });
    }
    document.addEventListener('keydown', function (ev) {
      var s = document.getElementById('globalPageSearch');
      if (!s) return;
      if (ev.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
        ev.preventDefault();
        s.focus();
      }
      if (ev.key === 'Escape' && document.activeElement === s) {
        s.value = '';
        applySearchFilter();
        s.blur();
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * Per-page initialization: runs on initial load AND after every       *
   * Turbo navigation.                                                   *
   * ------------------------------------------------------------------ */
  function initPage() {
    // Tooltips first (Bootstrap moves title -> data-bs-original-title),
    // then strip leftover title attributes so the browser's native
    // tooltip never appears. getOrCreateInstance avoids duplicating
    // tooltips on the permanent sidebar/topbar elements.
    if (window.bootstrap && window.bootstrap.Tooltip) {
      document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
        window.bootstrap.Tooltip.getOrCreateInstance(el);
      });
    }
    document.querySelectorAll('[title]').forEach(function (el) {
      el.removeAttribute('title');
    });

    // Body classes don't survive Turbo's body swap; resync from the
    // permanent sidebar element.
    var sidebar = document.getElementById('sidebar');
    if (sidebar) {
      document.body.classList.toggle('sidebar-collapsed', sidebar.classList.contains('collapsed'));
    }

    // Sync submenu trigger aria state
    document.querySelectorAll('[data-menu-target]').forEach(function (trigger) {
      var target = trigger.getAttribute('data-menu-target');
      var menu = document.getElementById(target);
      if (menu) {
        var isOpen = menu.classList.contains('open');
        trigger.setAttribute('aria-expanded', isOpen.toString());
        menu.setAttribute('aria-hidden', (!isOpen).toString());
      }
    });

    // Highlight current sidebar nav link based on URL path
    try {
      var path = window.location.pathname.replace(/\/$/, '');
      document.querySelectorAll('.sidebar .nav-link.active').forEach(function (a) {
        a.classList.remove('active');
      });
      document.querySelectorAll('.sidebar .nav-link[href]').forEach(function (a) {
        var href = (a.getAttribute('href') || '').replace(/\/$/, '');
        if (href && href !== '#' && (path === href || path.toLowerCase() === href.toLowerCase())) {
          a.classList.add('active');
          var parentSubmenu = a.closest('.submenu');
          if (parentSubmenu) {
            parentSubmenu.classList.add('open');
            parentSubmenu.setAttribute('aria-hidden', 'false');
            var parentTrigger = document.querySelector('[data-menu-target="' + parentSubmenu.id + '"]');
            if (parentTrigger) parentTrigger.setAttribute('aria-expanded', 'true');
          }
        }
      });
    } catch (e) { /* no-op */ }

    applyResponsiveSidebar();

    // Forms are opt-in for Turbo (POST handlers often return HTML directly,
    // which Turbo would reject). GET forms — search/filter bars — are plain
    // navigations with a query string, so let Turbo drive them smoothly.
    // Forms without an action (handled by their own page JS) are skipped.
    document.querySelectorAll('form[action]').forEach(function (form) {
      var method = (form.getAttribute('method') || 'get').trim().toLowerCase();
      if (method === 'get' && !form.hasAttribute('data-turbo')) {
        form.setAttribute('data-turbo', 'true');
      }
    });

    // If the topbar search still holds a query, filter the new page's tables
    var search = document.getElementById('globalPageSearch');
    if (search && search.value.trim()) applySearchFilter();
  }

  /* ------------------------------------------------------------------ *
   * Boot                                                                *
   * ------------------------------------------------------------------ */
  var booted = false;
  function boot() {
    if (!booted) {
      booted = true;
      setupOnce();
    }
    initPage();
  }

  // turbo:load fires on the initial page load and after every Turbo visit.
  document.addEventListener('turbo:load', boot);

  // Fallback: if the Turbo CDN failed to load, still initialize the shell.
  document.addEventListener('DOMContentLoaded', function () {
    if (!window.Turbo) boot();
  });
})();
