/**
 * Open WebUI + gena: структурированные события презентации (delta.gena в SSE) + док-виджет.
 * + вставка iframe предпросмотра под ссылками *.pptx в чате.
 * + индикатор «gena думает…» на время стрима; выбор стиля презентации кнопками.
 */
(function () {
  "use strict";

  var MARK = "data-gena-pptx-embed";

  /* ---------- «gena думает…» (пока идёт SSE) ---------- */
  function ensureThinkingIndicator() {
    var el = document.getElementById("gena-thinking-indicator");
    if (el) return el;
    el = document.createElement("div");
    el.id = "gena-thinking-indicator";
    el.setAttribute("aria-live", "polite");
    el.innerHTML =
      '<div class="gena-thinking-card">' +
      '<span class="gena-thinking-spinner" aria-hidden="true"></span>' +
      "<span>gena думает…</span>" +
      "</div>";
    document.body.appendChild(el);
    return el;
  }

  function setGenaThinking(on) {
    var el = ensureThinkingIndicator();
    if (on) el.classList.add("gena-thinking-visible");
    else el.classList.remove("gena-thinking-visible");
  }

  /* ---------- Поле ввода и отправка (разные версии Open WebUI) ---------- */
  function findChatInput() {
    var sels = [
      "#chat-input",
      "textarea#chat-input",
      'textarea[name="chat-input"]',
      "[contenteditable=true]#chat-input",
      "div#chat-input[contenteditable]",
      "textarea[placeholder*='Спросите']",
      "textarea[placeholder*='Ask']",
      "textarea[placeholder*='Message']",
      "main textarea",
    ];
    for (var i = 0; i < sels.length; i++) {
      var n = document.querySelector(sels[i]);
      if (n) return n;
    }
    return document.querySelector("textarea");
  }

  function findSendButton() {
    var sels = [
      "#send-message-button",
      'button[aria-label*="Send"]',
      'button[title*="Send"]',
      'button[type="submit"]',
    ];
    for (var i = 0; i < sels.length; i++) {
      var b = document.querySelector(sels[i]);
      if (b && b.offsetParent !== null) return b;
    }
    return document.querySelector('button[aria-label*="Отправ"]');
  }

  function setInputText(el, text) {
    if (!el) return;
    var t = text || "";
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      el.value = t;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      try {
        el.focus();
      } catch (e) {}
      return;
    }
    if (el.isContentEditable) {
      el.textContent = t;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      try {
        el.focus();
      } catch (e2) {}
    }
  }

  function submitStyleChoice(styleId, promptPlain) {
    var prefix = "[gena_style:" + styleId + "]\n\n";
    var body = (promptPlain || "").trim();
    var text = prefix + body;
    setInputText(findChatInput(), text);
    hideStylePicker();
    window.setTimeout(function () {
      var btn = findSendButton();
      if (btn) btn.click();
    }, 50);
  }

  /* ---------- Панель выбора стиля (кнопки) ---------- */
  function ensureStylePicker() {
    var el = document.getElementById("gena-style-picker");
    if (el) return el;
    el = document.createElement("div");
    el.id = "gena-style-picker";
    el.className = "gena-style-picker gena-style-picker-hidden";
    el.innerHTML =
      '<div class="gena-style-picker-inner">' +
      '<div class="gena-style-picker-title">Стиль презентации</div>' +
      '<div class="gena-style-btns" id="gena-style-btns"></div>' +
      '<button type="button" class="gena-style-cancel" id="gena-style-cancel">Закрыть</button>' +
      "</div>";
    document.body.appendChild(el);
    document.getElementById("gena-style-cancel").addEventListener("click", hideStylePicker);
    return el;
  }

  function hideStylePicker() {
    var el = document.getElementById("gena-style-picker");
    if (el) el.classList.add("gena-style-picker-hidden");
  }

  function showStylePicker(styles, promptPlain) {
    var el = ensureStylePicker();
    var box = document.getElementById("gena-style-btns");
    if (!box) return;
    box.innerHTML = "";
    var list = styles && styles.length ? styles : [];
    for (var i = 0; i < list.length; i++) {
      (function (st) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "gena-style-btn";
        var em = st.emoji ? st.emoji + " " : "";
        btn.textContent = em + (st.label || st.id || "");
        btn.addEventListener("click", function () {
          submitStyleChoice(st.id, promptPlain);
        });
        box.appendChild(btn);
      })(list[i]);
    }
    el.classList.remove("gena-style-picker-hidden");
  }

  /* ---------- SSE: прозрачный поток + извлечение delta.gena ---------- */
  function parseSseBlocks(text) {
    var events = [];
    var lines = text.split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (line.indexOf("data: ") !== 0) continue;
      var raw = line.slice(6).trim();
      if (raw === "[DONE]") continue;
      try {
        var j = JSON.parse(raw);
        var g =
          j &&
          j.choices &&
          j.choices[0] &&
          j.choices[0].delta &&
          j.choices[0].delta.gena;
        if (g) events.push(g);
      } catch (e) {
        /* ignore */
      }
    }
    return events;
  }

  function createGenaPassthroughTransform(onFirstChunk) {
    var dec = new TextDecoder();
    var buf = "";
    var first = true;
    function pumpDone() {
      if (first) {
        first = false;
        if (typeof onFirstChunk === "function") onFirstChunk();
      }
    }
    return new TransformStream({
      transform: function (chunk, controller) {
        if (chunk && chunk.byteLength) pumpDone();
        controller.enqueue(chunk);
        buf += dec.decode(chunk, { stream: true });
        var parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (var p = 0; p < parts.length; p++) {
          var block = parts[p];
          if (!block.trim()) continue;
          var evs = parseSseBlocks(block + "\n");
          for (var e = 0; e < evs.length; e++) {
            window.dispatchEvent(
              new CustomEvent("gena-presentation", { detail: evs[e] })
            );
          }
        }
      },
      flush: function () {
        buf += dec.decode();
        pumpDone();
        if (buf.trim()) {
          var evs = parseSseBlocks(buf);
          for (var e = 0; e < evs.length; e++) {
            window.dispatchEvent(
              new CustomEvent("gena-presentation", { detail: evs[e] })
            );
          }
        }
        buf = "";
      },
    });
  }

  function shouldInterceptChatCompletions(input, init) {
    var url = typeof input === "string" ? input : input && input.url;
    if (!url || url.indexOf("chat/completions") === -1) return false;
    init = init || {};
    if (!init.body || typeof init.body !== "string") return false;
    try {
      var b = JSON.parse(init.body);
      return !!(b && b.stream === true);
    } catch (err) {
      return false;
    }
  }

  var origFetch = window.fetch;
  window.fetch = function (input, init) {
    if (shouldInterceptChatCompletions(input, init || {})) {
      setGenaThinking(true);
      return origFetch
        .apply(this, arguments)
        .then(function (res) {
          if (!res.ok || !res.body) {
            setGenaThinking(false);
            return res;
          }
          try {
            var piped = res.body.pipeThrough(
              createGenaPassthroughTransform(function () {
                setGenaThinking(false);
              })
            );
            return new Response(piped, {
              status: res.status,
              statusText: res.statusText,
              headers: res.headers,
            });
          } catch (e) {
            setGenaThinking(false);
            return res;
          }
        })
        .catch(function (err) {
          setGenaThinking(false);
          throw err;
        });
    }
    return origFetch.apply(this, arguments);
  };

  /* ---------- Док-виджет ---------- */
  var dockState = {
    slides: [],
    phases: {},
  };

  function ensureDock() {
    var el = document.getElementById("gena-presentation-dock");
    if (el) return el;
    el = document.createElement("div");
    el.id = "gena-presentation-dock";
    el.className = "gena-dock-hidden";
    el.innerHTML =
      '<div class="gena-dock-head"><strong>gena · презентация</strong><div class="gena-dock-actions">' +
      '<button type="button" title="Свернуть" id="gena-dock-min">−</button>' +
      '<button type="button" title="Закрыть" id="gena-dock-close">×</button></div></div>' +
      '<div class="gena-dock-body" id="gena-dock-body"></div>';
    document.body.appendChild(el);
    document.getElementById("gena-dock-close").addEventListener("click", function () {
      el.classList.add("gena-dock-hidden");
    });
    document.getElementById("gena-dock-min").addEventListener("click", function () {
      el.classList.toggle("gena-dock-hidden");
    });
    return el;
  }

  function phaseRow(id, label) {
    return (
      '<div class="gena-phase" id="gena-ph-' +
      id +
      '"><span class="dot"></span><span>' +
      label +
      "</span></div>"
    );
  }

  function showDock() {
    var el = ensureDock();
    el.classList.remove("gena-dock-hidden");
  }

  function resetDock() {
    dockState = { slides: [], phases: {} };
    var body = document.getElementById("gena-dock-body");
    if (!body) return;
    body.innerHTML =
      phaseRow("research", "Веб-поиск и контекст") +
      phaseRow("llm", "Структура слайдов (LLM)") +
      phaseRow("images", "Картинки по слайдам") +
      phaseRow("build", "Сборка PPTX") +
      '<div id="gena-slides-grid" class="gena-slides-grid"></div>' +
      '<div id="gena-dock-complete" class="gena-complete"></div>' +
      '<div id="gena-dock-err" class="gena-err"></div>';
  }

  function setPhase(id, mode) {
    var row = document.getElementById("gena-ph-" + id);
    if (!row) return;
    row.classList.remove("gena-on", "gena-done");
    if (mode === "on") row.classList.add("gena-on");
    if (mode === "done") row.classList.add("gena-done");
  }

  function renderSlideTiles(structureSlides) {
    var grid = document.getElementById("gena-slides-grid");
    if (!grid || !structureSlides) return;
    grid.innerHTML = "";
    for (var i = 0; i < structureSlides.length; i++) {
      var s = structureSlides[i];
      var idx = typeof s.index === "number" ? s.index : i;
      var tile = document.createElement("div");
      tile.className = "gena-slide-tile gena-empty";
      tile.id = "gena-tile-" + idx;
      tile.innerHTML =
        '<div class="gena-ph">…</div><div class="gena-slide-cap">' +
        esc(s.title || "Слайд " + (idx + 1)) +
        "</div>";
      grid.appendChild(tile);
    }
  }

  function esc(s) {
    var t = document.createElement("div");
    t.textContent = s;
    return t.innerHTML;
  }

  function onSlideImage(detail) {
    var idx = detail.slide_index;
    var url = detail.preview_url;
    var tile = document.getElementById("gena-tile-" + idx);
    if (!tile) return;
    tile.classList.remove("gena-empty");
    tile.innerHTML = "";
    if (url) {
      var img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      img.src = url;
      tile.appendChild(img);
    } else {
      var ph = document.createElement("div");
      ph.className = "gena-ph";
      ph.textContent = "нет фото";
      tile.appendChild(ph);
    }
    var cap = document.createElement("div");
    cap.className = "gena-slide-cap";
    cap.textContent = "#" + (idx + 1);
    tile.appendChild(cap);
  }

  window.addEventListener("gena-presentation", function (ev) {
    var d = ev.detail;
    if (!d || !d.type) return;

    if (d.type === "presentation_style_prompt") {
      showStylePicker(d.styles || [], d.prompt_plain || "");
      return;
    }

    if (d.type === "presentation_start") {
      showDock();
      resetDock();
      setPhase("research", "on");
      return;
    }

    if (d.type === "phase") {
      if (d.phase === "research") {
        setPhase("research", "on");
      }
      if (d.phase === "research_done") {
        setPhase("research", "done");
      }
      if (d.phase === "llm") {
        setPhase("llm", "on");
      }
      if (d.phase === "images") {
        setPhase("llm", "done");
        setPhase("images", "on");
      }
      if (d.phase === "build") {
        setPhase("images", "done");
        setPhase("build", "on");
      }
      if (d.phase === "done") {
        setPhase("build", "done");
      }
      return;
    }

    if (d.type === "deck_structure") {
      renderSlideTiles(d.slides || []);
      return;
    }

    if (d.type === "slide_image") {
      onSlideImage(d);
      return;
    }

    if (d.type === "presentation_complete") {
      setPhase("build", "done");
      var box = document.getElementById("gena-dock-complete");
      if (box) {
        box.textContent = "";
        var lbl = document.createElement("div");
        lbl.className = "gena-dock-complete-label";
        lbl.textContent = "Готово";
        box.appendChild(lbl);
        var row = document.createElement("div");
        row.className = "gena-dock-actions-row";
        function addAction(href, label) {
          if (!href) return;
          var a = document.createElement("a");
          a.href = href;
          a.className = "gena-action-btn";
          a.target = "_blank";
          a.rel = "noopener";
          a.textContent = label;
          row.appendChild(a);
        }
        addAction(d.download_url, "Скачать PPTX");
        addAction(d.pdf_url, "Скачать PDF");
        addAction(d.editor_url, "Редактор");
        addAction(d.preview_page_url, "Предпросмотр");
        box.appendChild(row);
      }
      return;
    }

    if (d.type === "error") {
      var er = document.getElementById("gena-dock-err");
      if (er) er.textContent = d.message || "Ошибка";
    }
  });

  /* ---------- PPTX iframe под ссылками ---------- */
  function previewUrlFromAnchor(a) {
    var href = a.getAttribute("href");
    if (!href) return null;
    try {
      var u = new URL(href, window.location.href);
      if (!/\.pptx$/i.test(u.pathname)) return null;
      if (!/\/static\/presentations\/[^/]+\.pptx$/i.test(u.pathname)) return null;
      var rel = u.pathname.replace(/^\//, "");
      return u.origin + "/preview/pptx?path=" + encodeURIComponent(rel);
    } catch (e) {
      return null;
    }
  }

  function enhancePptxEmbeds(root) {
    var links = root.querySelectorAll('a[href*=".pptx"]');
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      if (a.getAttribute(MARK)) continue;
      var pv = previewUrlFromAnchor(a);
      if (!pv) continue;
      a.setAttribute(MARK, "1");
      var wrap = document.createElement("div");
      wrap.className = "gena-pptx-embed-wrap";
      var iframe = document.createElement("iframe");
      iframe.className = "gena-pptx-embed-iframe";
      iframe.src = pv;
      iframe.title = "Предпросмотр";
      iframe.loading = "lazy";
      iframe.setAttribute("referrerpolicy", "no-referrer-when-downgrade");
      wrap.appendChild(iframe);
      a.insertAdjacentElement("afterend", wrap);
    }
  }

  function bootEmbeds() {
    if (!document.body) return;
    var mo = new MutationObserver(function () {
      enhancePptxEmbeds(document.body);
    });
    mo.observe(document.body, { childList: true, subtree: true });
    enhancePptxEmbeds(document.body);
  }

  if (document.body) bootEmbeds();
  else document.addEventListener("DOMContentLoaded", bootEmbeds);
})();
