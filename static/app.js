/* Live results, saved machines, favorites, copy button and theme toggle.
   The site works without this file; it adds live updates and conveniences.
   Saved machines and favorites live in this browser only (no sign-up). */
(function () {
  "use strict";

  var store = {
    get: function (key, fallback) {
      try {
        var raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
      } catch (e) {
        return fallback;
      }
    },
    set: function (key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
    }
  };

  // --- Theme -------------------------------------------------------------

  var themeButton = document.getElementById("theme-toggle");
  if (themeButton) {
    themeButton.addEventListener("click", function () {
      var root = document.documentElement;
      var next = root.dataset.theme === "light" ? "dark" : "light";
      root.dataset.theme = next;
      try { localStorage.setItem("sf.theme", next); } catch (e) {}
    });
  }

  // --- Copy button -------------------------------------------------------

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy]");
    if (!button) return;
    var source = document.querySelector(button.dataset.copy);
    if (!source) return;
    copyText(source.textContent).then(
      function () { flash(button, "Copied"); },
      function () { flash(button, "Select the text to copy"); }
    );
  });

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // Older browsers, or plain http: copy through a hidden textarea.
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(area);
      if (ok) { resolve(); } else { reject(); }
    });
  }

  function flash(button, text) {
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.textContent = text;
    setTimeout(function () { button.textContent = button.dataset.label; }, 1500);
  }

  // --- Calculator page only from here on --------------------------------

  var form = document.getElementById("calc-form");
  if (!form) return;

  var results = document.getElementById("results");
  var mobileBar = document.getElementById("mobile-bar");
  var unitSystem = form.dataset.units;
  var machineType = form.dataset.machineType;

  // --- Live results ------------------------------------------------------

  var timer = null;
  var inFlight = null;
  var convertingUnits = false;

  function formQuery() {
    var params = new URLSearchParams();
    new FormData(form).forEach(function (value, key) {
      if (String(value).trim() !== "") params.append(key, value);
    });
    return params.toString();
  }

  function update() {
    var query = formQuery();
    // Keep the address bar in step, so favorites and shared links work.
    history.replaceState(null, "", form.action + (query ? "?" + query : ""));

    if (inFlight) inFlight.abort();
    inFlight = new AbortController();
    fetch(form.dataset.resultsUrl + "?" + query, { signal: inFlight.signal })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.text();
      })
      .then(function (html) {
        results.innerHTML = html;
        updateMobileBar();
      })
      .catch(function (error) {
        // Aborted: a newer request replaced this one. Anything else: keep
        // showing the last good results.
        if (error.name !== "AbortError" && window.console) console.warn(error);
      });
  }

  function scheduleUpdate() {
    clearTimeout(timer);
    timer = setTimeout(update, 250);
  }

  form.addEventListener("input", function (event) {
    if (event.target.name) scheduleUpdate();  // skip the "name this machine" box
  });
  form.addEventListener("change", function () {
    applyVisibility();
    scheduleUpdate();
  });

  // The inch/metric buttons submit the form so the server converts values.
  document.querySelectorAll('[name="convert_to"]').forEach(function (button) {
    button.addEventListener("click", function () { convertingUnits = true; });
  });

  form.addEventListener("submit", function (event) {
    var submitter = event.submitter;
    if (convertingUnits || (submitter && submitter.name === "convert_to")) return;
    event.preventDefault();
    clearTimeout(timer);
    update();
  });

  function updateMobileBar() {
    var card = results.querySelector("[data-headline]");
    var text = card ? card.dataset.headline : "";
    mobileBar.textContent = text;
    mobileBar.hidden = !text;
  }

  // --- Show only the fields that apply -----------------------------------
  // data-show-if="field:value1,value2"  /  data-hide-if="field:value"

  function matches(rule) {
    var parts = rule.split(":");
    var field = form.elements[parts[0]];
    return Boolean(field) && parts[1].split(",").indexOf(field.value) !== -1;
  }

  function applyVisibility() {
    form.querySelectorAll("[data-show-if], [data-hide-if]").forEach(function (el) {
      var show = el.dataset.showIf ? matches(el.dataset.showIf) : !matches(el.dataset.hideIf);
      el.hidden = !show;
      // Hidden fields are disabled so they aren't sent or checked.
      el.querySelectorAll("input, select").forEach(function (input) { input.disabled = !show; });
    });
  }

  // --- Machines ----------------------------------------------------------
  // Saved machines are stored in inch units, like everything else.

  var MACHINE_FIELDS = ["max_rpm", "chuck_max_rpm", "max_feed", "spindle_hp"];
  var METRIC_FACTORS = { max_feed: 25.4, spindle_hp: 0.745699872 };  // same as units.py
  var machineSelect = document.getElementById("machine");
  var machineName = document.getElementById("machine-name");
  var saveMachineButton = document.getElementById("save-machine");
  var deleteMachineButton = document.getElementById("delete-machine");

  function toInch(name, text) {
    var value = parseFloat(text);
    if (isNaN(value)) return null;
    return unitSystem === "metric" && METRIC_FACTORS[name] ? value / METRIC_FACTORS[name] : value;
  }

  function fromInch(name, value) {
    if (value === null || value === undefined) return "";
    var shown = unitSystem === "metric" && METRIC_FACTORS[name] ? value * METRIC_FACTORS[name] : value;
    return String(Math.round(shown * 100) / 100);
  }

  function setField(name, value) {
    var input = form.elements[name];
    if (input && value !== undefined) input.value = value;
  }

  function allMachines() { return store.get("sf.machines", []); }

  function myMachines() {
    return allMachines().filter(function (m) { return m && m.type === machineType; });
  }

  function renderMyMachines(selectedId) {
    var group = document.getElementById("my-machines");
    if (group) group.remove();
    var mine = myMachines();
    if (mine.length) {
      group = document.createElement("optgroup");
      group.id = "my-machines";
      group.label = "My Machines";
      mine.forEach(function (m) {
        var option = document.createElement("option");
        option.value = "mine:" + m.id;
        option.textContent = m.name;
        group.appendChild(option);
      });
      machineSelect.appendChild(group);
    }
    if (selectedId) machineSelect.value = "mine:" + selectedId;
    deleteMachineButton.hidden = machineSelect.value.indexOf("mine:") !== 0;
  }

  if (machineSelect) {
    machineSelect.addEventListener("change", function () {
      var value = machineSelect.value;
      if (value.indexOf("preset:") === 0) {
        var option = machineSelect.selectedOptions[0];
        MACHINE_FIELDS.forEach(function (name) {
          if (name in option.dataset) setField(name, option.dataset[name]);
        });
      } else if (value.indexOf("mine:") === 0) {
        var id = value.slice(5);
        var machine = allMachines().filter(function (m) { return m.id === id; })[0];
        if (machine) {
          MACHINE_FIELDS.forEach(function (name) { setField(name, fromInch(name, machine[name])); });
        }
      }
      deleteMachineButton.hidden = value.indexOf("mine:") !== 0;
    });

    saveMachineButton.addEventListener("click", function () {
      var name = machineName.value.trim();
      if (!name) { machineName.focus(); return; }
      var machine = { id: String(Date.now()), name: name, type: machineType };
      MACHINE_FIELDS.forEach(function (field) {
        var input = form.elements[field];
        machine[field] = input ? toInch(field, input.value) : null;
      });
      var machines = allMachines();
      machines.push(machine);
      store.set("sf.machines", machines);
      machineName.value = "";
      renderMyMachines(machine.id);
      scheduleUpdate();
    });

    deleteMachineButton.addEventListener("click", function () {
      var id = machineSelect.value.slice(5);
      store.set("sf.machines", allMachines().filter(function (m) { return m.id !== id; }));
      machineSelect.value = "";
      renderMyMachines();
      scheduleUpdate();
    });

    // The server doesn't know about saved machines, so reselect from the link.
    var fromLink = new URLSearchParams(location.search).get("machine") || "";
    renderMyMachines(fromLink.indexOf("mine:") === 0 ? fromLink.slice(5) : null);
  }

  // --- Favorites ---------------------------------------------------------

  var favoritesList = document.getElementById("favorites-list");
  var favoriteName = document.getElementById("favorite-name");
  var saveFavoriteButton = document.getElementById("save-favorite");

  function renderFavorites() {
    var favorites = store.get("sf.favorites", []);
    favoritesList.innerHTML = "";
    if (!favorites.length) {
      var empty = document.createElement("li");
      empty.className = "muted";
      empty.textContent = "No saved setups yet.";
      favoritesList.appendChild(empty);
      return;
    }
    favorites.forEach(function (favorite, index) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href = favorite.url;
      link.textContent = favorite.name;
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-small";
      remove.textContent = "Remove";
      remove.addEventListener("click", function () {
        var current = store.get("sf.favorites", []);
        current.splice(index, 1);
        store.set("sf.favorites", current);
        renderFavorites();
      });
      item.appendChild(link);
      item.appendChild(remove);
      favoritesList.appendChild(item);
    });
  }

  if (favoritesList) {
    saveFavoriteButton.addEventListener("click", function () {
      var name = favoriteName.value.trim();
      if (!name) { favoriteName.focus(); return; }
      var query = formQuery();
      var favorites = store.get("sf.favorites", []);
      favorites.push({ name: name, url: form.action + (query ? "?" + query : "") });
      store.set("sf.favorites", favorites);
      favoriteName.value = "";
      renderFavorites();
    });
    renderFavorites();
  }

  // --- Start -------------------------------------------------------------

  applyVisibility();
  updateMobileBar();
})();
