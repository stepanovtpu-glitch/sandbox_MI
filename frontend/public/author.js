/*!
 * Знак автора · А. В. Степанов (silverhead)
 * Правообладатель: ООО «ИНК», Управление автоматизации производства, 2026.
 * Подключение одной строкой:
 *   <script src="author.js" data-system="РИТМ" data-version="1.10.0" data-about="/api/about" defer></script>
 * Параметры: data-system, data-version, data-about (адрес JSON «о программе»), data-pos (br|bl), data-offset ("16px 16px"),
 * data-mode (float|inline — inline рисует плашку в элементе [data-author-slot]),
 * data-z (слой значка; ниже — чтобы выезжающие панели программы его закрывали),
 * data-extra (JSON дополнительных строк окна, например {"Методика":"Жихарева Н. В."}).
 */
(function () {
  "use strict";
  if (window.SilverheadAuthor) return;
  var me = document.currentScript || {};
  var ds = me.dataset || {};
  var cfg = {
    system: ds.system || document.title || "Программа",
    version: ds.version || "",
    about: ds.about || "",
    pos: ds.pos === "bl" ? "bl" : "br",
    offset: (ds.offset || "16px 16px").split(" "),
    mode: ds.mode || "float",
    z: ds.z || "",
    extra: (function () { try { return ds.extra ? JSON.parse(ds.extra) : {}; } catch (e) { return {}; } })()
  };
  var MARK = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 120 120\" ><defs><linearGradient id=\"shAs\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\"><stop offset=\"0\" stop-color=\"#F6F9FA\"/><stop offset=\".42\" stop-color=\"#C9D2D6\"/><stop offset=\".6\" stop-color=\"#9DAAAF\"/><stop offset=\"1\" stop-color=\"#E6ECEE\"/></linearGradient></defs><circle cx=\"60\" cy=\"60\" r=\"58\" fill=\"#0B3D31\"/><path d=\"M83.85 21.84 A45 45 0 1 0 83.85 98.16\" fill=\"none\" stroke=\"url(#shAs)\" stroke-width=\"6\" stroke-linecap=\"round\"/><line x1=\"77.49\" y1=\"32.01\" x2=\"80.93\" y2=\"26.50\" stroke=\"url(#shAs)\" stroke-width=\"2\" stroke-linecap=\"round\"/><line x1=\"27.00\" y1=\"60.00\" x2=\"20.50\" y2=\"60.00\" stroke=\"url(#shAs)\" stroke-width=\"2\" stroke-linecap=\"round\"/><line x1=\"77.49\" y1=\"87.99\" x2=\"80.93\" y2=\"93.50\" stroke=\"url(#shAs)\" stroke-width=\"2\" stroke-linecap=\"round\"/><path d=\"M47.5 84 L60 39 L72.5 84\" fill=\"none\" stroke=\"url(#shAs)\" stroke-width=\"6\" stroke-linejoin=\"miter\" stroke-miterlimit=\"10\"/><line x1=\"52.5\" y1=\"70.5\" x2=\"79.08\" y2=\"29.47\" stroke=\"#F2C88A\" stroke-width=\"2.8\" stroke-linecap=\"round\"/><circle cx=\"52.5\" cy=\"70.5\" r=\"3.6\" fill=\"#F2C88A\"/><circle cx=\"52.5\" cy=\"70.5\" r=\"1.4\" fill=\"#0B3D31\"/></svg>";
  var NAME = "Степанов А. В.", NICK = "silverhead", OWNER = "ООО «ИНК»", UNIT = "Управление автоматизации производства";
  var css = [
    ":host{all:initial}",
    "*{box-sizing:border-box;font-family:'Segoe UI',Arial,sans-serif}",
    ".b{position:fixed;z-index:2147483000;display:flex;align-items:center;gap:0;height:36px;border-radius:18px;background:#0B3D31;border:1px solid rgba(201,210,214,.35);box-shadow:0 6px 20px rgba(0,0,0,.28);cursor:pointer;overflow:hidden;max-width:36px;transition:max-width .35s ease,box-shadow .2s;opacity:.92;padding:0}",
    ".b:hover,.b:focus-visible{max-width:330px;opacity:1;box-shadow:0 10px 28px rgba(0,0,0,.35);outline:none}",
    ".b .m{flex:none;width:34px;height:34px;display:block}.b .m svg{width:34px;height:34px;display:block}",
    ".b .t{white-space:nowrap;padding:0 14px 0 8px;line-height:1.15}.b .t b{display:block;color:#fff;font-size:12.5px;font-weight:700}.b .t i{display:block;color:#9FC4B8;font-size:10.5px;font-style:normal}",
    ".i{display:inline-flex;align-items:center;gap:8px;height:36px;border-radius:18px;background:#0B3D31;border:1px solid rgba(201,210,214,.35);padding:0 14px 0 1px;cursor:pointer}",
    ".i .m svg{width:34px;height:34px;display:block}.i b{display:block;color:#fff;font-size:12.5px;line-height:1.15}.i i{display:block;color:#9FC4B8;font-size:10.5px;font-style:normal;line-height:1.15}",
    ".ov{position:fixed;inset:0;z-index:2147483001;background:rgba(4,16,13,.62);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;padding:16px;opacity:0;transition:opacity .2s}",
    ".ov.on{opacity:1}",
    ".dl{width:min(520px,100%);background:linear-gradient(160deg,#0E3A30,#071F19);color:#E6F2EE;border:1px solid rgba(201,210,214,.3);border-radius:22px;box-shadow:0 30px 80px rgba(0,0,0,.5);overflow:hidden;transform:translateY(8px);transition:transform .25s}",
    ".ov.on .dl{transform:none}",
    ".hd{display:flex;gap:18px;align-items:center;padding:22px 24px 16px;border-bottom:1px solid rgba(201,210,214,.18)}.hd svg{width:84px;height:84px;flex:none}",
    ".hd h3{margin:0;font-size:22px;letter-spacing:2px;color:#fff}.hd .n{margin-top:4px;font-size:14px;color:#C9D2D6;letter-spacing:1px}.hd .n em{font-style:normal;color:#F2C88A;font-size:11px;font-weight:700;letter-spacing:2.4px;margin-left:6px}",
    ".bd{padding:14px 24px 6px}.r{display:grid;grid-template-columns:150px 1fr;gap:10px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.06);font-size:13.5px}.r span{color:#9FC4B8}.r b{font-weight:600;color:#fff}",
    ".ft{padding:12px 24px 18px;font-size:11.5px;color:#8FB3A7;line-height:1.45}",
    ".x{position:absolute;right:14px;top:12px;width:34px;height:34px;border-radius:50%;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.06);color:#fff;font-size:18px;cursor:pointer}",
    ".wrap{position:relative}",
    "@media print{.b{display:none}}"
  ].join("\n");

  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  var host, root;
  function mount() {
    host = document.createElement("silverhead-author");
    root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    root.appendChild(el("style", null, css));
    var slot = document.querySelector("[data-author-slot]");
    if (cfg.mode === "inline" || slot) {
      var p = el("div", "i", "<span class='m'>" + MARK + "</span><span><b>Разработка А. В. Степанова</b><i>" + NICK + " · правообладатель " + OWNER + "</i></span>");
      p.setAttribute("role", "button"); p.setAttribute("tabindex", "0"); p.title = "Автор: " + NAME + " · Правообладатель: " + OWNER;
      p.onclick = open; p.onkeydown = function (e) { if (e.key === "Enter") open(); };
      root.appendChild(p);
      (slot || document.body).appendChild(host);
    } else {
      var b = el("div", "b", "<span class='m'>" + MARK + "</span><span class='t'><b>Разработка А. В. Степанова</b><i>" + NICK + " · правообладатель " + OWNER + "</i></span>");
      b.style[cfg.pos === "bl" ? "left" : "right"] = cfg.offset[0];
      b.style.bottom = cfg.offset[1] || cfg.offset[0];
      if (cfg.z) b.style.zIndex = cfg.z;
      b.setAttribute("role", "button"); b.setAttribute("tabindex", "0"); b.title = "Автор: " + NAME + " · Правообладатель: " + OWNER;
      b.onclick = open; b.onkeydown = function (e) { if (e.key === "Enter") open(); };
      root.appendChild(b);
      document.body.appendChild(host);
    }
  }

  function rows(extra) {
    var r = [["Система", esc(cfg.system) + (cfg.version ? " · " + esc(cfg.version) : "")], ["Автор", NAME + " (" + NICK + ")"], ["Правообладатель", OWNER], ["Подразделение", UNIT]];
    Object.keys(cfg.extra).forEach(function (k) { r.push([esc(k), esc(cfg.extra[k])]); });
    if (extra) Object.keys(extra).forEach(function (k) {
      if (["system", "version", "author", "owner", "handle", "unit"].indexOf(k) >= 0) return;
      var v = extra[k]; if (v == null || typeof v === "object") return; r.push([esc(k), esc(v)]);
    });
    return r.map(function (x) { return "<div class='r'><span>" + x[0] + "</span><b>" + x[1] + "</b></div>"; }).join("");
  }

  var ov = null;
  function open() {
    if (ov) return;
    ov = el("div", "ov");
    var dl = el("div", "dl wrap",
      "<button class='x' aria-label='Закрыть'>×</button>" +
      "<div class='hd'>" + MARK + "<div><h3>А. В. СТЕПАНОВ</h3><div class='n'>" + NICK + "<em>АВТОРСКАЯ РАЗРАБОТКА</em></div></div></div>" +
      "<div class='bd'>" + rows(null) + "</div>" +
      "<div class='ft'>Право авторства и право на имя неотчуждаемы (ст. 1265 ГК РФ). Исключительное право на служебную разработку принадлежит " + OWNER + " (ст. 1295 ГК РФ).</div>");
    ov.appendChild(dl);
    ov.onclick = function (e) { if (e.target === ov) close(); };
    dl.querySelector(".x").onclick = close;
    root.appendChild(ov);
    requestAnimationFrame(function () { ov.classList.add("on"); });
    if (cfg.about && window.fetch) {
      fetch(cfg.about, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (!j || !ov) return;
        if (j.version && !cfg.version) cfg.version = j.version;
        if (j.system) cfg.system = j.system;
        dl.querySelector(".bd").innerHTML = rows(j);
      }).catch(function () {});
    }
  }
  function close() { if (!ov) return; var o = ov; ov = null; o.classList.remove("on"); setTimeout(function () { o.remove(); }, 220); }
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });

  window.SilverheadAuthor = { open: open, close: close, config: cfg };
  try { console.info("%c silverhead %c " + cfg.system + " · автор: " + NAME + " · правообладатель: " + OWNER, "background:#0B3D31;color:#C9D2D6;padding:2px 6px;border-radius:4px;font-weight:700", "color:#5E8C80"); } catch (e) {}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
