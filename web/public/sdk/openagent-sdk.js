/**
 * OpenAgent Embed SDK v1.0.0
 *
 * Usage:
 *   OpenAgentSDK.init({ channelId: 'YOUR_CHANNEL_ID' })
 *
 * Returns an instance with open(), close(), toggle(), isOpen(), destroy() methods.
 *
 * Note: `window.NewAgentSDK` is exposed as a deprecated alias for snippets
 * generated before the OpenAgent rename. New integrations should use
 * `OpenAgentSDK`.
 */
(function (root) {
  'use strict';

  var VERSION = '1.0.2';
  var instances = {};

  var DEFAULTS = {
    launcher: {
      show: true,
      position: 'bottom-right',
      offsetX: 24,
      offsetY: 24,
    },
    window: {
      width: 400,
      height: 680,
      minWidth: 320,
      maxWidth: 600,
      minHeight: 400,
      maxHeight: 800,
    },
  };

  function mergeDeep(target, source) {
    var result = {};
    for (var key in target) {
      if (target.hasOwnProperty(key)) result[key] = target[key];
    }
    for (var k in source) {
      if (source.hasOwnProperty(k)) {
        if (typeof source[k] === 'object' && source[k] !== null && !Array.isArray(source[k]) && typeof result[k] === 'object') {
          result[k] = mergeDeep(result[k], source[k]);
        } else {
          result[k] = source[k];
        }
      }
    }
    return result;
  }

  function getBaseUrl() {
    var sdkScript = getSdkScript();
    if (sdkScript) {
      return (sdkScript.src || '').replace(/\/sdk\/openagent-sdk\.js.*$/, '');
    }
    return window.location.origin;
  }

  function getSdkScript() {
    var scripts = document.getElementsByTagName('script');
    for (var i = scripts.length - 1; i >= 0; i--) {
      var src = scripts[i].src || '';
      if (src.indexOf('openagent-sdk.js') !== -1) {
        return scripts[i];
      }
    }
    return null;
  }

  function getScriptChannelSource() {
    var sdkScript = getSdkScript();
    if (!sdkScript || !sdkScript.getAttribute) return null;
    return sdkScript.getAttribute('data-channel-source');
  }

  function getStringLength(value) {
    if (typeof Array.from === 'function') {
      return Array.from(value).length;
    }
    return value.length;
  }

  function normalizeChannelSource(value) {
    if (typeof value !== 'string') return '';
    var normalized = value.replace(/^\s+|\s+$/g, '');
    if (!normalized || getStringLength(normalized) > 64) return '';
    if (/[\x00-\x1F\x7F]/.test(normalized)) return '';
    return normalized;
  }

  function getViewportRect() {
    var vv = window.visualViewport;
    return {
      width: vv ? vv.width : window.innerWidth,
      height: vv ? vv.height : window.innerHeight,
      offsetLeft: vv ? vv.offsetLeft : 0,
      offsetTop: vv ? vv.offsetTop : 0,
    };
  }

  // Lucide message-circle SVG
  var MSG_CIRCLE_SVG = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></svg>';
  var CLOSE_SVG = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

  function createInstance(config) {
    var channelId = config.channelId;
    if (!channelId) throw new Error('OpenAgentSDK: channelId is required');

    if (instances[channelId]) {
      instances[channelId].destroy();
    }

    var opts = mergeDeep(DEFAULTS, config);
    var baseUrl = (config.baseUrl || getBaseUrl()).replace(/\/$/, '');
    var chatUrlObj = new URL(baseUrl + '/chat/' + channelId, window.location.href);
    chatUrlObj.searchParams.set('embed', '1');
    if (config.test === true) {
      chatUrlObj.searchParams.set('test', 'true');
    }
    var channelSource = normalizeChannelSource(
      config.channelSource != null ? config.channelSource : getScriptChannelSource()
    );
    if (channelSource) {
      chatUrlObj.searchParams.set('channel_source', channelSource);
    }
    var chatUrl = chatUrlObj.toString();
    var isOpen = false;
    var iframeReady = false;
    var destroyed = false;

    var callbacks = {
      onReady: config.onReady || null,
      onOpen: config.onOpen || null,
      onClose: config.onClose || null,
      onError: config.onError || null,
    };

    var container = document.createElement('div');
    container.id = 'openagent-sdk-' + channelId;
    container.style.cssText = 'position:fixed;z-index:2147483647;';
    document.body.appendChild(container);

    var pos = opts.launcher.position;
    var ox = opts.launcher.offsetX;
    var oy = opts.launcher.offsetY;

    function positionLauncher(el) {
      el.style.position = 'fixed';
      if (pos === 'bottom-right' || pos === 'right-bottom') {
        el.style.right = ox + 'px'; el.style.bottom = oy + 'px';
      } else if (pos === 'bottom-left' || pos === 'left-bottom') {
        el.style.left = ox + 'px'; el.style.bottom = oy + 'px';
      } else if (pos === 'top-right' || pos === 'right-top') {
        el.style.right = ox + 'px'; el.style.top = oy + 'px';
      } else if (pos === 'top-left' || pos === 'left-top') {
        el.style.left = ox + 'px'; el.style.top = oy + 'px';
      } else {
        el.style.right = ox + 'px'; el.style.bottom = oy + 'px';
      }
    }

    // Decide fullscreen mode from viewport WIDTH only. Using height is unsafe
    // because laptops with toolbars/dock often report < 800 and would be
    // wrongly fullscreened.
    function isMobileFullscreen() {
      return getViewportRect().width <= 640;
    }

    function positionWindow(el) {
      el.style.position = 'fixed';
      el.style.left = '';
      el.style.right = '';
      el.style.top = '';
      el.style.bottom = '';
      el.style.maxWidth = '';
      el.style.maxHeight = '';

      var viewport = getViewportRect();
      var gap = 16;

      if (isMobileFullscreen()) {
        var margin = 8;
        el.style.left = (viewport.offsetLeft + margin) + 'px';
        el.style.top = (viewport.offsetTop + margin) + 'px';
        el.style.width = Math.max(0, viewport.width - margin * 2) + 'px';
        el.style.height = Math.max(0, viewport.height - margin * 2) + 'px';
        el.style.borderRadius = '16px';
        return;
      }

      var w = Math.min(Math.max(opts.window.width, opts.window.minWidth), opts.window.maxWidth);
      var h = Math.min(Math.max(opts.window.height, opts.window.minHeight), opts.window.maxHeight);
      // Cap to viewport with small margin so it never exceeds the visible area
      // on short windows.
      h = Math.min(h, Math.max(0, viewport.height - (oy + 56 + gap + 8)));
      el.style.width = w + 'px';
      el.style.height = h + 'px';
      el.style.borderRadius = '24px';

      if (pos === 'bottom-right' || pos === 'right-bottom') {
        el.style.right = ox + 'px'; el.style.bottom = (oy + 56 + gap) + 'px';
      } else if (pos === 'bottom-left' || pos === 'left-bottom') {
        el.style.left = ox + 'px'; el.style.bottom = (oy + 56 + gap) + 'px';
      } else if (pos === 'top-right' || pos === 'right-top') {
        el.style.right = ox + 'px'; el.style.top = (oy + 56 + gap) + 'px';
      } else if (pos === 'top-left' || pos === 'left-top') {
        el.style.left = ox + 'px'; el.style.top = (oy + 56 + gap) + 'px';
      } else {
        el.style.right = ox + 'px'; el.style.bottom = (oy + 56 + gap) + 'px';
      }
    }

    function syncLauncherVisibility() {
      if (!launcherBtn) return;
      if (isOpen && isMobileFullscreen()) {
        // Fullscreen overlay would cover the launcher; hide it to avoid an
        // unreachable button stuck under the iframe.
        launcherBtn.style.display = 'none';
      } else {
        launcherBtn.style.display = '';
      }
    }

    // FAB launcher button (56x56, design spec)
    var launcherBtn = null;
    if (opts.launcher.show !== false) {
      launcherBtn = document.createElement('button');
      launcherBtn.setAttribute('aria-label', 'Open chat');
      launcherBtn.style.cssText =
        'width:56px;height:56px;border-radius:28px;border:none;cursor:pointer;' +
        'display:flex;align-items:center;justify-content:center;' +
        'box-shadow:0 4px 12px rgba(0,0,0,0.15);transition:transform 0.2s;' +
        'background-color:#1A1A1A;color:#FFFFFF;';
      launcherBtn.innerHTML = MSG_CIRCLE_SVG;
      positionLauncher(launcherBtn);
      launcherBtn.addEventListener('click', function () { instance.toggle(); });
      launcherBtn.addEventListener('mouseenter', function () { launcherBtn.style.transform = 'scale(1.08)'; });
      launcherBtn.addEventListener('mouseleave', function () { launcherBtn.style.transform = 'scale(1)'; });
      container.appendChild(launcherBtn);
    }

    // Chat window (rounded-24, design spec)
    var chatWindow = document.createElement('div');
    chatWindow.style.cssText =
      'display:none;border-radius:24px;overflow:hidden;' +
      'box-shadow:0 8px 32px rgba(0,0,0,0.12);border:1px solid #E4E4E7;' +
      'background:#FFFFFF;';
    positionWindow(chatWindow);

    var iframe = document.createElement('iframe');
    iframe.src = chatUrl;
    iframe.style.cssText = 'width:100%;height:100%;border:none;visibility:hidden;';
    iframe.setAttribute('allow', 'clipboard-write');
    chatWindow.appendChild(iframe);

    var loadingOverlay = document.createElement('div');
    loadingOverlay.style.cssText =
      'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' +
      'background:#FFFFFF;color:#A1A1AA;z-index:1;';
    loadingOverlay.innerHTML =
      '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation:openagent-sdk-spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>';
    chatWindow.appendChild(loadingOverlay);
    container.appendChild(chatWindow);

    if (!document.getElementById('openagent-sdk-style')) {
      var style = document.createElement('style');
      style.id = 'openagent-sdk-style';
      style.textContent = '@keyframes openagent-sdk-spin{to{transform:rotate(360deg)}}';
      document.head.appendChild(style);
    }

    function syncLoadingOverlay() {
      loadingOverlay.style.display = isOpen && !iframeReady ? 'flex' : 'none';
      iframe.style.visibility = iframeReady ? 'visible' : 'hidden';
    }

    // Listen for close messages from embedded chat page
    function onMessage(e) {
      if (destroyed) return;
      var data = e.data;
      if (data && data.type === 'openagent-close') {
        instance.close();
      } else if (data && data.type === 'openagent-ready') {
        iframeReady = true;
        syncLoadingOverlay();
      }
    }
    window.addEventListener('message', onMessage);

    // rAF-throttled to avoid layout thrash when the address bar shows/hides
    // (visualViewport.scroll fires continuously on mobile).
    var viewportRafId = 0;
    function onViewportChange() {
      if (destroyed || !isOpen) return;
      if (viewportRafId) return;
      viewportRafId = requestAnimationFrame(function () {
        viewportRafId = 0;
        positionWindow(chatWindow);
        syncLauncherVisibility();
      });
    }
    window.addEventListener('resize', onViewportChange);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', onViewportChange);
      window.visualViewport.addEventListener('scroll', onViewportChange);
    }

    // Fetch channel config via public endpoint (no auth required)
    fetch(baseUrl + '/api/v1/public/channels/' + channelId)
      .then(function (r) { return r.json(); })
      .then(function (ch) {
        var cfg = ch.config || {};
        var app = cfg.appearance || {};
        if (launcherBtn) {
          if (app.embedButtonBgColor) launcherBtn.style.backgroundColor = app.embedButtonBgColor;
          if (app.embedButtonIconColor) launcherBtn.style.color = app.embedButtonIconColor;
        }
        if (callbacks.onReady) callbacks.onReady();
      })
      .catch(function (err) {
        if (callbacks.onError) callbacks.onError({ message: err.message || 'Failed to load channel config' });
      });

    var instance = {
      version: VERSION,

      open: function () {
        if (destroyed || isOpen) return;
        positionWindow(chatWindow);
        chatWindow.style.display = 'block';
        isOpen = true;
        syncLoadingOverlay();
        if (launcherBtn) {
          launcherBtn.innerHTML = CLOSE_SVG;
        }
        syncLauncherVisibility();
        if (iframe.contentWindow) {
          iframe.contentWindow.postMessage({ type: 'openagent-open' }, '*');
        }
        if (callbacks.onOpen) callbacks.onOpen();
      },

      close: function () {
        if (destroyed || !isOpen) return;
        chatWindow.style.display = 'none';
        isOpen = false;
        syncLoadingOverlay();
        if (launcherBtn) {
          launcherBtn.innerHTML = MSG_CIRCLE_SVG;
          launcherBtn.style.display = '';
        }
        if (callbacks.onClose) callbacks.onClose();
      },

      toggle: function () {
        if (isOpen) instance.close(); else instance.open();
      },

      isOpen: function () { return isOpen; },

      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        isOpen = false;
        if (viewportRafId) {
          cancelAnimationFrame(viewportRafId);
          viewportRafId = 0;
        }
        window.removeEventListener('message', onMessage);
        window.removeEventListener('resize', onViewportChange);
        if (window.visualViewport) {
          window.visualViewport.removeEventListener('resize', onViewportChange);
          window.visualViewport.removeEventListener('scroll', onViewportChange);
        }
        if (container.parentNode) container.parentNode.removeChild(container);
        delete instances[channelId];
      },
    };

    instances[channelId] = instance;
    return instance;
  }

  root.OpenAgentSDK = {
    version: VERSION,
    init: createInstance,
  };

  // Deprecated alias for snippets generated under the previous codename.
  // Remove after one major version once existing embeds are migrated.
  root.NewAgentSDK = root.OpenAgentSDK;

})(typeof window !== 'undefined' ? window : this);
