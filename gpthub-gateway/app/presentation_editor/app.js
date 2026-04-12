(function () {
  var $ = function (sel, el) {
    return (el || document).querySelector(sel);
  };

  var params = new URLSearchParams(window.location.search);
  var stem = (params.get("stem") || "").trim();

  var state = {
    deck_title: "",
    slides: [],
    research_excerpt: "",
  };

  function api(path, opts) {
    return fetch(path, opts).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          throw new Error(t || r.statusText);
        });
      }
      var ct = r.headers.get("content-type") || "";
      if (ct.indexOf("application/json") !== -1) return r.json();
      return r.text();
    });
  }

  function emptySlide() {
    return {
      title: "Слайд",
      subtitle: "",
      bullets: [""],
      speaker_notes: "",
      accent: "#1e40af",
      image_mode: "auto",
      image_query: "",
      image_prompt: "",
      visual_style: "corporate",
    };
  }

  function bulletsToText(bullets) {
    if (!Array.isArray(bullets)) return "";
    return bullets.join("\n");
  }

  function textToBullets(s) {
    return s
      .split("\n")
      .map(function (l) {
        return l.trim();
      })
      .filter(Boolean);
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function opt(val, cur) {
    var c = (cur || "auto") === val ? " selected" : "";
    return '<option value="' + val + '"' + c + ">" + val + "</option>";
  }

  function renderSlideCard(slide, i) {
    var btxt = bulletsToText(slide.bullets);
    return (
      '<section class="slide-card" data-idx="' +
      i +
      '"><h2>Слайд ' +
      (i + 1) +
      ' <button type="button" class="btn danger rm">Удалить</button></h2>' +
      "<label>Заголовок</label>" +
      '<input type="text" class="f-title" value="' +
      esc(slide.title || "") +
      '" />' +
      "<label>Подзаголовок</label>" +
      '<input type="text" class="f-sub" value="' +
      esc(slide.subtitle || "") +
      '" />' +
      "<label>Пункты (каждый с новой строки)</label>" +
      '<textarea class="f-bul">' +
      esc(btxt) +
      "</textarea>" +
      "<label>Заметки докладчика</label>" +
      '<textarea class="f-notes">' +
      esc(slide.speaker_notes || "") +
      "</textarea>" +
      '<div class="row2"><div><label>Акцент #RGB</label>' +
      '<input type="text" class="f-accent" value="' +
      esc(slide.accent || "#1e40af") +
      '" /></div><div><label>Картинки</label>' +
      '<select class="f-imode">' +
      opt("auto", slide.image_mode) +
      opt("search", slide.image_mode) +
      opt("generate", slide.image_mode) +
      "</select></div></div>" +
      "<label>Запрос картинки (веб, EN)</label>" +
      '<input type="text" class="f-iq" value="' +
      esc(slide.image_query || "") +
      '" />' +
      "<label>Промпт нейро (EN)</label>" +
      '<input type="text" class="f-ip" value="' +
      esc(slide.image_prompt || "") +
      '" />' +
      "</section>"
    );
  }

  function bindSlide(i) {
    var sec = document.querySelector('.slide-card[data-idx="' + i + '"]');
    if (!sec) return;
    sec.querySelector(".rm").addEventListener("click", function () {
      if (state.slides.length <= 1) {
        setMsg("Нужен хотя бы один слайд.", "err");
        return;
      }
      state.slides.splice(i, 1);
      render();
    });
  }

  function render() {
    var app = $("#app");
    if (!stem) {
      app.innerHTML =
        '<div class="empty">Укажите <code>?stem=presentation_xxxxxxxxxx</code> (из ссылки после генерации).</div>';
      return;
    }

    var pptxHref =
      window.location.origin + "/static/presentations/" + stem + ".pptx";

    app.innerHTML =
      '<header class="bar"><h1>Редактор презентации</h1>' +
      '<input type="text" id="deck_title" placeholder="Название презентации" />' +
      '<button type="button" class="btn secondary" id="btnReload">Обновить</button>' +
      '<button type="button" class="btn" id="btnSave">Сохранить</button>' +
      '<button type="button" class="btn" id="btnRebuild">Пересобрать PPTX</button>' +
      '<a class="pptx" href="' +
      pptxHref +
      '" target="_blank" rel="noopener">Скачать PPTX</a>' +
      "</header>" +
      '<div id="msg"></div><main id="main"></main>';

    $("#deck_title").value = state.deck_title || "";
    $("#deck_title").addEventListener("input", function () {
      state.deck_title = this.value;
    });

    $("#btnReload").addEventListener("click", loadDeck);
    $("#btnSave").addEventListener("click", saveDeck);
    $("#btnRebuild").addEventListener("click", rebuildPptx);

    var main = $("#main");
    var addBtn =
      '<p><button type="button" class="btn secondary" id="btnAddSlide">+ Слайд</button></p>';
    main.innerHTML =
      addBtn + state.slides.map(renderSlideCard).join("");

    $("#btnAddSlide").addEventListener("click", function () {
      state.slides.push(emptySlide());
      render();
    });

    state.slides.forEach(function (_, j) {
      bindSlide(j);
    });
  }

  function collectFromDom() {
    state.deck_title = $("#deck_title").value.trim();
    var sections = document.querySelectorAll(".slide-card");
    var slides = [];
    sections.forEach(function (sec) {
      slides.push({
        title: sec.querySelector(".f-title").value,
        subtitle: sec.querySelector(".f-sub").value,
        bullets: textToBullets(sec.querySelector(".f-bul").value),
        speaker_notes: sec.querySelector(".f-notes").value,
        accent: sec.querySelector(".f-accent").value.trim() || "#1e40af",
        image_mode: sec.querySelector(".f-imode").value,
        image_query: sec.querySelector(".f-iq").value,
        image_prompt: sec.querySelector(".f-ip").value,
        visual_style: "corporate",
      });
    });
    state.slides = slides;
  }

  function setMsg(text, cls) {
    var el = $("#msg");
    if (!el) return;
    el.textContent = text || "";
    el.className = cls || "";
  }

  function loadDeck() {
    if (!stem) return;
    $("#app").innerHTML =
      '<p class="empty">Загрузка…</p>';
    api("/presentation/api/deck/" + encodeURIComponent(stem))
      .then(function (data) {
        state.deck_title = data.deck_title || "";
        state.slides = Array.isArray(data.slides) ? data.slides : [];
        state.research_excerpt = data.research_excerpt || "";
        if (state.slides.length === 0) state.slides = [emptySlide()];
        render();
        setMsg("Загружено.", "ok");
      })
      .catch(function (e) {
        $("#app").innerHTML =
          '<div class="empty">Ошибка загрузки: ' +
          esc(e.message) +
          '</div><p class="empty"><a href="/presentation/editor/">Назад</a></p>';
      });
  }

  function saveDeck() {
    collectFromDom();
    if (!stem) return;
    setMsg("Сохранение…", "");
    api("/presentation/api/deck/" + encodeURIComponent(stem), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deck_title: state.deck_title,
        slides: state.slides,
        research_excerpt: state.research_excerpt,
      }),
    })
      .then(function () {
        setMsg("Сохранено.", "ok");
      })
      .catch(function (e) {
        setMsg("Ошибка: " + e.message, "err");
      });
  }

  function rebuildPptx() {
    collectFromDom();
    if (!stem) return;
    setMsg("Сохранение и пересборка PPTX…", "");
    api("/presentation/api/deck/" + encodeURIComponent(stem), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deck_title: state.deck_title,
        slides: state.slides,
        research_excerpt: state.research_excerpt,
      }),
    })
      .then(function () {
        return api(
          "/presentation/api/deck/" + encodeURIComponent(stem) + "/rebuild",
          { method: "POST" }
        );
      })
      .then(function () {
        setMsg("PPTX обновлён.", "ok");
      })
      .catch(function (e) {
        setMsg("Ошибка: " + e.message, "err");
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (stem) loadDeck();
    else render();
  });
})();
