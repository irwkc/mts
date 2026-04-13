/**
 * Open WebUI + gena: структурированные события презентации (delta.gena в SSE) + док-виджет.
 * + вставка iframe предпросмотра под ссылками *.pptx в чате.
 * + индикатор «gena думает…» на время стрима.
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

  /* ---------- SSE: прозрачный поток + извлечение delta.gena (построчно) ---------- */
  function dispatchGenaFromDataLine(line) {
    if (line.indexOf("data: ") !== 0) return;
    var raw = line.slice(6).trim();
    if (raw === "[DONE]") return;
    try {
      var j = JSON.parse(raw);
      var g =
        j &&
        j.choices &&
        j.choices[0] &&
        j.choices[0].delta &&
        j.choices[0].delta.gena;
      if (g) {
        window.dispatchEvent(new CustomEvent("gena-presentation", { detail: g }));
      }
    } catch (e) {
      /* ignore */
    }
  }

  function createGenaPassthroughTransform(onFirstChunk) {
    var dec = new TextDecoder();
    var lineBuf = "";
    var first = true;
    function pumpDone() {
      if (first) {
        first = false;
        if (typeof onFirstChunk === "function") onFirstChunk();
      }
    }
    function flushLines(finalBlock) {
      var parts = finalBlock.split(/\r?\n/);
      for (var i = 0; i < parts.length; i++) {
        dispatchGenaFromDataLine(parts[i]);
      }
    }
    return new TransformStream({
      transform: function (chunk, controller) {
        if (chunk && chunk.byteLength) pumpDone();
        controller.enqueue(chunk);
        lineBuf += dec.decode(chunk, { stream: true });
        var parts = lineBuf.split(/\r?\n/);
        lineBuf = parts.pop() || "";
        for (var i = 0; i < parts.length; i++) {
          dispatchGenaFromDataLine(parts[i]);
        }
      },
      flush: function () {
        lineBuf += dec.decode();
        pumpDone();
        flushLines(lineBuf);
        lineBuf = "";
      },
    });
  }

  function getFetchUrl(input) {
    if (typeof input === "string") return input;
    if (input && typeof input.url === "string") return input.url;
    return "";
  }

  function shouldInterceptChatCompletions(input, init) {
    var url = getFetchUrl(input);
    if (!url || url.indexOf("chat/completions") === -1) return false;
    var method = "GET";
    if (init && init.method) method = String(init.method).toUpperCase();
    else if (typeof Request !== "undefined" && input instanceof Request) {
      method = (input.method || "GET").toUpperCase();
    }
    if (method !== "POST") return false;
    if (init && init.body && typeof init.body === "string") {
      try {
        var b = JSON.parse(init.body);
        if (b && b.stream === false) return false;
      } catch (err) {
        return true;
      }
    }
    return true;
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
        lbl.textContent = "Готово — ссылки на PPTX/PDF в сообщении чата";
        box.appendChild(lbl);
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
