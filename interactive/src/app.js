/* Cislunar Sail Explorer: interface, 3-D scene and charts.
 * Needs window.SailEngine (engine.js) and window.SAIL_DATA (data.js); the 3-D view also needs three.js r128
 * with OrbitControls and the Line2 helpers. Without three.js the numbers, timeline and charts still work. */
(function () {
  "use strict";
  var E = window.SailEngine, DATA = window.SAIL_DATA, K = E.K, RAD = Math.PI / 180;
  var THREE = window.THREE;
  var HAS3D = !!(THREE && THREE.OrbitControls && THREE.Line2 && THREE.LineMaterial && THREE.LineGeometry);

  // ------------------------------------------------------------------ helpers
  function $(id) { return document.getElementById(id); }
  function clamp(x, a, b) { return x < a ? a : (x > b ? b : x); }
  function fmt(x, d) {
    if (x == null || !isFinite(x)) return "–";
    return x.toLocaleString("en-US", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
  }
  function dateOf(jd) { return E.dateFromJd(jd); }
  function isoDay(jd) { return dateOf(jd).toISOString().slice(0, 10); }
  function prettyDate(jd) {
    return dateOf(jd).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }
  function countLE(arr, t) { var lo = 0, hi = arr.length; while (lo < hi) { var m = (lo + hi) >> 1; if (arr[m] <= t) lo = m + 1; else hi = m; } return lo; }
  function lerpAt(ts, vs, t) {
    var n = ts.length; if (!n) return NaN;
    if (t <= ts[0]) return vs[0]; if (t >= ts[n - 1]) return vs[n - 1];
    var i = countLE(ts, t) - 1, w = (t - ts[i]) / (ts[i + 1] - ts[i]);
    return vs[i] * (1 - w) + vs[i + 1] * w;
  }
  function hexNum(h) { return parseInt(h.slice(1), 16); }
  function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
  function nrm(a) { return Math.sqrt(dot(a, a)); }
  function mv(M, v) { return [M[0][0] * v[0] + M[0][1] * v[1] + M[0][2] * v[2], M[1][0] * v[0] + M[1][1] * v[1] + M[1][2] * v[2], M[2][0] * v[0] + M[2][1] * v[1] + M[2][2] * v[2]]; }
  function mm(A, B) { var C = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]; for (var i = 0; i < 3; i++) for (var j = 0; j < 3; j++) C[i][j] = A[i][0] * B[0][j] + A[i][1] * B[1][j] + A[i][2] * B[2][j]; return C; }
  function tr(A) { return [[A[0][0], A[1][0], A[2][0]], [A[0][1], A[1][1], A[2][1]], [A[0][2], A[1][2], A[2][2]]]; }
  var P3 = [[1, 0, 0], [0, 0, 1], [0, -1, 0]];          // frame (x, y, z) -> three.js (x, z, -y): frame z is "up"

  var PH = {
    spiral:   { name: "Earth spiral",       color: "#3987e5" },
    energy:   { name: "Energy matching",    color: "#d95926" },
    approach: { name: "Phasing coast",      color: "#199e70" },
    trim:     { name: "Capture (modelled)", color: "#9085e9", dashed: true },
    ops:      { name: "On station",         color: "#d55181" },
  };
  var PH_ORDER = ["spiral", "energy", "approach", "trim", "ops"];
  var TNAME = { L1H: "EML1 halo", L2H: "EML2 halo", NRHO: "9:2 NRHO", DRO: "DRO", L4: "EML4", L5: "EML5" };
  var FILM_ORDER = ["AL_CP1", "AL_PEN_CR", "AL_MYLAR", "AL_AL_CP1", "CP1_THIN", "IDEAL"];
  var PRESET_ORDER = ["CR-S", "CR-H", "CR-HR", "CR-A", "SC", "NEAS", "ACS3", "LS2"];
  var ORBIT_INC = { GTO: 27, LEO: 28.5, GEO: 0 };

  // ------------------------------------------------------------------ form
  var FIELDS = ["launch", "orbit", "alt", "perigee", "apogee", "inc", "raanMode", "raan", "tliPerigee", "tliApogee", "tliLead", "target",
    "preset", "mass", "area", "film", "derate", "sepOn", "sepThrust", "isp", "prop", "gimbal", "sepInShadow", "deployAlt", "solar",
    "solarGravity", "maxYears"];

  function readParams() {
    var P = {};
    FIELDS.forEach(function (k) {
      var el = $(k);
      if (!el) return;
      if (el.type === "checkbox") P[k] = el.checked;
      else if (el.type === "number") P[k] = parseFloat(el.value);
      else P[k] = el.value;
    });
    return P;
  }

  function validate(P) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(P.launch || "")) return "Enter a launch date.";
    var y = +P.launch.slice(0, 4);
    if (y < 2025 || y > 2050) return "Choose a launch date between 2025 and 2050.";
    if (!(P.mass > 0)) return "Mass at launch must be above 0 kg.";
    if (!(P.area > 0)) return "Sail area must be above 0 m².";
    if (!(P.derate >= 10 && P.derate <= 100)) return "Optical efficiency must be between 10 and 100 %.";
    if (P.orbit === "LEO" && !(P.alt >= 200 && P.alt <= 5000)) return "LEO altitude must be between 200 and 5,000 km.";
    if (P.orbit === "GTO" && !(P.perigee >= 150 && P.apogee > P.perigee && P.apogee <= 100000))
      return "The GTO perigee must be at least 150 km and below the apogee (apogee up to 100,000 km).";
    if (P.orbit === "TLI" && !(P.tliPerigee >= 150 && P.tliApogee >= 250000 && P.tliApogee <= 1000000))
      return "TLI needs a perigee of at least 150 km and an apogee radius of 250,000–1,000,000 km.";
    if (P.orbit !== "TLI" && !(P.inc >= 0 && P.inc <= 180)) return "Inclination must be between 0 and 180°.";
    if (P.raanMode === "manual" && !(P.raan >= 0 && P.raan <= 360)) return "RAAN must be between 0 and 360°.";
    if (!(P.maxYears >= 1 && P.maxYears <= 15)) return "Give up after 1 to 15 years.";
    if (P.sepOn) {
      if (!(P.sepThrust > 0)) return "SEP thrust must be above 0 mN.";
      if (!(P.isp >= 200)) return "Specific impulse must be at least 200 s.";
      if (!(P.prop >= 0 && P.prop < P.mass)) return "Propellant must be less than the mass at launch.";
      if (!(P.gimbal >= 0 && P.gimbal <= 180)) return "Gimbal range must be between 0 and 180°.";
      if (!(P.deployAlt >= 0)) return "Deploy altitude cannot be negative.";
    }
    return null;
  }

  function engineParams(P) {
    var prm = {
      launch: P.launch, orbit: P.orbit, inc: P.inc, raanMode: P.raanMode, raan: P.raan, argp: 180,
      mass: P.mass, area: P.area, film: P.film, derate: P.derate, sepOn: P.sepOn, sepThrust: P.sepThrust, isp: P.isp,
      prop: P.prop, gimbal: P.gimbal, sepInShadow: P.sepInShadow, deployAlt: P.sepOn ? P.deployAlt : 0, target: P.target,
      solar: P.solar, solarGravity: P.solarGravity, maxYears: P.maxYears,
    };
    if (P.orbit === "LEO") prm.alt = P.alt;
    if (P.orbit === "GTO") { prm.perigee = P.perigee; prm.apogee = P.apogee; }
    if (P.orbit === "TLI") { prm.perigee = P.tliPerigee; prm.apogee = P.tliApogee; prm.tliLead = P.tliLead; }
    return prm;
  }

  function applyPreset(key) {
    var p = DATA.presets[key];
    if (!p) return;
    $("mass").value = p.mass; $("area").value = p.area; $("film").value = p.film;
    $("sepOn").checked = p.sep_mN > 0;
    if (p.sep_mN > 0) { $("sepThrust").value = p.sep_mN; $("isp").value = p.isp; $("prop").value = p.prop; $("gimbal").value = p.gimbal; }
    $("deployAlt").value = key === "CR-HR" ? 2000 : 0;
  }

  function syncVisibility() {
    var orbit = $("orbit").value;
    document.querySelectorAll("[data-for]").forEach(function (el) { el.hidden = el.getAttribute("data-for") !== orbit; });
    document.querySelectorAll("[data-notfor]").forEach(function (el) { el.hidden = el.getAttribute("data-notfor") === orbit; });
    $("raanBox").hidden = orbit === "TLI" || $("raanMode").value !== "manual";
    var sep = $("sepOn").checked;
    document.querySelectorAll("[data-sep]").forEach(function (el) {
      el.setAttribute("data-dim", sep ? "false" : "true");
      el.querySelectorAll("input").forEach(function (i) { i.disabled = !sep; });
    });
  }

  function syncDerived() {
    var P = readParams();
    if (!(P.mass > 0 && P.area > 0 && P.derate > 0)) { $("dAc").textContent = $("dLoad").textContent = $("dSide").textContent = "–"; return; }
    var sc = E.makeCraft({ mass: P.mass, area: P.area, film: P.film, derate: P.derate });
    $("dAc").textContent = fmt(sc.acMM, 3) + " mm/s²";
    $("dLoad").textContent = fmt(P.mass / P.area * 1000, 1) + " g/m²";
    $("dSide").textContent = fmt(Math.sqrt(P.area), 1) + " m";
  }

  function syncSite() {
    var v = parseFloat($("inc").value), site = $("site");
    var match = "";
    for (var i = 0; i < site.options.length; i++) if (site.options[i].value !== "" && Math.abs(parseFloat(site.options[i].value) - v) < 1e-6) match = site.options[i].value;
    site.value = match;
  }

  function initForm() {
    var pre = $("preset");
    PRESET_ORDER.forEach(function (k) {
      var p = DATA.presets[k]; if (!p) return;
      var o = document.createElement("option"); o.value = k; o.textContent = k + " · " + p.name; pre.appendChild(o);
    });
    var oc = document.createElement("option"); oc.value = "custom"; oc.textContent = "Custom"; pre.appendChild(oc);
    var film = $("film");
    FILM_ORDER.forEach(function (k) {
      var f = DATA.films[k]; if (!f) return;
      var o = document.createElement("option"); o.value = k; o.textContent = f.name; film.appendChild(o);
    });
    pre.value = "CR-S"; applyPreset("CR-S"); syncSite(); syncVisibility(); syncDerived();

    var form = $("form");
    form.addEventListener("submit", function (ev) { ev.preventDefault(); runNow(); });
    form.addEventListener("input", function (ev) {
      var id = ev.target.id;
      if (["mass", "area", "film", "sepOn", "sepThrust", "isp", "prop", "gimbal", "deployAlt"].indexOf(id) >= 0) $("preset").value = "custom";
      if (id === "inc") syncSite();
      syncDerived();
      if (ev.target.type === "number" || ev.target.type === "date") schedule(650);
    });
    form.addEventListener("change", function (ev) {
      var id = ev.target.id;
      if (id === "preset") { applyPreset(ev.target.value); syncDerived(); }
      if (id === "orbit") { var inc = ORBIT_INC[ev.target.value]; if (inc != null) { $("inc").value = inc; syncSite(); } }
      if (id === "site" && ev.target.value !== "") $("inc").value = ev.target.value;
      if (["mass", "area", "film", "sepOn"].indexOf(id) >= 0 && $("preset").value !== "custom") $("preset").value = "custom";
      syncVisibility(); syncDerived();
      if (id === "autorun") { if (ev.target.checked) schedule(10); return; }
      if (ev.target.type !== "number" && ev.target.type !== "date") schedule(60);
    });
    document.querySelectorAll("[data-shift]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = $("launch").value; if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return;
        var d = new Date(v + "T00:00:00Z"), k = +b.getAttribute("data-shift");
        var day = Math.min(d.getUTCDate(), 28), nd = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + k, day));
        $("launch").value = nd.toISOString().slice(0, 10);
        schedule(60, true);
      });
    });
  }

  var schedTimer = 0;
  function schedule(ms, force) {
    if (!force && !$("autorun").checked) return;
    clearTimeout(schedTimer);
    schedTimer = setTimeout(runNow, ms);
  }

  // ------------------------------------------------------------------ running the engine
  var runToken = 0, R = null, G = null;      // R: engine result; G: derived display data

  function setRunState(kind, msg, frac) {
    var el = $("runstate");
    el.className = "runstate" + (kind === "busy" ? " busy" : kind === "err" ? " err" : "");
    $("runmsg").textContent = msg;
    $("runbar").style.width = (clamp(frac || 0, 0, 1) * 100).toFixed(1) + "%";
  }

  function drive(gen, token, onProgress, onDone, onError, isLive) {
    (function step() {
      if (!isLive(token)) return;
      var s, start = performance.now();
      try {
        do { s = gen.next(); } while (!s.done && performance.now() - start < 14);
      } catch (e) { onError(e); return; }
      if (s.done) { onDone(s.value); return; }
      onProgress(s.value);
      setTimeout(step, 0);
    })();
  }

  var PHASE_BASE = { "Earth spiral": [0, 0.7], "Energy matching": [0.7, 0.88], "Phasing": [0.88, 1] };
  function overallFrac(p) {
    var b = PHASE_BASE[p.phase] || [0, 1];
    return b[0] + (b[1] - b[0]) * clamp(p.frac * (p.phase === "Earth spiral" ? 3 : 1), 0, 1);
  }

  function runNow() {
    clearTimeout(schedTimer);
    var P = readParams(), err = validate(P);
    $("formerr").hidden = !err; $("formerr").textContent = err || "";
    if (err) { setRunState("err", err, 0); return; }
    var token = ++runToken, t0 = performance.now();
    setRunState("busy", "Flying mission…", 0.02);
    if (G) document.body.classList.add("refreshing");
    drive(E.runMission(engineParams(P)), token,
      function (p) { setRunState("busy", p.msg, overallFrac(p)); },
      function (res) { onResult(res, P, performance.now() - t0); },
      function (e) { setRunState("err", "The engine stopped: " + e.message, 0); if (window.console) console.error(e); },
      function (tk) { return tk === runToken; });
  }

  function statusText(res) {
    var d = fmt(res.tEnd), ac = fmt(res.craft.acMM, 3);
    switch (res.status) {
      case "decayed": return "The orbit decayed: perigee fell below 130 km on day " + d + ". Start higher, deploy the sail above the drag layer with SEP, or use a lighter, larger sail.";
      case "timeout": return "The spiral had not reached cislunar energy after " + fmt(res.prm.maxYears) + " years (a_c = " + ac + " mm/s²). Add sail area, cut mass or start from a higher orbit.";
      case "impact": return "The trajectory struck the Moon on day " + d + " while matching energy. Shift the launch by a few days or pick another destination.";
      case "reentry": return "The trajectory re-entered Earth's atmosphere on day " + d + ". Shift the launch date.";
      case "escape": return "The sailcraft left the Earth–Moon system on day " + d + ". From TLI this happens for some arrival geometries; change the launch date or the aim angle.";
      default: return "";
    }
  }
  function statusShort(res) {
    return ({ decayed: "Orbit decayed", timeout: "Spiral too slow", impact: "Struck the Moon", reentry: "Re-entered", escape: "Escaped" })[res.status] || res.status;
  }

  function onResult(res, P, ms) {
    R = res; R.P = P;
    document.body.classList.remove("refreshing");
    var ok = res.status === "ok";
    setRunState(ok ? "ok" : "err", ok ? ("Flown in " + (ms / 1000).toFixed(ms < 1000 ? 2 : 1) + " s · " + fmt(res.summary.toTargetDays) + " days to station")
      : statusShort(res) + " on day " + fmt(res.tEnd), 1);
    G = buildDisplayData(res);
    renderTiles(); renderTimeline(); renderPhaseTable(); renderCharts();
    var b = $("banner"); b.hidden = ok; b.innerHTML = ""; if (!ok) { var s = document.createElement("b"); s.textContent = statusShort(res) + ". "; b.appendChild(s); b.appendChild(document.createTextNode(statusText(res))); }
    if (HAS3D) buildScene(res);
    var tStart = res.insertion ? Math.min(res.tEnd, res.insertion.t + 0.3 * (res.tEnd - res.insertion.t)) : res.tEnd;
    setPlaying(false); setTime(tStart);
    if (HAS3D) { camDist = 1150; aimCamera(viewMode); }
  }

  // ------------------------------------------------------------------ derived display data
  function buildDisplayData(res) {
    var g = { tEnd: res.tEnd, tHand: res.p1 ? res.p1.t[res.p1.t.length - 1] : 0, segs: [], spiral: null };
    if (res.p1) {
      var t = [], ra = [], rp = [];
      for (var i = 0; i < res.p1.t.length; i++) { var I = E.meeInfo(res.p1.y[i]); t.push(res.p1.t[i]); ra.push(I.ra); rp.push(I.rp); }
      g.spiral = { t: t, ra: ra, rp: rp, C: res.p1.C.slice(), m: res.p1.y.map(function (y) { return y[5]; }) };
    }
    function push(key, ts, Xs, ms) { if (ts && ts.length >= 2) g.segs.push({ key: key, t: ts.slice(), X: Xs.slice(), m: ms ? ms.slice() : null }); }
    if (res.p2) push("energy", res.p2.t, res.p2.X, res.p2.m);
    if (res.p3) push("approach", res.p3.t, res.p3.X, res.p3.m);
    if (res.p4) push("trim", res.p4.t, res.p4.X, null);
    if (res.ops) {
      var n = Math.max(240, Math.ceil(res.ops.days * 30)), ts = [], Xs = [];
      for (var j = 0; j <= n; j++) { var tau = res.ops.days * j / n; ts.push(res.ops.t0 + tau); Xs.push(E.orbitState(res.target, res.ops.i0, tau * K.DAY / K.T)); }
      push("ops", ts, Xs, null);
    }
    for (var s = 1; s < g.segs.length; s++) {           // stitch segments so the drawn path is continuous
      var a = g.segs[s - 1], b = g.segs[s];
      if (b.t[0] > a.t[a.t.length - 1] + 1e-9) { b.t.unshift(a.t[a.t.length - 1]); b.X.unshift(a.X[a.X.length - 1]); if (b.m) b.m.unshift(a.m ? a.m[a.m.length - 1] : b.m[0]); }
    }
    var Ct = res.target.C;
    g.segs.forEach(function (sg) {
      sg.rE = sg.X.map(function (X) { return Math.hypot(X[0] + K.MU, X[1], X[2]) * K.L; });
      if (sg.key === "trim") { var c0 = E.jacobi(sg.X[0]); sg.C = sg.t.map(function (tt, k) { return c0 + (Ct - c0) * k / (sg.t.length - 1); }); }
      else if (sg.key === "ops") sg.C = sg.t.map(function () { return Ct; });
      else sg.C = sg.X.map(function (X) { return E.jacobi(X); });
    });
    g.mFinal = res.mFinal != null ? res.mFinal : (res.p1 ? res.p1.y[res.p1.y.length - 1][5] : res.sc.m0);
    return g;
  }

  function phaseAt(t) {
    if (!R) return null;
    for (var i = 0; i < R.phases.length; i++) { var p = R.phases[i]; if (t < p.t1 || i === R.phases.length - 1) return p; }
    return null;
  }
  function segAt(t) {
    for (var i = 0; i < G.segs.length; i++) { var s = G.segs[i]; if (t <= s.t[s.t.length - 1]) return s; }
    return G.segs[G.segs.length - 1] || null;
  }

  // ------------------------------------------------------------------ readouts
  function tile(k, v, u, sub, hero, flag) {
    var d = document.createElement("div"); d.className = "tile" + (hero ? " hero" : "");
    var kk = document.createElement("div"); kk.className = "k"; kk.textContent = k; d.appendChild(kk);
    var vv = document.createElement("div"); vv.className = "v"; vv.textContent = v;
    if (u) { var sm = document.createElement("small"); sm.textContent = u; vv.appendChild(sm); }
    d.appendChild(vv);
    var ss = document.createElement("div"); ss.className = "s";
    if (flag) { var f = document.createElement("span"); f.className = "flag"; f.textContent = sub; ss.appendChild(f); } else ss.textContent = sub;
    d.appendChild(ss);
    return d;
  }

  function renderTiles() {
    var res = R, s = res.summary, ok = res.status === "ok", c = res.craft, host = $("tiles");
    host.innerHTML = "";
    var cis = (s.energyDays || 0) + (s.approachDays || 0) + (s.trimDays || 0);
    host.appendChild(tile("Days to station", ok ? fmt(s.toTargetDays) : "–", ok ? "d" : "",
      ok ? "On station " + prettyDate(res.jd0 + s.toTargetDays) + " · " + (TNAME[res.prm.target] || "") : statusShort(res), true, !ok));
    host.appendChild(tile("Earth spiral", res.p1 ? fmt(s.spiralDays) : "0", "d",
      res.p1 ? fmt(s.spiralDays / 365.25, 2) + " years to C ≈ 3.29" : "Not needed after TLI"));
    host.appendChild(tile("Cislunar arrival", ok ? fmt(cis) : "–", ok ? "d" : "",
      ok ? "Energy " + fmt(s.energyDays) + " · phasing " + fmt(s.approachDays) + " · capture " + fmt(s.trimDays) : "Not reached"));
    host.appendChild(tile("Characteristic accel.", fmt(c.acMM, 3), "mm/s²", c.sepMM > 0 ? "SEP adds " + fmt(c.sepMM, 3) + " mm/s²" : "Sail only, at 1 AU"));
    host.appendChild(tile("Sail loading", fmt(c.loading, 1), "g/m²", fmt(Math.sqrt(res.sc.area), 1) + " m square sail"));
    host.appendChild(tile("Propellant used", s.propLoaded > 0 ? fmt(s.propUsed, 2) : "–", s.propLoaded > 0 ? "kg" : "",
      s.propLoaded > 0 ? "of " + fmt(s.propLoaded, 1) + " kg loaded" : "No SEP on board"));
    if (res.handover) host.appendChild(tile("Plane offset at hand-over", fmt(res.handover.incMoon, 1), "°",
      "From lunar plane · RAAN " + fmt(res.raan, 1) + "°" + (res.prm.raanMode === "auto" ? " (aligned)" : "")));
    else host.appendChild(tile("Plane offset at hand-over", "0", "°", "TLI flies in the lunar plane"));
    host.appendChild(tile("Solar activity", fmt(res.f107), "sfu", "Lunar plane " + fmt(res.moonIncl, 1) + "° to equator at launch"));
  }

  function renderPhaseTable() {
    var tb = $("phaseTable").querySelector("tbody"); tb.innerHTML = "";
    R.phases.forEach(function (p) {
      var tr_ = document.createElement("tr");
      var c1 = document.createElement("td"), sw = document.createElement("i"); sw.className = "sw"; sw.style.background = PH[p.key].color;
      c1.appendChild(sw); c1.appendChild(document.createTextNode(PH[p.key].name));
      var c2 = document.createElement("td"); c2.textContent = prettyDate(R.jd0 + p.t0);
      var c3 = document.createElement("td"); c3.className = "n"; c3.textContent = fmt(p.t0, 1);
      var c4 = document.createElement("td"); c4.className = "n"; c4.textContent = fmt(p.t1 - p.t0, 1);
      tr_.appendChild(c1); tr_.appendChild(c2); tr_.appendChild(c3); tr_.appendChild(c4); tb.appendChild(tr_);
    });
  }

  // ------------------------------------------------------------------ timeline and playback
  var playT = 0, playing = false, dirty = true;

  function renderTimeline() {
    var bar = $("tlbar"), T = R.tEnd; bar.innerHTML = "";
    bar.style.display = "block";
    R.phases.forEach(function (p) {
      var i = document.createElement("i"), col = PH[p.key].color;
      i.style.position = "absolute"; i.style.top = "0"; i.style.bottom = "0";
      i.style.left = (p.t0 / T * 100) + "%";
      i.style.width = "max(3px, calc(" + ((p.t1 - p.t0) / T * 100) + "% - 2px))";
      i.style.background = PH[p.key].dashed ? "repeating-linear-gradient(90deg," + col + " 0 5px, transparent 5px 8px)" : col;
      bar.appendChild(i);
    });
    var sc = $("scrub"); sc.max = String(T); sc.value = String(playT);
    var lg = $("legend"); lg.innerHTML = "";
    R.phases.forEach(function (p) {
      var b = document.createElement("button"); b.type = "button";
      var sw = document.createElement("i"); sw.style.background = PH[p.key].color; if (PH[p.key].dashed) sw.className = "dash";
      var nm = document.createElement("span"); nm.textContent = PH[p.key].name;
      var du = document.createElement("b"); du.textContent = fmt(p.t1 - p.t0, (p.t1 - p.t0) < 10 ? 1 : 0) + " d";
      b.appendChild(sw); b.appendChild(nm); b.appendChild(du);
      b.setAttribute("aria-label", "Jump to " + PH[p.key].name + ", " + fmt(p.t1 - p.t0, 1) + " days");
      b.addEventListener("click", function () { setPlaying(false); setTime(p.t0 + 1e-3); });
      lg.appendChild(b);
    });
  }

  function setTime(t) {
    if (!R) return;
    playT = clamp(t, 0, R.tEnd);
    $("scrub").value = String(playT);
    var jd = R.jd0 + playT;
    $("tlday").innerHTML = "";
    var b = document.createElement("b"); b.textContent = "Day " + fmt(playT, 1);
    $("tlday").appendChild(b); $("tlday").appendChild(document.createTextNode(isoDay(jd)));
    chartDist.setCursor(playT); chartC.setCursor(playT);
    dirty = true;
  }

  function setPlaying(on) {
    playing = !!on && !!R;
    $("playicon").setAttribute("d", playing ? "M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z" : "M4 2.5v11l9-5.5z");
    $("play").setAttribute("aria-label", playing ? "Pause" : "Play");
  }

  function paceAt(t) {
    var v = $("speed").value;
    if (v !== "auto") return parseFloat(v);
    var p = phaseAt(t);
    if (!p) return 5;
    if (p.key === "spiral") return Math.max(8, (p.t1 - p.t0) / 36);
    if (p.key === "ops") return 3;
    return 2;
  }

  function initTimeline() {
    $("play").addEventListener("click", function () {
      if (!R) return;
      if (!playing && playT >= R.tEnd - 1e-6) setTime(0);
      setPlaying(!playing);
    });
    $("scrub").addEventListener("input", function () { setPlaying(false); setTime(parseFloat($("scrub").value)); });
  }

  // ------------------------------------------------------------------ charts (SVG)
  var SVGNS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, parent) {
    var e = document.createElementNS(SVGNS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function niceStep(span, n) { var raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p; return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p; }
  function linTicks(a, b, n) { var s = niceStep(b - a, n), out = []; for (var v = Math.ceil(a / s - 1e-9) * s; v <= b + 1e-9; v += s) out.push(+v.toFixed(10)); return out; }
  function logTicks(a, b) {
    var out = [];
    for (var e = Math.floor(Math.log10(a)); e <= Math.ceil(Math.log10(b)); e++) [1, 2, 5].forEach(function (m) { var v = m * Math.pow(10, e); if (v >= a * 0.999 && v <= b * 1.001) out.push(v); });
    return out;
  }
  function kmTick(v) { return v >= 1e6 ? fmt(v / 1e6) + "M" : v >= 1e3 ? fmt(v / 1e3) + "k" : fmt(v); }

  var chartSeq = 0;
  function Chart(host) {
    this.host = host; this.cfg = null; this.id = "c" + (++chartSeq);
    var self = this;
    host.addEventListener("keydown", function (ev) {
      if (!self.cfg || !R) return;
      var span = self.cfg.x1 - self.cfg.x0, step = span / 100 * (ev.shiftKey ? 10 : 1);
      if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
        ev.preventDefault(); setPlaying(false);
        var t = clamp((playT < self.cfg.x0 ? self.cfg.x0 : playT) + (ev.key === "ArrowRight" ? step : -step), self.cfg.x0, self.cfg.x1);
        setTime(t); self.showTip(t);
      }
    });
    host.addEventListener("blur", function () { self.hideTip(); });
  }
  Chart.prototype.draw = function (cfg) {
    var host = this.host; host.innerHTML = ""; this.cfg = cfg;
    var W = Math.max(280, Math.round(host.clientWidth || 600)), H = W < 520 ? 210 : 240;
    var m = { l: 50, r: 18, t: 14, b: 26 }, pw = W - m.l - m.r, ph = H - m.t - m.b;
    this.W = W; this.H = H; this.m = m;
    var X = function (x) { return m.l + (x - cfg.x0) / (cfg.x1 - cfg.x0) * pw; };
    var Y = cfg.ylog
      ? function (y) { return m.t + (Math.log(cfg.y1) - Math.log(Math.max(y, 1e-9))) / (Math.log(cfg.y1) - Math.log(cfg.y0)) * ph; }
      : function (y) { return m.t + (cfg.y1 - y) / (cfg.y1 - cfg.y0) * ph; };
    this.X = X; this.Y = Y;
    var root = svg("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, "aria-hidden": "true" }, host);
    root.style.touchAction = "pan-y";
    var defs = svg("defs", {}, root);
    var cp = svg("clipPath", { id: this.id + "clip" }, defs);
    svg("rect", { x: m.l, y: m.t, width: pw, height: ph }, cp);
    cfg.yTicks.forEach(function (v) {
      var y = Y(v);
      svg("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "#1f2a40", "stroke-width": 1 }, root);
      var tx = svg("text", { x: m.l - 7, y: y + 3.5, "text-anchor": "end", fill: "#7a869e", "font-size": 11, "font-family": "IBM Plex Mono, ui-monospace, monospace" }, root);
      tx.textContent = cfg.yFmt(v);
    });
    if (cfg.yUnit) { var u = svg("text", { x: m.l - 7, y: m.t - 3, "text-anchor": "end", fill: "#7a869e", "font-size": 10.5, "font-family": "IBM Plex Sans, sans-serif" }, root); u.textContent = cfg.yUnit; }
    linTicks(cfg.x0, cfg.x1, W < 520 ? 4 : 7).forEach(function (v) {
      var x = X(v);
      svg("line", { x1: x, x2: x, y1: H - m.b, y2: H - m.b + 4, stroke: "#34425e", "stroke-width": 1 }, root);
      var tx = svg("text", { x: x, y: H - m.b + 16, "text-anchor": "middle", fill: "#7a869e", "font-size": 11, "font-family": "IBM Plex Mono, ui-monospace, monospace" }, root);
      tx.textContent = fmt(v);
    });
    var xl = svg("text", { x: W - m.r, y: H - m.b + 16, "text-anchor": "end", fill: "#7a869e", "font-size": 10.5, "font-family": "IBM Plex Sans, sans-serif" }, root);
    xl.textContent = "";
    svg("line", { x1: m.l, x2: W - m.r, y1: H - m.b + 0.5, y2: H - m.b + 0.5, stroke: "#34425e", "stroke-width": 1 }, root);
    var plot = svg("g", { "clip-path": "url(#" + this.id + "clip)" }, root);
    (cfg.bands || []).forEach(function (b) {
      var d = "";
      for (var i = 0; i < b.t.length; i++) d += (i ? "L" : "M") + X(b.t[i]).toFixed(1) + " " + Y(b.hi[i]).toFixed(1);
      for (var j = b.t.length - 1; j >= 0; j--) d += "L" + X(b.t[j]).toFixed(1) + " " + Y(b.lo[j]).toFixed(1);
      svg("path", { d: d + "Z", fill: b.color, "fill-opacity": 0.12, stroke: "none" }, plot);
    });
    (cfg.refs || []).forEach(function (r) {
      if (r.y < Math.min(cfg.y0, cfg.y1) || r.y > Math.max(cfg.y0, cfg.y1)) return;
      var y = Y(r.y);
      svg("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "#5a6884", "stroke-width": 1 }, root);
      var tx = svg("text", { x: m.l + 6, y: r.below ? y + 13 : y - 5, "text-anchor": "start", fill: "#a5b0c6", "font-size": 11, "font-family": "IBM Plex Sans, sans-serif" }, root);
      tx.textContent = r.label;
    });
    cfg.series.forEach(function (s) {
      var d = "", pen = false;
      for (var i = 0; i < s.t.length; i++) {
        var v = s.v[i];
        if (v == null || !isFinite(v) || (cfg.ylog && v <= 0)) { pen = false; continue; }
        d += (pen ? "L" : "M") + X(s.t[i]).toFixed(1) + " " + Y(v).toFixed(1); pen = true;
      }
      var a = { d: d, fill: "none", stroke: s.color, "stroke-width": s.width || 2, "stroke-linejoin": "round", "stroke-linecap": "round" };
      if (s.dashed) a["stroke-dasharray"] = "5 4";
      svg("path", a, plot);
    });
    (cfg.notes || []).forEach(function (n) {
      var tx = svg("text", { x: W - m.r - 4, y: m.t + 12, "text-anchor": "end", fill: "#a5b0c6", "font-size": 11, "font-family": "IBM Plex Sans, sans-serif" }, root);
      tx.textContent = n;
    });
    this.cursor = svg("line", { x1: -10, x2: -10, y1: m.t, y2: H - m.b, stroke: "#e8ecf4", "stroke-width": 1, "stroke-opacity": 0.55 }, root);
    this.cross = svg("line", { x1: -10, x2: -10, y1: m.t, y2: H - m.b, stroke: "#a5b0c6", "stroke-width": 1 }, root);
    this.cross.style.display = "none";
    var hit = svg("rect", { x: m.l, y: 0, width: pw, height: H, fill: "transparent" }, root);
    hit.style.cursor = "crosshair";
    this.tip = document.createElement("div"); this.tip.className = "tip"; this.tip.hidden = true; host.appendChild(this.tip);
    var self = this;
    function xToT(ev) { var bb = root.getBoundingClientRect(), px = (ev.clientX - bb.left) * W / bb.width; return clamp(cfg.x0 + (px - m.l) / pw * (cfg.x1 - cfg.x0), cfg.x0, cfg.x1); }
    hit.addEventListener("pointermove", function (ev) { self.showTip(xToT(ev)); });
    hit.addEventListener("pointerleave", function () { self.hideTip(); });
    hit.addEventListener("click", function (ev) { setPlaying(false); setTime(xToT(ev)); });
    this.setCursor(playT);
  };
  Chart.prototype.setCursor = function (t) {
    if (!this.cfg || !this.cursor) return;
    var on = t >= this.cfg.x0 && t <= this.cfg.x1, x = on ? this.X(t) : -10;
    this.cursor.setAttribute("x1", x); this.cursor.setAttribute("x2", x);
  };
  Chart.prototype.showTip = function (t) {
    var cfg = this.cfg; if (!cfg) return;
    var x = this.X(t);
    this.cross.style.display = ""; this.cross.setAttribute("x1", x); this.cross.setAttribute("x2", x);
    var info = cfg.tooltip(t), tip = this.tip; tip.innerHTML = "";
    var hd = document.createElement("div"); hd.className = "t"; hd.textContent = "Day " + fmt(t, 1) + " · " + isoDay(R.jd0 + t); tip.appendChild(hd);
    info.forEach(function (row) {
      var r = document.createElement("div"); r.className = "r";
      var i = document.createElement("i"); i.style.background = row.color; if (row.dashed) i.style.background = "repeating-linear-gradient(90deg," + row.color + " 0 3px, transparent 3px 5px)";
      var b = document.createElement("b"); b.textContent = row.value;
      var s = document.createElement("span"); s.textContent = row.label;
      r.appendChild(i); r.appendChild(b); r.appendChild(s); tip.appendChild(r);
    });
    tip.hidden = false;
    var hostW = this.host.clientWidth, tw = tip.offsetWidth, scale = hostW / this.W;
    var left = x * scale + 12; if (left + tw > hostW) left = x * scale - tw - 12;
    tip.style.left = Math.max(0, left) + "px"; tip.style.top = (this.m.t * scale + 4) + "px";
  };
  Chart.prototype.hideTip = function () { if (this.tip) this.tip.hidden = true; if (this.cross) this.cross.style.display = "none"; };

  var chartDist, chartC, chartScan;

  function renderCharts() {
    if (!R) return;
    var g = G, res = R, series = [], bands = [], lo = Infinity, hi = 0;
    if (g.spiral) {
      bands.push({ t: g.spiral.t, lo: g.spiral.rp, hi: g.spiral.ra, color: PH.spiral.color });
      series.push({ t: g.spiral.t, v: g.spiral.ra, color: PH.spiral.color });
      series.push({ t: g.spiral.t, v: g.spiral.rp, color: PH.spiral.color, width: 1.5 });
      g.spiral.rp.forEach(function (v) { if (isFinite(v) && v > 0) lo = Math.min(lo, v); }); g.spiral.ra.forEach(function (v) { if (isFinite(v)) hi = Math.max(hi, v); });
    }
    g.segs.forEach(function (sg) {
      var step = Math.max(1, Math.floor(sg.t.length / 1400)), t = [], v = [];
      for (var i = 0; i < sg.t.length; i += step) { t.push(sg.t[i]); v.push(sg.rE[i]); if (isFinite(sg.rE[i])) { lo = Math.min(lo, sg.rE[i]); hi = Math.max(hi, sg.rE[i]); } }
      t.push(sg.t[sg.t.length - 1]); v.push(sg.rE[sg.rE.length - 1]);
      series.push({ t: t, v: v, color: PH[sg.key].color, dashed: !!PH[sg.key].dashed });
    });
    if (!isFinite(lo)) lo = K.R_E; if (!(hi > 0)) hi = 4e5;
    var y0 = Math.max(4000, lo * 0.8), y1 = Math.max(6e5, hi * 1.3);
    chartDist.draw({
      x0: 0, x1: res.tEnd, ylog: true, y0: y0, y1: y1, yTicks: logTicks(y0, y1), yFmt: kmTick, yUnit: "km",
      bands: bands, series: series, refs: [{ y: K.D_EM, label: "Moon's distance" }],
      tooltip: function (t) {
        var p = phaseAt(t), rows = [];
        if (g.spiral && t <= g.tHand) {
          rows.push({ color: PH.spiral.color, value: fmt(lerpAt(g.spiral.t, g.spiral.ra, t)) + " km", label: "apogee" });
          rows.push({ color: PH.spiral.color, value: fmt(lerpAt(g.spiral.t, g.spiral.rp, t)) + " km", label: "perigee" });
        } else { var sg = segAt(t); if (sg) rows.push({ color: PH[sg.key].color, dashed: PH[sg.key].dashed, value: fmt(lerpAt(sg.t, sg.rE, t)) + " km", label: "from Earth" }); }
        if (p) rows.push({ color: PH[p.key].color, dashed: PH[p.key].dashed, value: PH[p.key].name, label: "" });
        return rows;
      },
    });

    var span = res.tEnd - g.tHand, x0 = Math.max(0, g.tHand - Math.max(20, 0.35 * span)), Ct = res.target.C;
    var cs = [], cmin = Ct, cmax = -Infinity, clipped = false;
    if (g.spiral) {
      var ts = [], vs = [];
      for (var i = 0; i < g.spiral.t.length; i++) if (g.spiral.t[i] >= x0 && isFinite(g.spiral.C[i])) { ts.push(g.spiral.t[i]); vs.push(g.spiral.C[i]); cmax = Math.max(cmax, g.spiral.C[i]); }
      if (ts.length) cs.push({ t: ts, v: vs, color: PH.spiral.color });
    }
    g.segs.forEach(function (sg) {
      var step = Math.max(1, Math.floor(sg.t.length / 1400)), t = [], v = [];
      for (var i = 0; i < sg.t.length; i += step) { t.push(sg.t[i]); v.push(sg.C[i]); if (isFinite(sg.C[i])) { cmin = Math.min(cmin, sg.C[i]); cmax = Math.max(cmax, sg.C[i]); } }
      t.push(sg.t[sg.t.length - 1]); v.push(sg.C[sg.C.length - 1]);
      cs.push({ t: t, v: v, color: PH[sg.key].color, dashed: !!PH[sg.key].dashed });
    });
    if (!isFinite(cmax)) cmax = DATA.C_lagrange.L1 + 0.1;
    var cy1 = Math.min(3.45, Math.max(cmax, DATA.C_lagrange.L1 + 0.05) + 0.02), cy0 = Math.min(cmin, Ct) - 0.03;
    if (cmax > cy1) clipped = true;
    var refs = [{ y: DATA.C_lagrange.L1, label: "L1 gateway 3.188" }];
    var tLabel = "Destination " + Ct.toFixed(3);
    if (Math.abs(Ct - DATA.C_lagrange.L1) < 0.03) refs.push({ y: Ct, label: tLabel, below: true }); else refs.push({ y: Ct, label: tLabel });
    chartC.draw({
      x0: x0, x1: res.tEnd, ylog: false, y0: cy0, y1: cy1, yTicks: linTicks(cy0, cy1, 5), yFmt: function (v) { return v.toFixed(2); }, yUnit: "C",
      series: cs, refs: refs, notes: clipped && g.spiral ? ["Spiral values above " + cy1.toFixed(2) + " are off the top"] : [],
      tooltip: function (t) {
        var rows = [], p = phaseAt(t);
        if (g.spiral && t <= g.tHand) rows.push({ color: PH.spiral.color, value: lerpAt(g.spiral.t, g.spiral.C, t).toFixed(3), label: "approx., Moon ignored" });
        else { var sg = segAt(t); if (sg) rows.push({ color: PH[sg.key].color, dashed: PH[sg.key].dashed, value: lerpAt(sg.t, sg.C, t).toFixed(3), label: sg.key === "trim" ? "modelled" : "Jacobi C" }); }
        rows.push({ color: "#5a6884", value: Ct.toFixed(3), label: "destination" });
        if (p) rows.push({ color: PH[p.key].color, dashed: PH[p.key].dashed, value: PH[p.key].name, label: "" });
        return rows;
      },
    });
  }

  // ------------------------------------------------------------------ launch-date scan
  var scan = { busy: false, token: 0, items: [] };
  function drawScan() {
    var host = $("chartScan"); host.innerHTML = "";
    var items = scan.items;
    if (!items.length) {
      var p = document.createElement("p"); p.className = "cap"; p.style.margin = "4px 0 0";
      p.textContent = "No scan yet. Each launch month takes about a second to fly.";
      host.appendChild(p); return;
    }
    var W = Math.max(280, Math.round(host.clientWidth || 600)), H = W < 520 ? 190 : 210, m = { l: 50, r: 12, t: 22, b: 30 };
    var pw = W - m.l - m.r, ph = H - m.t - m.b;
    var vals = items.filter(function (it) { return it.days != null; }).map(function (it) { return it.days; });
    var vmax = vals.length ? Math.max.apply(null, vals) : 100, y1 = niceStep(vmax * 1.15, 4) * Math.ceil(vmax * 1.15 / niceStep(vmax * 1.15, 4));
    var root = svg("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, "aria-hidden": "true" }, host);
    var Y = function (v) { return m.t + (1 - v / y1) * ph; };
    linTicks(0, y1, 4).forEach(function (v) {
      var y = Y(v);
      svg("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: v === 0 ? "#34425e" : "#1f2a40", "stroke-width": 1 }, root);
      var tx = svg("text", { x: m.l - 7, y: y + 3.5, "text-anchor": "end", fill: "#7a869e", "font-size": 11, "font-family": "IBM Plex Mono, monospace" }, root);
      tx.textContent = fmt(v);
    });
    var u = svg("text", { x: m.l - 7, y: m.t - 9, "text-anchor": "end", fill: "#7a869e", "font-size": 10.5, "font-family": "IBM Plex Sans, sans-serif" }, root);
    u.textContent = "days";
    var n = 12, band = pw / n, bw = Math.min(24, band * 0.6);
    var imin = -1, imax = -1;
    items.forEach(function (it, i) { if (it.days == null) return; if (imin < 0 || it.days < items[imin].days) imin = i; if (imax < 0 || it.days > items[imax].days) imax = i; });
    var cur = $("launch").value;
    var tip = document.createElement("div"); tip.className = "tip"; tip.hidden = true; host.appendChild(tip);
    items.forEach(function (it, i) {
      var cx = m.l + band * (i + 0.5), g = svg("g", {}, root);
      if (it.days != null) {
        var y = Y(it.days), h = Y(0) - y, r = Math.min(4, h);
        var d = "M" + (cx - bw / 2) + " " + Y(0) + "V" + (y + r) + "Q" + (cx - bw / 2) + " " + y + " " + (cx - bw / 2 + r) + " " + y +
          "H" + (cx + bw / 2 - r) + "Q" + (cx + bw / 2) + " " + y + " " + (cx + bw / 2) + " " + (y + r) + "V" + Y(0) + "Z";
        svg("path", { d: d, fill: it.date === cur ? "#5598e7" : PH.spiral.color }, g);
        if (i === imin || i === imax) {
          var vt = svg("text", { x: cx, y: y - 6, "text-anchor": "middle", fill: "#e8ecf4", "font-size": 11, "font-family": "IBM Plex Mono, monospace" }, g);
          vt.textContent = fmt(it.days);
        }
      } else if (it.status) {
        var xt = svg("text", { x: cx, y: Y(0) - 6, "text-anchor": "middle", fill: "#e66767", "font-size": 12, "font-family": "IBM Plex Mono, monospace" }, g);
        xt.textContent = "×";
      }
      var d0 = new Date(it.date + "T00:00:00Z");
      var lb = svg("text", { x: cx, y: H - m.b + 15, "text-anchor": "middle", fill: it.date === cur ? "#e8ecf4" : "#7a869e", "font-size": 10.5, "font-family": "IBM Plex Mono, monospace", "font-weight": it.date === cur ? 600 : 400 }, g);
      lb.textContent = d0.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" });
      if (i === 0 || d0.getUTCMonth() === 0) { var yl = svg("text", { x: cx, y: H - m.b + 27, "text-anchor": "middle", fill: "#7a869e", "font-size": 10, "font-family": "IBM Plex Mono, monospace" }, g); yl.textContent = String(d0.getUTCFullYear()); }
      var hit = svg("rect", { x: cx - band / 2, y: m.t - 10, width: band, height: ph + 10, fill: "transparent" }, g);
      hit.style.cursor = it.status ? "pointer" : "default";
      hit.addEventListener("pointerenter", function () {
        tip.innerHTML = "";
        var t1 = document.createElement("div"); t1.className = "t"; t1.textContent = "Launch " + it.date; tip.appendChild(t1);
        var r = document.createElement("div"); r.className = "r";
        var sw = document.createElement("i"); sw.style.background = PH.spiral.color;
        var b = document.createElement("b"); b.textContent = it.days != null ? fmt(it.days) + " d" : (it.status ? statusShort({ status: it.status }) : "flying…");
        var s = document.createElement("span"); s.textContent = it.days != null ? "to station · " + it.arrival : "";
        r.appendChild(sw); r.appendChild(b); r.appendChild(s); tip.appendChild(r);
        tip.hidden = false;
        var sc = host.clientWidth / W, left = cx * sc + 10; if (left + tip.offsetWidth > host.clientWidth) left = cx * sc - tip.offsetWidth - 10;
        tip.style.left = Math.max(0, left) + "px"; tip.style.top = "0px";
      });
      hit.addEventListener("pointerleave", function () { tip.hidden = true; });
      hit.addEventListener("click", function () { if (!it.status) return; $("launch").value = it.date; runNow(); drawScan(); });
    });
  }

  function startScan() {
    if (scan.busy) { scan.busy = false; scan.token++; $("scanBtn").textContent = "Scan 12 launch months"; $("scanmsg").textContent = "Scan stopped."; return; }
    var P0 = readParams(), err = validate(P0);
    if (err) { $("scanmsg").textContent = err; return; }
    var d0 = new Date(P0.launch + "T00:00:00Z"), day = Math.min(d0.getUTCDate(), 28), dates = [];
    for (var k = 0; k < 12; k++) dates.push(new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth() + k, k === 0 ? d0.getUTCDate() : day)).toISOString().slice(0, 10));
    scan = { busy: true, token: scan.token + 1, items: dates.map(function (d) { return { date: d, days: null, status: null }; }) };
    var token = scan.token;
    $("scanBtn").textContent = "Stop scan";
    drawScan();
    var i = 0;
    function next() {
      if (token !== scan.token) return;
      if (i >= dates.length) {
        scan.busy = false; $("scanBtn").textContent = "Scan 12 launch months";
        var ok = scan.items.filter(function (it) { return it.days != null; });
        if (ok.length) {
          var best = ok.reduce(function (a, b) { return b.days < a.days ? b : a; }), worst = ok.reduce(function (a, b) { return b.days > a.days ? b : a; });
          $("scanmsg").textContent = "Fastest: launch " + best.date + ", " + fmt(best.days) + " days. Slowest: " + worst.date + ", " + fmt(worst.days) + " days." +
            (ok.length < dates.length ? " " + (dates.length - ok.length) + " launch dates did not arrive (×)." : "");
        } else $("scanmsg").textContent = "None of the twelve launch dates arrived.";
        drawScan(); return;
      }
      var P = Object.assign({}, P0, { launch: dates[i] });
      $("scanmsg").textContent = "Flying launch " + dates[i] + " (" + (i + 1) + " of 12)…";
      drive(E.runMission(engineParams(P)), token, function () {}, function (res) {
        var it = scan.items[i];
        it.status = res.status;
        if (res.status === "ok") { it.days = res.summary.toTargetDays; it.arrival = isoDay(res.jd0 + res.summary.toTargetDays); }
        i++; drawScan(); setTimeout(next, 0);
      }, function (e) { scan.items[i].status = "error"; i++; setTimeout(next, 0); }, function (tk) { return tk === scan.token; });
    }
    next();
  }

  // ------------------------------------------------------------------ 3-D scene
  var S = null, frameMode = "inertial", viewMode = "3d", focusMode = "earth", autoZoom = true, camDist = 1150, keepScale = false;
  var lineMats = [], vpW = 800, vpH = 500;

  function lineMat(color, width, opacity, dashed) {
    var m = new THREE.LineMaterial({ color: hexNum(color), linewidth: width, transparent: true, opacity: opacity, dashed: !!dashed,
      dashSize: 9, gapSize: 6, dashScale: 1, depthWrite: opacity >= 1 });
    m.resolution.set(vpW, vpH); lineMats.push(m); return m;
  }
  function dropMat(m) { var i = lineMats.indexOf(m); if (i >= 0) lineMats.splice(i, 1); }

  function Track(parent, times, flat, color, o) {
    o = o || {};
    this.times = times; this.nseg = times.length - 1;
    var gF = new THREE.LineGeometry(); gF.setPositions(flat);
    var gP = new THREE.LineGeometry(); gP.setPositions(flat);
    this.fut = new THREE.Line2(gF, lineMat(color, (o.width || 2) * 0.75, o.dim == null ? 0.26 : o.dim, o.dashed));
    this.past = new THREE.Line2(gP, lineMat(color, o.width || 2, 1, o.dashed));
    if (o.dashed) { this.fut.computeLineDistances(); this.past.computeLineDistances(); }
    this.fut.renderOrder = 1; this.past.renderOrder = 2;
    parent.add(this.fut); parent.add(this.past);
  }
  Track.prototype.setTime = function (t) {
    var k = countLE(this.times, t) - 1;
    if (k < 1) this.past.visible = false;
    else { this.past.visible = true; this.past.geometry.instanceCount = Math.min(k, this.nseg); }
  };
  Track.prototype.dispose = function () {
    [this.fut, this.past].forEach(function (l) { if (l.parent) l.parent.remove(l); l.geometry.dispose(); l.material.dispose(); dropMat(l.material); });
  };

  function DynLine(parent, nPts, color, width, opacity) {
    this.n = nPts;
    this.geo = new THREE.LineGeometry(); this.geo.setPositions(new Float32Array(nPts * 3));
    this.line = new THREE.Line2(this.geo, lineMat(color, width, opacity)); this.line.frustumCulled = false; this.line.renderOrder = 3;
    parent.add(this.line);
  }
  DynLine.prototype.set = function (flat) {
    var buf = this.geo.attributes.instanceStart.data, a = buf.array, n = this.n;
    for (var i = 0; i < n - 1; i++) {
      var j = i * 6, k = i * 3;
      a[j] = flat[k]; a[j + 1] = flat[k + 1]; a[j + 2] = flat[k + 2]; a[j + 3] = flat[k + 3]; a[j + 4] = flat[k + 4]; a[j + 5] = flat[k + 5];
    }
    buf.needsUpdate = true;
  };

  function setM(obj, M, s) {
    s = s || 1;
    obj.matrix.set(M[0][0] * s, M[0][1] * s, M[0][2] * s, 0, M[1][0] * s, M[1][1] * s, M[1][2] * s, 0, M[2][0] * s, M[2][1] * s, M[2][2] * s, 0, 0, 0, 0, 1);
    obj.matrixWorldNeedsUpdate = true;
  }
  function v3(a) { return new THREE.Vector3(a[0], a[1], a[2]); }

  function glowTexture() {
    var c = document.createElement("canvas"); c.width = c.height = 64;
    var x = c.getContext("2d"), gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.25, "rgba(255,240,200,.55)"); gr.addColorStop(1, "rgba(255,220,150,0)");
    x.fillStyle = gr; x.fillRect(0, 0, 64, 64);
    var t = new THREE.CanvasTexture(c); return t;
  }

  function ringPoints(r, n) { var p = []; for (var i = 0; i <= n; i++) { var a = 2 * Math.PI * i / n; p.push(new THREE.Vector3(r * Math.cos(a), r * Math.sin(a), 0)); } return p; }

  function initScene() {
    var canvas = $("scene");
    var renderer;
    try { renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true }); }
    catch (e) { HAS3D = false; noThree("This browser could not start WebGL, so the 3-D view is off. The numbers, timeline and charts still update."); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x04070d, 1);
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(38, 1.6, 0.5, 60000);
    var controls = new THREE.OrbitControls(camera, canvas);
    controls.enableDamping = true; controls.dampingFactor = 0.12; controls.rotateSpeed = 0.55; controls.zoomSpeed = 0.9;
    controls.enablePan = false; controls.minDistance = 12; controls.maxDistance = 12000;
    canvas.addEventListener("wheel", function () { setAutoZoom(false); }, { passive: true });
    canvas.addEventListener("touchstart", function (ev) { if (ev.touches.length > 1) setAutoZoom(false); }, { passive: true });
    S = { renderer: renderer, scene: scene, camera: camera, controls: controls, perResult: [], tracks: [] };

    var sun = new THREE.DirectionalLight(0xfff3dc, 1.35); scene.add(sun); scene.add(sun.target); S.sunLight = sun;
    scene.add(new THREE.AmbientLight(0x3a4866, 0.55));

    // star field (fixed seed)
    var seed = 7, rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    var sp = new Float32Array(1600 * 3), scol = new Float32Array(1600 * 3);
    for (var i = 0; i < 1600; i++) {
      var u = 2 * rnd() - 1, ph = 2 * Math.PI * rnd(), s = Math.sqrt(1 - u * u), R0 = 20000;
      sp[i * 3] = R0 * s * Math.cos(ph); sp[i * 3 + 1] = R0 * u; sp[i * 3 + 2] = R0 * s * Math.sin(ph);
      var b = 0.35 + 0.65 * Math.pow(rnd(), 3), tint = rnd();
      scol[i * 3] = b * (0.85 + 0.15 * tint); scol[i * 3 + 1] = b * 0.9; scol[i * 3 + 2] = b * (1.0 - 0.1 * tint);
    }
    var sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.BufferAttribute(sp, 3)); sg.setAttribute("color", new THREE.BufferAttribute(scol, 3));
    S.stars = new THREE.Points(sg, new THREE.PointsMaterial({ size: 1.6, sizeAttenuation: false, vertexColors: true, transparent: true, opacity: 0.8, depthWrite: false }));
    scene.add(S.stars);

    // frame-plane grid: rings every 100,000 km
    S.grid = new THREE.Group(); S.grid.matrixAutoUpdate = false; setM(S.grid, P3); scene.add(S.grid);
    [100, 200, 300, 400, 500].forEach(function (r) {
      S.grid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(ringPoints(r, 256)), new THREE.LineBasicMaterial({ color: 0x141d31, transparent: true, opacity: 0.9 })));
    });

    // Earth
    S.earth = new THREE.Group(); scene.add(S.earth);
    S.earth.add(new THREE.Mesh(new THREE.SphereGeometry(K.R_E / 1000, 48, 32), new THREE.MeshStandardMaterial({ color: 0x2f6fc4, emissive: 0x061427, roughness: 0.78, metalness: 0 })));
    S.earth.add(new THREE.Mesh(new THREE.SphereGeometry(K.R_E / 1000 * 1.045, 48, 32), new THREE.MeshBasicMaterial({ color: 0x5fa2ff, transparent: true, opacity: 0.12, side: THREE.BackSide, depthWrite: false })));
    S.earthAxes = new THREE.Group(); S.earthAxes.matrixAutoUpdate = false; scene.add(S.earthAxes);
    S.earthAxes.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(ringPoints(K.R_E / 1000 * 1.18, 96)), new THREE.LineBasicMaterial({ color: 0x6da7ec, transparent: true, opacity: 0.55 })));
    S.earthAxes.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, -K.R_E / 1000 * 1.5), new THREE.Vector3(0, 0, K.R_E / 1000 * 1.5)]), new THREE.LineBasicMaterial({ color: 0x9ec5f4, transparent: true, opacity: 0.7 })));

    // Moon
    S.moon = new THREE.Mesh(new THREE.SphereGeometry(K.R_M / 1000, 40, 24), new THREE.MeshStandardMaterial({ color: 0xbab7af, roughness: 0.95, metalness: 0, emissive: 0x0b0b0c }));
    scene.add(S.moon);

    // frame groups
    S.eciGroup = new THREE.Group(); S.eciGroup.matrixAutoUpdate = false; scene.add(S.eciGroup);
    S.rotGroup = new THREE.Group(); S.rotGroup.matrixAutoUpdate = false; scene.add(S.rotGroup);
    S.rotOnly = new THREE.Group(); S.rotGroup.add(S.rotOnly);

    // Moon's orbit (inertial view) and lunar-distance ring (rotating view)
    S.moonRing = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ringPoints(1, 160)), new THREE.LineBasicMaterial({ color: 0x8a93a8, transparent: true, opacity: 0.45 }));
    S.moonRing.frustumCulled = false; S.eciGroup.add(S.moonRing);
    S.rotOnly.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(ringPoints(K.D_EM / 1000, 256)), new THREE.LineBasicMaterial({ color: 0x8a93a8, transparent: true, opacity: 0.35 })));

    // Lagrange points
    S.lpts = {};
    ["L1", "L2", "L3", "L4", "L5"].forEach(function (k) {
      var L = DATA.lagrange[k], p = [(L[0] + K.MU) * K.L / 1000, L[1] * K.L / 1000, L[2] * K.L / 1000];
      var mk = new THREE.Mesh(new THREE.OctahedronGeometry(2.4), new THREE.MeshBasicMaterial({ color: 0x7a869e }));
      mk.position.set(p[0], p[1], p[2]); S.rotGroup.add(mk); S.lpts[k] = { mesh: mk, raw: p };
    });

    // catalogue orbits (faint) for context
    S.catalog = {};
    DATA.orbits.forEach(function (o) {
      var pts = o.states.map(function (X) { return new THREE.Vector3((X[0] + K.MU) * K.L / 1000, X[1] * K.L / 1000, X[2] * K.L / 1000); });
      pts.push(pts[0].clone());
      var ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x4a5672, transparent: true, opacity: 0.55 }));
      S.rotGroup.add(ln); S.catalog[o.key] = ln;
    });

    // Sun arrow
    S.sunArrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0), 150, 0xf5c451, 12, 6);
    scene.add(S.sunArrow);

    // sailcraft
    S.craft = new THREE.Group(); scene.add(S.craft);
    S.pivot = new THREE.Group(); S.craft.add(S.pivot);
    var plane = new THREE.PlaneGeometry(1, 1);
    S.pivot.add(new THREE.Mesh(plane, new THREE.MeshStandardMaterial({ color: 0xf5c451, emissive: 0x5a420c, metalness: 0.3, roughness: 0.45, side: THREE.DoubleSide })));
    S.pivot.add(new THREE.LineSegments(new THREE.EdgesGeometry(plane), new THREE.LineBasicMaterial({ color: 0xffe9b0 })));
    S.pivot.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-.5, -.5, 0.002), new THREE.Vector3(.5, .5, 0.002), new THREE.Vector3(-.5, .5, 0.002), new THREE.Vector3(.5, -.5, 0.002)]),
      new THREE.LineBasicMaterial({ color: 0x3a2a06 })));
    S.normal = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, 0), 1.05, 0x9ec5f4, 0.3, 0.16); S.pivot.add(S.normal);
    S.glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), color: 0xf5c451, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    S.glow.scale.set(2.2, 2.2, 1); S.craft.add(S.glow);

    // per-frame dynamic lines (inertial view during the spiral)
    S.oscLine = new DynLine(S.eciGroup, 181, "#86b6ef", 2, 0.95);
    S.trail = new DynLine(S.eciGroup, 121, "#cde2fb", 2.4, 1);

    // labels
    var lh = $("labels"); S.labels = {};
    [["earth", "Earth", "big"], ["moon", "Moon", "big"], ["sun", "Sun", "big sun"], ["craft", "Sailcraft", "craft"], ["target", "", ""],
     ["L1", "L1", ""], ["L2", "L2", ""], ["L3", "L3", ""], ["L4", "L4", ""], ["L5", "L5", ""]].forEach(function (a) {
      var d = document.createElement("div"); d.className = "lbl " + a[2]; d.textContent = a[1]; lh.appendChild(d); S.labels[a[0]] = d;
    });

    var ro = new ResizeObserver(resize3D); ro.observe($("viewport"));
    resize3D();
    initViewbar();
    aimCamera("3d");
  }

  function noThree(msg) {
    var d = document.createElement("div"); d.className = "no3d"; d.textContent = msg; $("viewport").appendChild(d);
    $("hud").hidden = true; document.querySelector(".viewbar").hidden = true;
  }

  function resize3D() {
    if (!S) return;
    var vp = $("viewport"), w = Math.max(200, vp.clientWidth), h = Math.max(200, vp.clientHeight);
    vpW = w; vpH = h;
    S.renderer.setSize(w, h, false);
    S.camera.aspect = w / h; S.camera.updateProjectionMatrix();
    lineMats.forEach(function (m) { m.resolution.set(w, h); });
    dirty = true;
  }

  function clearResultObjects() {
    S.tracks.forEach(function (t) { t.dispose(); }); S.tracks = [];
    S.perResult.forEach(function (o) { if (o.parent) o.parent.remove(o); if (o.geometry) o.geometry.dispose(); if (o.material) { o.material.dispose(); dropMat(o.material); } });
    S.perResult = [];
  }

  function buildScene(res) {
    clearResultObjects();
    var g = G, F = E.frameAt(res.jd0 + g.tHand), z = F.zh;
    var x = [1 - z[0] * z[0], -z[0] * z[1], -z[0] * z[2]], xn = nrm(x); x = [x[0] / xn, x[1] / xn, x[2] / xn];
    var y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]];
    S.B = [x, y, z];                    // display basis: lunar orbit plane at hand-over is horizontal
    S.Meci = mm(P3, S.B);

    // spiral: osculating ellipses (inertial) coloured from dim (early) to bright (late)
    S.ellipses = [];
    if (res.p1) {
      var N = 56, c0 = new THREE.Color(0x173156), c1 = new THREE.Color(0x6da7ec);
      for (var k = 0; k < N; k++) {
        var tk = g.tHand * k / (N - 1), pts = E.phase1Ellipse(res, tk, 160).map(function (r) { return new THREE.Vector3(r[0] / 1000, r[1] / 1000, r[2] / 1000); });
        var col = c0.clone().lerp(c1, k / (N - 1));
        var ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.85 }));
        S.eciGroup.add(ln); S.perResult.push(ln); S.ellipses.push({ t: tk, line: ln });
      }
      // spiral path in the rotating frame (most recent revolutions within a point budget)
      var rp = spiralRotPath(res, 60000);
      if (rp.t.length > 2) S.tracks.push(trackOf(S.rotOnly, rp.t, rp.flat, PH.spiral.color, { width: 1.6 }));
    }
    // cislunar segments in both frames
    g.segs.forEach(function (sg) {
      var fe = new Float32Array(sg.t.length * 3), fr = new Float32Array(sg.t.length * 3);
      for (var i = 0; i < sg.t.length; i++) {
        var X = sg.X[i], u = [(X[0] + K.MU) * K.L, X[1] * K.L, X[2] * K.L], Fi = E.frameAt(res.jd0 + sg.t[i]);
        fr[i * 3] = u[0] / 1000; fr[i * 3 + 1] = u[1] / 1000; fr[i * 3 + 2] = u[2] / 1000;
        fe[i * 3] = (Fi.xh[0] * u[0] + Fi.yh[0] * u[1] + Fi.zh[0] * u[2]) / 1000;
        fe[i * 3 + 1] = (Fi.xh[1] * u[0] + Fi.yh[1] * u[1] + Fi.zh[1] * u[2]) / 1000;
        fe[i * 3 + 2] = (Fi.xh[2] * u[0] + Fi.yh[2] * u[1] + Fi.zh[2] * u[2]) / 1000;
      }
      var o = { width: sg.key === "ops" ? 1.8 : 2.2, dashed: !!PH[sg.key].dashed };
      S.tracks.push(trackOf(S.eciGroup, sg.t, fe, PH[sg.key].color, o));
      S.tracks.push(trackOf(S.rotOnly, sg.t, fr, PH[sg.key].color, o));
    });

    // destination
    Object.keys(S.catalog).forEach(function (k) { S.catalog[k].visible = k !== res.target.key; });
    if (res.target.kind === "orbit") {
      var flat = [];
      res.target.states.forEach(function (X) { flat.push((X[0] + K.MU) * K.L / 1000, X[1] * K.L / 1000, X[2] * K.L / 1000); });
      var X0 = res.target.states[0]; flat.push((X0[0] + K.MU) * K.L / 1000, X0[1] * K.L / 1000, X0[2] * K.L / 1000);
      var tl = new THREE.Line2((function () { var gg = new THREE.LineGeometry(); gg.setPositions(flat); return gg; })(), lineMat(PH.ops.color, 1.6, 0.8));
      S.rotGroup.add(tl); S.perResult.push(tl);
    } else {
      var L = S.lpts[res.target.key].raw, ring = new THREE.Line2((function () { var gg = new THREE.LineGeometry(), f = []; for (var i = 0; i <= 96; i++) { var a = 2 * Math.PI * i / 96; f.push(L[0] + 14 * Math.cos(a), L[1] + 14 * Math.sin(a), L[2]); } gg.setPositions(f); return gg; })(), lineMat(PH.ops.color, 1.6, 0.85));
      S.rotGroup.add(ring); S.perResult.push(ring);
    }
    S.labels.target.textContent = TNAME[res.target.key] || "";
    S.labels.craft.textContent = R.P.preset !== "custom" ? R.P.preset : "Sailcraft";
    applyFrame();
  }

  function trackOf(parent, times, flat, color, o) { var t = new Track(parent, times, flat, color, o); t.parent = parent; return t; }

  function spiralRotPath(res, maxPts) {
    var p1 = res.p1, n = p1.t.length, tH = p1.t[n - 1], perRev = 64, budget = maxPts / perRev, acc = 0, iStart = 0;
    for (var i = n - 1; i > 0; i--) {
      var I = E.meeInfo(p1.y[i]), P = 2 * Math.PI * Math.sqrt(I.a * I.a * I.a / K.MU_E) / K.DAY;
      acc += (p1.t[i] - p1.t[i - 1]) / P;
      if (acc > budget) { iStart = i; break; }
    }
    var ts = [], flat = [], t = p1.t[iStart], guard = 0;
    while (t <= tH && guard++ < maxPts + 10) {
      var st = E.phase1State(res, t), rot = E.eciToRotPos(st.r, res.jd0 + t);
      ts.push(t); flat.push(rot[0] / 1000, rot[1] / 1000, rot[2] / 1000);
      t += 2 * Math.PI * Math.sqrt(Math.pow(st.info.a, 3) / K.MU_E) / K.DAY / perRev;
    }
    var stH = E.phase1State(res, tH), rH = E.eciToRotPos(stH.r, res.jd0 + tH);
    ts.push(tH); flat.push(rH[0] / 1000, rH[1] / 1000, rH[2] / 1000);
    return { t: ts, flat: flat };
  }

  function applyFrame() {
    if (!S) return;
    var rot = frameMode === "rotating";
    S.rotOnly.visible = rot;
    S.eciGroup.visible = !rot;
    document.querySelectorAll("[data-frame]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-frame") === frameMode)); });
    dirty = true;
  }

  function setAutoZoom(on) { autoZoom = on; $("autozoom").setAttribute("aria-pressed", String(on)); }

  function aimCamera(view) {
    if (!S) return;
    viewMode = view;
    document.querySelectorAll("[data-view]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-view") === view)); });
    var az = -118 * RAD;
    if (R && S.B && frameMode === "inertial") { var mo = E.moonEci(R.jd0 + playT).r; az = Math.atan2(dot(S.B[1], mo), dot(S.B[0], mo)) - 118 * RAD; }
    var el = (view === "top" ? 88 : view === "side" ? 2.5 : 30) * RAD;
    var dirF = [Math.cos(el) * Math.cos(az), Math.cos(el) * Math.sin(az), Math.sin(el)];
    var d = mv(P3, dirF), n = nrm(d), tgt = S.controls.target;
    var dist = S.camera.position.distanceTo(tgt) || camDist;
    if (autoZoom) dist = camDist;
    S.camera.position.set(tgt.x + d[0] / n * dist, tgt.y + d[1] / n * dist, tgt.z + d[2] / n * dist);
    S.camera.lookAt(tgt); S.controls.update();
    dirty = true;
  }

  function initViewbar() {
    document.querySelectorAll("[data-frame]").forEach(function (b) { b.addEventListener("click", function () { frameMode = b.getAttribute("data-frame"); applyFrame(); aimCamera(viewMode); }); });
    document.querySelectorAll("[data-view]").forEach(function (b) { b.addEventListener("click", function () { aimCamera(b.getAttribute("data-view")); }); });
    $("focus").addEventListener("change", function () {
      focusMode = $("focus").value;
      if (focusMode !== "earth") {
        setAutoZoom(false);
        var off = S.camera.position.clone().sub(S.controls.target);
        off.setLength(focusMode === "moon" ? 260 : 150);
        S.camera.position.copy(S.controls.target).add(off);
      }
      dirty = true;
    });
    $("autozoom").addEventListener("click", function () { setAutoZoom(!autoZoom); if (autoZoom) { focusMode = "earth"; $("focus").value = "earth"; } dirty = true; });
  }

  // state of the sailcraft at mission day t, in ECI km plus rotating-frame data
  function craftState(t) {
    var jd = R.jd0 + t, F = E.frameAt(jd), su = E.sunEci(jd).u, s = [-su[0], -su[1], -su[2]], out = { F: F, su: su, jd: jd };
    var mo = E.moonEci(jd); out.rM = mo.r;
    if (R.p1 && t <= G.tHand) {
      var d = E.phase1Display(R, t);
      out.r = d.r; out.n = d.n; out.lit = !!d.lit; out.sepOn = d.sepOn; out.m = d.m; out.phase = "spiral";
      out.C = lerpAt(G.spiral.t, G.spiral.C, t); out.Capprox = true; out.attitude = "Raising apogee";
      out.deployed = d.deployed;
    } else {
      var q = E.rotState(R, t);
      if (!q) return null;
      var X = q.X, u = [(X[0] + K.MU) * K.L, X[1] * K.L, X[2] * K.L];
      out.r = [F.xh[0] * u[0] + F.yh[0] * u[1] + F.zh[0] * u[2], F.xh[1] * u[0] + F.yh[1] * u[1] + F.zh[1] * u[2], F.xh[2] * u[0] + F.yh[2] * u[1] + F.zh[2] * u[2]];
      out.u = u;
      var ph = phaseAt(t); out.phase = ph ? ph.key : "ops";
      if (q.n) {
        var n = q.n; out.n = [F.xh[0] * n[0] + F.yh[0] * n[1] + F.zh[0] * n[2], F.xh[1] * n[0] + F.yh[1] * n[1] + F.zh[1] * n[2], F.xh[2] * n[0] + F.yh[2] * n[1] + F.zh[2] * n[2]];
      } else out.n = s;
      out.attitude = out.phase === "energy" ? "Pumping energy" : out.phase === "approach" ? "Feathered" : out.phase === "trim" ? "Trimming" : "Station-keeping";
      var sg = segAt(t);
      out.C = sg ? lerpAt(sg.t, sg.C, t) : R.target.C; out.Capprox = false;
      out.m = sg && sg.m ? lerpAt(sg.t, sg.m, t) : G.mFinal;
      var p = dot(out.r, su), lit = !(p < 0 && nrm([out.r[0] - su[0] * p, out.r[1] - su[1] * p, out.r[2] - su[2] * p]) < K.R_E);
      var rm = [out.r[0] - mo.r[0], out.r[1] - mo.r[1], out.r[2] - mo.r[2]], pm = dot(rm, su);
      if (pm < 0 && nrm([rm[0] - su[0] * pm, rm[1] - su[1] * pm, rm[2] - su[2] * pm]) < K.R_M) lit = false;
      out.lit = lit; out.sepOn = false;
    }
    out.cone = Math.acos(clamp(Math.abs(dot(out.n, s)), 0, 1)) / RAD;
    out.rE = nrm(out.r); out.rMoon = nrm([out.r[0] - mo.r[0], out.r[1] - mo.r[1], out.r[2] - mo.r[2]]);
    return out;
  }

  var hudEls = null;
  function hudInit() {
    var h = $("hud"); h.innerHTML = "";
    function el(tag, cls, parent) { var e = document.createElement(tag); if (cls) e.className = cls; parent.appendChild(e); return e; }
    hudEls = {};
    hudEls.when = el("div", "when", h);
    var ph = el("div", "ph", h); hudEls.sw = el("i", "", ph); hudEls.ph = el("span", "", ph);
    var kv = el("div", "kv", h);
    [["rE", "From Earth"], ["rM", "From Moon"], ["att", "Sail"], ["cone", "Sun angle"], ["lit", "Light"], ["C", "Jacobi C"], ["m", "Mass"]].forEach(function (a) {
      el("span", "", kv).textContent = a[1]; hudEls[a[0]] = el("b", "", kv);
    });
  }

  function updateHud(st) {
    if (!hudEls) hudInit();
    var p = phaseAt(playT);
    hudEls.when.textContent = "Day " + fmt(playT, 1) + " · " + isoDay(st.jd);
    if (p) { hudEls.sw.style.background = PH[p.key].color; hudEls.ph.textContent = PH[p.key].name + (p.key === "ops" ? " · " + (TNAME[R.target.key] || "") : ""); }
    hudEls.rE.textContent = fmt(st.rE) + " km";
    hudEls.rM.textContent = fmt(st.rMoon) + " km";
    hudEls.att.textContent = st.phase === "spiral" && st.deployed === false ? "Stowed, SEP climb" : st.attitude;
    hudEls.cone.textContent = fmt(st.cone, 1) + "°";
    hudEls.lit.textContent = (st.lit ? "Sunlit" : "Eclipse") + (st.sepOn ? " · SEP on" : "");
    hudEls.C.textContent = isFinite(st.C) ? (st.Capprox ? "≈ " : "") + st.C.toFixed(3) : "–";
    hudEls.m.textContent = fmt(st.m, 2) + " kg";
  }

  function project(v, el, dx, dy) {
    var p = v.clone().project(S.camera);
    if (p.z > 1 || p.z < -1) { el.style.visibility = "hidden"; return; }
    var x = (p.x * 0.5 + 0.5) * vpW + (dx || 0), y = (-p.y * 0.5 + 0.5) * vpH + (dy || 0);
    if (x < -40 || x > vpW + 40 || y < -20 || y > vpH + 20) { el.style.visibility = "hidden"; return; }
    el.style.visibility = "visible";
    el.style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) translate(-50%,-50%)";
  }

  var lastRingT = -1e9;
  function updateScene(dt) {
    if (!S || !R || !G) return;
    var st = craftState(playT);
    if (!st) return;
    var F = st.F, rot = frameMode === "rotating";
    var Mfr = [F.xh, F.yh, F.zh];                         // ECI -> rotating
    var Meci = rot ? mm(P3, Mfr) : S.Meci;               // ECI raw -> three
    var Mrot = rot ? P3 : mm(S.Meci, tr(Mfr));           // rotating raw -> three
    setM(S.eciGroup, S.Meci);
    setM(S.rotGroup, Mrot);
    var gridM = P3; setM(S.grid, gridM);

    // tracks and spiral visuals
    S.tracks.forEach(function (tk) { tk.setTime(playT); });
    var inSpiral = R.p1 && playT <= G.tHand;
    (S.ellipses || []).forEach(function (e) { e.line.visible = e.t <= playT + 1e-9; });
    S.oscLine.line.visible = !rot && inSpiral;
    S.trail.line.visible = !rot && inSpiral;
    if (!rot && inSpiral) {
      var ell = E.phase1Ellipse(R, playT, 180), f1 = new Float32Array(181 * 3);
      for (var i = 0; i < 181; i++) { f1[i * 3] = ell[i][0] / 1000; f1[i * 3 + 1] = ell[i][1] / 1000; f1[i * 3 + 2] = ell[i][2] / 1000; }
      S.oscLine.set(f1);
      var a = E.meeInfo(E.phase1State(R, playT).y).a, Pd = 2 * Math.PI * Math.sqrt(a * a * a / K.MU_E) / K.DAY, f2 = new Float32Array(121 * 3);
      for (var j = 0; j < 121; j++) {
        var tt = Math.max(0, playT - 1.25 * Pd * (1 - j / 120)), r = E.phase1State(R, tt).r;
        f2[j * 3] = r[0] / 1000; f2[j * 3 + 1] = r[1] / 1000; f2[j * 3 + 2] = r[2] / 1000;
      }
      S.trail.set(f2);
    }

    // bodies
    var camDistNow = S.camera.position.distanceTo(S.controls.target);
    var bs = keepScale ? 1 : clamp(camDistNow / 300, 1, 4);
    S.earth.scale.setScalar(bs); S.moon.scale.setScalar(bs);
    setM(S.earthAxes, Meci, bs);
    var mp = rot ? mv(P3, [K.D_EM / 1000, 0, 0]) : mv(S.Meci, [st.rM[0] / 1000, st.rM[1] / 1000, st.rM[2] / 1000]);
    S.moon.position.set(mp[0], mp[1], mp[2]);
    if (!rot && Math.abs(playT - lastRingT) > 1.5) {
      lastRingT = playT;
      var pa = S.moonRing.geometry.attributes.position, nR = pa.count;
      for (var q = 0; q < nR; q++) { var m = E.moonEci(st.jd + 27.32 * (q / (nR - 1) - 0.5)).r; pa.setXYZ(q, m[0] / 1000, m[1] / 1000, m[2] / 1000); }
      pa.needsUpdate = true;
    }
    var sd = mv(Meci, st.su), sdv = v3(sd).normalize();
    S.sunLight.position.copy(sdv).multiplyScalar(2000); S.sunLight.target.position.set(0, 0, 0);
    var arrowLen = clamp(camDistNow * 0.22, 25, 260);
    S.sunArrow.setDirection(sdv); S.sunArrow.setLength(arrowLen, arrowLen * 0.09, arrowLen * 0.045);
    S.lpts.L1.mesh.scale.setScalar(clamp(camDistNow / 900, 0.15, 2.5));
    ["L2", "L3", "L4", "L5"].forEach(function (k) { S.lpts[k].mesh.scale.copy(S.lpts.L1.mesh.scale); });

    // sailcraft
    var cp = mv(Meci, [st.r[0] / 1000, st.r[1] / 1000, st.r[2] / 1000]), nv = v3(mv(Meci, st.n)).normalize();
    S.craft.position.set(cp[0], cp[1], cp[2]);
    S.pivot.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), nv);
    var cs = S.camera.position.distanceTo(S.craft.position) * 0.032;
    S.craft.scale.setScalar(cs);

    // camera focus and zoom
    var focus = focusMode === "moon" ? S.moon.position.clone() : focusMode === "craft" ? S.craft.position.clone() : new THREE.Vector3(0, 0, 0);
    var off = S.camera.position.clone().sub(S.controls.target);
    if (autoZoom && focusMode === "earth") {
      var want = inSpiral ? clamp(3.4 * E.meeInfo(E.phase1State(R, playT).y).ra / 1000, 50, 1150) : 1150;
      var len = off.length(), k2 = 1 - Math.exp(-(dt || 0.016) * 3.5);
      off.setLength(len + (want - len) * k2);
      if (Math.abs(want - len) > 0.5) dirty = true;
    }
    S.controls.target.copy(focus); S.camera.position.copy(focus).add(off);
    S.camera.lookAt(focus); S.camera.updateMatrixWorld();

    // labels
    var L = S.labels, er = K.R_E / 1000 * bs, mr = K.R_M / 1000 * bs;
    project(new THREE.Vector3(0, -er, 0), L.earth, 0, 14);
    project(S.moon.position.clone().add(new THREE.Vector3(0, -mr, 0)), L.moon, 0, 13);
    project(sdv.clone().multiplyScalar(arrowLen * 1.08), L.sun, 0, 0);
    project(S.craft.position.clone(), L.craft, 0, -18);
    ["L1", "L2", "L3", "L4", "L5"].forEach(function (k) { var w = S.lpts[k].mesh.getWorldPosition(new THREE.Vector3()); project(w, L[k], 14, -8); });
    if (R.target.kind === "orbit") {
      var ts = R.target.states, far = ts[Math.floor(ts.length / 4)];
      var wp = v3(mv(Mrot, [(far[0] + K.MU) * K.L / 1000, far[1] * K.L / 1000, far[2] * K.L / 1000]));
      project(wp, L.target, 0, -12);
    } else { var w5 = S.lpts[R.target.key].mesh.getWorldPosition(new THREE.Vector3()); project(w5, L.target, 0, 16); }
    L[R.target.key] && R.target.kind === "point" && (L[R.target.key].style.visibility = "hidden");

    $("scalenote").textContent = (bs > 1.05 ? "Earth and Moon drawn ×" + bs.toFixed(1) + " for visibility · " : "Earth and Moon to scale · ") +
      "rings every 100,000 km · " + (rot ? "x-axis points at the Moon" : "lunar orbit plane horizontal");
    updateHud(st);
  }

  // ------------------------------------------------------------------ main loop
  var lastNow = 0;
  function loop(now) {
    requestAnimationFrame(loop);
    var dt = lastNow ? Math.min((now - lastNow) / 1000, 0.1) : 0.016; lastNow = now;
    if (playing && R) {
      var t = playT + dt * paceAt(playT);
      if (t >= R.tEnd) { t = R.tEnd; setPlaying(false); }
      setTime(t);
    }
    if (!S) return;
    var moved = S.controls.update();
    if (moved) dirty = true;
    if (!dirty) return;
    dirty = false;
    updateScene(dt);
    S.renderer.render(S.scene, S.camera);
  }

  // ------------------------------------------------------------------ boot
  function boot() {
    initForm(); initTimeline();
    chartDist = new Chart($("chartDist")); chartC = new Chart($("chartC")); chartScan = $("chartScan");
    drawScan();
    $("scanBtn").addEventListener("click", startScan);
    if (HAS3D) initScene();
    else noThree("The 3-D view needs three.js from cdn.jsdelivr.net, which did not load. The numbers, timeline and charts still update.");
    var rw = 0, rt = 0;
    new ResizeObserver(function () {
      var w = $("chartDist").clientWidth; if (Math.abs(w - rw) < 2) return; rw = w;
      clearTimeout(rt); rt = setTimeout(function () { if (R) renderCharts(); drawScan(); }, 120);
    }).observe($("chartDist"));
    requestAnimationFrame(loop);
    runNow();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
