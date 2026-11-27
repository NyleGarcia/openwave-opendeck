// Connecting to OpenDeck, once, for every inspector in this plugin.
//
// Two conventions are in the wild and OpenDeck ships both: the Elgato SDK
// calls a global function with the connection details, while OpenDeck's own
// newer plugins await a global promise of the same tuple. Supporting both is
// four lines and removes a whole class of "the panel is blank" bug.
//
// The context to send on is inActionInfo.context -- the ACTION's context, not
// the inspector's own uuid. Sending the inspector's uuid instead is accepted
// by the socket and then routed nowhere: settings are never saved, the
// plugin is never asked for its lists, and the panel sits empty with no error
// anywhere to explain it.
(function () {
  let socket = null;
  let context = null;
  let action = null;
  let controller = "Keypad";
  let settings = {};
  let answered = false;
  let strings = {};
  const listeners = [];

  // The words come from the plugin, in OpenDeck's language, with every
  // payload: an inspector is a page loaded from disk and cannot read lang/
  // itself. Until the first one arrives the English written in the page
  // stands in, and a key no language has shows as itself rather than blank.
  //
  // Placeholders are bare {name}s filled in one pass, so a value that
  // happens to contain braces -- a device called "{mix}" -- is not expanded
  // again. Translated text only ever reaches the page as text (textContent,
  // new Option), never as markup: a language file is data, and must not be
  // able to put an element on the page.
  const own = (object, name) =>
    Object.prototype.hasOwnProperty.call(object, name);

  function t(key, values) {
    const text = own(strings, key) && typeof strings[key] === "string"
      ? strings[key] : key;
    if (!values) return text;
    return text.replace(/\{(\w+)\}/g, (whole, name) =>
      own(values, name) ? String(values[name]) : whole);
  }

  function translate(payload) {
    if (!payload || !payload.strings || typeof payload.strings !== "object") {
      return;
    }
    strings = payload.strings;
    if (typeof payload.language === "string") {
      document.documentElement.lang = payload.language.replace("_", "-");
    }
    for (const node of document.querySelectorAll("[data-i18n]")) {
      const key = node.dataset.i18n;
      if (own(strings, key)) node.textContent = t(key);
    }
  }

  function start(port, _uuid, registerEvent, _info, actionInfo) {
    const info = typeof actionInfo === "string"
      ? JSON.parse(actionInfo) : actionInfo;
    context = info.context;
    action = info.action;
    settings = (info.payload && info.payload.settings) || {};
    controller = (info.payload && info.payload.controller) || "Keypad";
    socket = new WebSocket("ws://127.0.0.1:" + port);
    socket.onopen = () => {
      socket.send(JSON.stringify({ event: registerEvent, uuid: _uuid }));
      OpenWave.ask();
      // Asking once is not enough: the socket can be open before the plugin
      // has finished registering, and a reply that lands then is answered to
      // nobody. Retry until a payload arrives, then stop.
      let tries = 0;
      const retry = setInterval(() => {
        if (answered || ++tries > 6) { clearInterval(retry); return; }
        OpenWave.ask();
      }, 600);
    };
    socket.onmessage = (event) => {
      let message;
      try { message = JSON.parse(event.data); } catch (e) { return; }
      if (message.event === "sendToPropertyInspector") {
        answered = true;
        report("payload " + JSON.stringify(message.payload || {}).length + "b");
        try {
          translate(message.payload);
          listeners.forEach((fn) => fn(message.payload || {}));
        } catch (err) {
          report("render threw: " + err);
        }
      } else if (message.event === "didReceiveSettings") {
        settings = (message.payload && message.payload.settings) || settings;
      }
    };
    window.addEventListener("error", (e) => report(
      "error: " + e.message + " @" + e.filename + ":" + e.lineno));
    listeners.forEach((fn) => fn(null));
  }

  window.connectElgatoStreamDeckSocket = start;
  window.connectOpenActionSocket = start;
  if (globalThis.connectOpenActionSocketData) {
    Promise.resolve(globalThis.connectOpenActionSocketData)
      .then((details) => start.apply(null, details));
  }

  // A webview inside a Tauri window has no console anyone can read, so the
  // inspector reports what it did back to the plugin, which has a log file.
  // Diagnosing "the dropdown is empty" any other way means guessing.
  function report(text) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({
      event: "sendToPlugin", context, action,
      payload: { debug: text, action },
    }));
  }

  window.OpenWave = {
    report,
    // The string for `key` in OpenDeck's language, {placeholders} filled
    // from `values`. For text a page builds in script; text that is simply
    // in the page carries a data-i18n attribute instead and is filled above.
    t,
    // Replace a dropdown's contents with one unselectable line of text.
    only(select, text) {
      select.innerHTML = "";
      select.appendChild(new Option(text, ""));
    },
    controller: () => controller,
    settings: () => settings,
    onPayload(fn) { listeners.push(fn); },
    ask() {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({
        event: "sendToPlugin", context, action,
        payload: { request: "targets", action },
      }));
    },
    // Plugin-wide, not per key: a deck with one key in Amber and the rest in
    // Default reads as broken rather than customised.
    saveGlobal(changes) {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({
        event: "setGlobalSettings", context, payload: changes,
      }));
    },
    save(changes) {
      Object.assign(settings, changes);
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({
        event: "setSettings", context, payload: settings,
      }));
    },
  };
})();
