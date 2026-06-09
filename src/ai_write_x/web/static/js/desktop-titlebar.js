(function () {
    'use strict';

    function api() {
        return (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
    }

    function setMaximizedClass(isMax) {
        document.body.classList.toggle('xb-window-maximized', !!isMax);
    }

    function callWindow(method, after) {
        var a = api();
        if (!a || typeof a[method] !== 'function') {
            return;
        }
        try {
            var result = a[method]();
            if (result && typeof result.then === 'function') {
                result.then(function (res) { if (after) after(res); });
            } else if (after) {
                after(result);
            }
        } catch (e) {
            /* ignore desktop bridge errors */
        }
    }

    function bind() {
        var bar = document.getElementById('xb-titlebar');
        if (!bar || bar.dataset.bound === '1') {
            return;
        }
        bar.dataset.bound = '1';
        bar.setAttribute('aria-hidden', 'false');

        var minBtn = document.getElementById('xb-win-min');
        var maxBtn = document.getElementById('xb-win-max');
        var closeBtn = document.getElementById('xb-win-close');
        var dragZone = document.getElementById('xb-titlebar-drag');

        if (minBtn) {
            minBtn.addEventListener('click', function () { callWindow('minimize_window'); });
        }
        if (maxBtn) {
            maxBtn.addEventListener('click', function () {
                callWindow('toggle_maximize_window', function (res) {
                    if (res && typeof res.maximized !== 'undefined') {
                        setMaximizedClass(res.maximized);
                    }
                });
            });
        }
        if (closeBtn) {
            closeBtn.addEventListener('click', function () { callWindow('close_window'); });
        }
        if (dragZone) {
            dragZone.addEventListener('dblclick', function () {
                callWindow('toggle_maximize_window', function (res) {
                    if (res && typeof res.maximized !== 'undefined') {
                        setMaximizedClass(res.maximized);
                    }
                });
            });
        }
    }

    function activate() {
        if (!document.body.classList.contains('desktop-frameless')) {
            return;
        }
        bind();
    }

    document.addEventListener('pywebviewready', activate);
    if (document.readyState !== 'loading') {
        activate();
    } else {
        document.addEventListener('DOMContentLoaded', activate);
    }

    var observer = new MutationObserver(function () {
        if (document.body.classList.contains('desktop-frameless')) {
            activate();
        }
    });
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
})();
