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
  var TSHORT = { L1H: "EML1", L2H: "EML2", NRHO: "NRHO", DRO: "DRO", L4: "EML4", L5: "EML5" };
  function orbitKind(v) { return v && v.indexOf("CIS:") === 0 ? "CIS" : v; }
  function stopsOf(P) {
    var st = [{ key: P.target, dwell: P.dwell1 }];
    if (P.stop2 && P.stop2 !== "none") {
      st.push({ key: P.stop2, dwell: P.dwell2 });
      if (P.stop3 && P.stop3 !== "none") st.push({ key: P.stop3, dwell: 0 });
    }
    return st;
  }
  var FILM_ORDER = ["AL_CP1", "AL_PEN_CR", "AL_MYLAR", "AL_AL_CP1", "CP1_THIN", "IDEAL"];
  var PRESET_ORDER = ["CR-S", "CR-H", "CR-HR", "CR-A", "SC", "NEAS", "ACS3", "LS2"];
  var ORBIT_INC = { GTO: 27, LEO: 28.5, GEO: 0 };

  // ------------------------------------------------------------------ form
  var FIELDS = ["launch", "orbit", "alt", "perigee", "apogee", "inc", "raanMode", "raan", "tliPerigee", "tliApogee", "tliLead", "target",
    "dwell1", "stop2", "dwell2", "stop3",
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
    var kind = orbitKind(P.orbit), earth = kind !== "TLI" && kind !== "CIS";
    if (earth && !(P.inc >= 0 && P.inc <= 180)) return "Inclination must be between 0 and 180°.";
    if (earth && P.raanMode === "manual" && !(P.raan >= 0 && P.raan <= 360)) return "RAAN must be between 0 and 360°.";
    var st = stopsOf(P), prev = kind === "CIS" ? P.orbit.slice(4) : null;
    for (var i = 0; i < st.length; i++) {
      if (st[i].key === prev) return i === 0 ? "The first stop is the orbit the sailcraft starts on. Pick a different first stop." : "Stop " + (i + 1) + " is the same station as stop " + i + ". Pick a different one.";
      prev = st[i].key;
    }
    if (st.length > 1 && !(P.dwell1 >= 0 && P.dwell1 <= 365)) return "The stay at the first stop must be 0–365 days.";
    if (st.length > 2 && !(P.dwell2 >= 0 && P.dwell2 <= 365)) return "The stay at the second stop must be 0–365 days.";
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
    var kind = orbitKind(P.orbit);
    prm.orbit = kind;
    if (kind === "CIS") prm.origin = P.orbit.slice(4);
    if (kind === "LEO") prm.alt = P.alt;
    if (kind === "GTO") { prm.perigee = P.perigee; prm.apogee = P.apogee; }
    if (kind === "TLI") { prm.perigee = P.tliPerigee; prm.apogee = P.tliApogee; prm.tliLead = P.tliLead; }
    prm.stops = stopsOf(P);
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
    var kind = orbitKind($("orbit").value), earth = kind !== "TLI" && kind !== "CIS";
    document.querySelectorAll("[data-for]").forEach(function (el) { el.hidden = el.getAttribute("data-for") !== kind; });
    document.querySelectorAll("[data-earthorbit]").forEach(function (el) { el.hidden = !earth; });
    $("raanBox").hidden = !earth || $("raanMode").value !== "manual";
    $("launchLbl").textContent = kind === "CIS" ? "Start date" : "Launch date";
    var s2 = $("stop2").value !== "none", s3 = s2 && $("stop3").value !== "none";
    document.querySelectorAll("[data-leg2]").forEach(function (el) { el.hidden = !s2; });
    document.querySelectorAll("[data-leg3]").forEach(function (el) { el.hidden = !s3; });
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
    renderTiles(); renderTimeline(); renderPhaseTable(); renderLegTable(); renderCharts(); drawMatrix();
    var b = $("banner"); b.hidden = ok; b.innerHTML = ""; if (!ok) { var s = document.createElement("b"); s.textContent = statusShort(res) + ". "; b.appendChild(s); b.appendChild(document.createTextNode(statusText(res))); }
    if (HAS3D) buildScene(res);
    var lastLeg = res.legs && res.legs.length ? res.legs[res.legs.length - 1] : null;
    var tStart = ok && lastLeg ? Math.min(res.tEnd, lastLeg.tIns + 0.3 * (res.tEnd - lastLeg.tIns)) : res.tEnd;
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
    (res.stays || []).forEach(function (st) {
      var n = Math.max(160, Math.ceil(st.days * 30)), ts = [], Xs = [];
      for (var j = 0; j <= n; j++) { var tau = st.days * j / n; ts.push(st.t0 + tau); Xs.push(E.orbitState(st.tgt, st.i0, tau * K.DAY / K.T)); }
      g.segs.push({ key: "ops", t: ts, X: Xs, m: null, est: false, stay: st, leg: st.leg });
    });
    (res.legs || []).forEach(function (L, k) {
      [["energy", L.p2], ["approach", L.p3], ["trim", L.p4]].forEach(function (q) {
        var seg = q[1];
        if (!seg || seg.t.length < 2) return;
        g.segs.push({ key: q[0], t: seg.t.slice(), X: seg.X.slice(), m: seg.m ? seg.m.slice() : null, est: !!L.reversed, leg: k });
      });
    });
    g.segs.sort(function (a, b) { return a.t[0] - b.t[0]; });
    for (var s = 1; s < g.segs.length; s++) {           // stitch segments so the drawn path is continuous
      var a = g.segs[s - 1], b = g.segs[s];
      if (b.t[0] > a.t[a.t.length - 1] + 1e-9) { b.t.unshift(a.t[a.t.length - 1]); b.X.unshift(a.X[a.X.length - 1]); if (b.m) b.m.unshift(a.m ? a.m[a.m.length - 1] : b.m[0]); }
    }
    g.segs.forEach(function (sg) {
      sg.rE = sg.X.map(function (X) { return Math.hypot(X[0] + K.MU, X[1], X[2]) * K.L; });
      sg.rM = sg.X.map(function (X) { return Math.hypot(X[0] - 1 + K.MU, X[1], X[2]) * K.L; });
      if (sg.key === "trim") { var c0 = E.jacobi(sg.X[0]), c1 = E.jacobi(sg.X[sg.X.length - 1]); sg.C = sg.t.map(function (tt, k) { return c0 + (c1 - c0) * k / (sg.t.length - 1); }); }
      else sg.C = sg.X.map(function (X) { return E.jacobi(X); });
    });
    g.mFinal = res.mFinal != null ? res.mFinal : (res.p1 ? res.p1.y[res.p1.y.length - 1][5] : res.sc.m0);
    return g;
  }

  function stationName(key) { return TNAME[key] || key; }
  /** Human description of the phase entry p (with its leg). */
  function phaseText(p) {
    if (!p) return "";
    if (p.key === "spiral") return "Earth spiral";
    var L = R.legs && R.legs[p.leg];
    if (p.stay) {
      var st = (R.stays || []).filter(function (x) { return Math.abs(x.t0 - p.t0) < 1e-9; })[0];
      return st ? (st.kind === "final" ? "On station at " : "At ") + stationName(st.tgt.key) : p.label;
    }
    if (!L) return PH[p.key].name;
    var from = L.from ? TSHORT[L.from] : (R.prm.orbit === "TLI" ? "TLI" : "Earth");
    return "Leg " + (p.leg + 1) + " · " + from + " → " + TSHORT[L.target.key] + " · " + PH[p.key].name.replace(" (modelled)", "") + (p.est ? " (estimated)" : (p.key === "trim" ? " (modelled)" : ""));
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
    var res = R, s = res.summary, ok = res.status === "ok", c = res.craft, host = $("tiles"), legs = s.legs || [];
    host.innerHTML = "";
    var multi = legs.length > 1, okLegs = legs.filter(function (l) { return l.status === "ok"; });
    host.appendChild(tile(multi ? "Days to final stop" : "Days to station", ok ? fmt(s.toTargetDays) : "–", ok ? "d" : "",
      ok ? "At " + stationName(res.target.key) + " on " + prettyDate(res.jd0 + s.toTargetDays) : statusShort(res) + (res.failedLeg != null ? " on leg " + (res.failedLeg + 1) : ""), true, !ok));
    if (res.origin) host.appendChild(tile("Start", TSHORT[res.origin.key], "", "On " + prettyDate(res.jd0) + " · no Earth spiral"));
    else host.appendChild(tile("Earth spiral", res.p1 ? fmt(s.spiralDays) : "0", "d",
      res.p1 ? fmt(s.spiralDays / 365.25, 2) + " years to C ≈ 3.29" : "Not needed after TLI"));
    host.appendChild(tile("Cislunar transit", okLegs.length ? fmt(s.cislunarDays) : "–", okLegs.length ? "d" : "",
      legs.length + (legs.length === 1 ? " leg" : " legs") + (multi ? ": " + legs.map(function (l) { return l.status === "ok" ? fmt(l.transfer + l.wait) : "×"; }).join(" + ") + " d" : (okLegs.length ? ", energy " + fmt(s.energyDays) + " · phasing " + fmt(s.approachDays) + " · capture " + fmt(s.trimDays) : ""))));
    host.appendChild(tile("Characteristic accel.", fmt(c.acMM, 3), "mm/s²", c.sepMM > 0 ? "SEP adds " + fmt(c.sepMM, 3) + " mm/s²" : "Sail only, at 1 AU"));
    host.appendChild(tile("Sail loading", fmt(c.loading, 1), "g/m²", fmt(Math.sqrt(res.sc.area), 1) + " m square sail"));
    host.appendChild(tile("Propellant used", s.propLoaded > 0 ? fmt(s.propUsed, 2) : "–", s.propLoaded > 0 ? "kg" : "",
      s.propLoaded > 0 ? "of " + fmt(s.propLoaded, 1) + " kg loaded" : "No SEP on board"));
    if (res.handover) host.appendChild(tile("Plane offset at hand-over", fmt(res.handover.incMoon, 1), "°",
      "From lunar plane · RAAN " + fmt(res.raan, 1) + "°" + (res.prm.raanMode === "auto" ? " (aligned)" : "")));
    else host.appendChild(tile("Stations", String(legs.length + (res.origin ? 1 : 0)), "",
      (res.origin ? TSHORT[res.origin.key] + " → " : "TLI → ") + legs.map(function (l) { return TSHORT[l.to]; }).join(" → ")));
    host.appendChild(tile("Solar activity", fmt(res.f107), "sfu", "Lunar plane " + fmt(res.moonIncl, 1) + "° to equator at start"));
  }

  function renderPhaseTable() {
    var tb = $("phaseTable").querySelector("tbody"); tb.innerHTML = "";
    R.phases.forEach(function (p) {
      var tr_ = document.createElement("tr");
      var c1 = document.createElement("td"), sw = document.createElement("i"); sw.className = "sw"; sw.style.background = PH[p.key].color;
      if (p.key === "trim" || p.est) sw.style.background = "repeating-linear-gradient(90deg," + PH[p.key].color + " 0 3px, transparent 3px 5px)";
      c1.appendChild(sw); c1.appendChild(document.createTextNode(phaseText(p)));
      var c2 = document.createElement("td"); c2.textContent = prettyDate(R.jd0 + p.t0);
      var c3 = document.createElement("td"); c3.className = "n"; c3.textContent = fmt(p.t0, 1);
      var c4 = document.createElement("td"); c4.className = "n"; c4.textContent = fmt(p.t1 - p.t0, 1);
      tr_.appendChild(c1); tr_.appendChild(c2); tr_.appendChild(c3); tr_.appendChild(c4); tb.appendChild(tr_);
    });
  }

  function renderLegTable() {
    var tb = $("legTable").querySelector("tbody"); tb.innerHTML = "";
    var legs = R.summary.legs || [];
    function td(txt, num) { var c = document.createElement("td"); if (num) c.className = "n"; c.textContent = txt; return c; }
    if (!legs.length) {
      var tr0 = document.createElement("tr"), c0 = td("No cislunar legs were flown: " + statusShort(R).toLowerCase() + " during the Earth spiral.");
      c0.colSpan = 10; tr0.appendChild(c0); tb.appendChild(tr0); return;
    }
    legs.forEach(function (l, i) {
      var ok = l.status === "ok", tr_ = document.createElement("tr");
      var from = l.from ? stationName(l.from) : (R.prm.orbit === "TLI" ? "TLI" : "Earth (after the spiral)");
      var stay = (R.stays || []).filter(function (s) { return s.leg === i; })[0];
      tr_.appendChild(td(String(i + 1)));
      tr_.appendChild(td(from + " → " + stationName(l.to)));
      tr_.appendChild(td("Day " + fmt(l.depart, 1) + " · " + isoDay(R.jd0 + l.depart)));
      tr_.appendChild(td(ok ? "Day " + fmt(l.arrive, 1) + " · " + isoDay(R.jd0 + l.arrive) : statusShort({ status: l.status })));
      tr_.appendChild(td(ok ? fmt(l.transfer, 1) : "–", true));
      tr_.appendChild(td(fmt(l.energy, 1), true));
      tr_.appendChild(td(ok ? fmt(l.phasing, 1) : "–", true));
      tr_.appendChild(td(ok ? fmt(l.capture, 1) : "–", true));
      tr_.appendChild(td(stay ? (stay.kind === "final" ? "on station" : fmt(stay.days, 1)) : "–", true));
      tr_.appendChild(td(!ok ? "Not completed" : l.reversed ? "Estimated, reverse leg" : "Flown" + (l.wait > 0 ? ", left " + fmt(l.wait) + " d later" : "")));
      tb.appendChild(tr_);
    });
  }

  // ------------------------------------------------------------------ timeline and playback
  var playT = 0, playing = false, dirty = true;

  var zoom = "all";
  function tWin() {
    if (zoom === "cis" && G && R && R.legs && R.legs.length) return [Math.max(0, R.legs[0].tDep - 2), R.tEnd];
    return [0, R ? R.tEnd : 1];
  }
  var chipItems = [];

  function renderTimeline() {
    var bar = $("tlbar"), W = tWin(), T0 = W[0], T1 = W[1], span = Math.max(T1 - T0, 1e-6);
    bar.innerHTML = ""; bar.style.display = "block";
    R.phases.forEach(function (p) {
      var a = Math.max(p.t0, T0), b = Math.min(p.t1, T1);
      if (b <= a) return;
      var i = document.createElement("i"), col = PH[p.key].color;
      i.style.position = "absolute"; i.style.top = "0"; i.style.bottom = "0";
      i.style.left = ((a - T0) / span * 100) + "%";
      i.style.width = "max(3px, calc(" + ((b - a) / span * 100) + "% - 2px))";
      i.style.background = (p.key === "trim" || p.est) ? "repeating-linear-gradient(90deg," + col + " 0 5px, transparent 5px 8px)" : col;
      bar.appendChild(i);
    });
    var sc = $("scrub"); sc.min = String(T0); sc.max = String(T1); sc.value = String(clamp(playT, T0, T1));
    // phase key
    var lg = $("legend"); lg.innerHTML = "";
    var present = {}, dashed = false;
    R.phases.forEach(function (p) { present[p.key] = true; if (p.key === "trim" || p.est) dashed = true; });
    PH_ORDER.forEach(function (k) {
      if (!present[k]) return;
      var it = document.createElement("span"); it.className = "it";
      var sw = document.createElement("i"); sw.style.background = PH[k].color;
      it.appendChild(sw); it.appendChild(document.createTextNode(PH[k].name.replace(" (modelled)", "")));
      lg.appendChild(it);
    });
    if (dashed) { var it2 = document.createElement("span"); it2.className = "it"; var sw2 = document.createElement("i"); sw2.className = "dash"; it2.appendChild(sw2); it2.appendChild(document.createTextNode("Dashed: modelled or estimated")); lg.appendChild(it2); }
    // leg chips: spiral, each leg, each stay
    var host = $("legchips"); host.innerHTML = ""; chipItems = [];
    function chip(color, text, days, t0, t1) {
      var b = document.createElement("button"); b.type = "button";
      var dot = document.createElement("i"); dot.style.background = color;
      var nm = document.createElement("span"); nm.textContent = text;
      var du = document.createElement("b"); du.textContent = fmt(days, days < 10 ? 1 : 0) + " d";
      b.appendChild(dot); b.appendChild(nm); b.appendChild(du);
      b.setAttribute("aria-label", "Jump to " + text + ", " + fmt(days, 1) + " days");
      b.addEventListener("click", function () { setPlaying(false); if (t0 < tWin()[0] || t0 > tWin()[1]) setZoom("all"); setTime(t0 + 1e-3); });
      host.appendChild(b); chipItems.push({ el: b, t0: t0, t1: t1 });
    }
    if (R.p1) chip(PH.spiral.color, "Earth spiral", G.tHand, 0, G.tHand);
    var items = [];
    (R.legs || []).forEach(function (L, k) {
      var from = L.from ? TSHORT[L.from] : (R.prm.orbit === "TLI" ? "TLI" : "Earth");
      var t1 = L.status === "ok" ? L.tIns : L.tEnd;
      items.push({ t0: L.tDep, t1: t1, color: PH.energy.color, text: "Leg " + (k + 1) + " · " + from + " → " + TSHORT[L.target.key] + (L.reversed ? " (est.)" : (L.status !== "ok" ? " (failed)" : "")) });
    });
    (R.stays || []).forEach(function (st) { items.push({ t0: st.t0, t1: st.t0 + st.days, color: PH.ops.color, text: (st.kind === "final" ? "On station · " : "At ") + TSHORT[st.tgt.key] }); });
    items.sort(function (a, b) { return a.t0 - b.t0; });
    items.forEach(function (it) { chip(it.color, it.text, it.t1 - it.t0, it.t0, it.t1); });
    markChips();
  }
  function markChips() { chipItems.forEach(function (c) { c.el.classList.toggle("now", playT >= c.t0 - 1e-6 && playT <= c.t1 + 1e-6); }); }
  function setZoom(z) {
    zoom = z;
    document.querySelectorAll("[data-zoom]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-zoom") === z)); });
    if (R) { renderTimeline(); renderCharts(); setTime(clamp(playT, tWin()[0], tWin()[1])); }
    if (S && R) {                       // cislunar legs read best in the Earth-Moon rotating frame, centred on the Moon
      if (z === "cis") {
        var keys = (R.origin ? [R.origin.key] : []).concat((R.summary.legs || []).map(function (l) { return l.to; }));
        var far = keys.some(function (k) { return k === "L4" || k === "L5"; });
        frameMode = "rotating"; applyFrame(); setAutoZoom(false);
        focusMode = far ? "earth" : "moon"; $("focus").value = focusMode;
        aimCamera(viewMode, far ? 1150 : 430);
      } else {
        frameMode = "inertial"; applyFrame(); focusMode = "earth"; $("focus").value = "earth"; setAutoZoom(true);
        camDist = 1150; aimCamera(viewMode);
      }
    }
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
    markChips();
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
      if (!playing && playT >= R.tEnd - 1e-6) setTime(tWin()[0]);
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
    var m = { l: 50, r: 18, t: cfg.yUnit ? 22 : 14, b: 26 }, pw = W - m.l - m.r, ph = H - m.t - m.b;
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
    if (cfg.yUnit) { var u = svg("text", { x: m.l - 7, y: m.t - 11, "text-anchor": "end", fill: "#7a869e", "font-size": 10.5, "font-family": "IBM Plex Sans, sans-serif" }, root); u.textContent = cfg.yUnit; }
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
    var placed = [];
    (cfg.refs || []).slice().sort(function (p, q) { return q.y - p.y; }).forEach(function (r) {
      if (r.y < Math.min(cfg.y0, cfg.y1) || r.y > Math.max(cfg.y0, cfg.y1)) return;
      var y = Y(r.y), ly = y - 5, right = false;
      placed.forEach(function (q) { if (!q.right && Math.abs(q.ly - ly) < 13) right = true; });
      if (right) placed.forEach(function (q) { if (q.right && Math.abs(q.ly - ly) < 13) ly = y + 13; });
      placed.push({ ly: ly, right: right });
      svg("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "#5a6884", "stroke-width": 1 }, root);
      var tx = svg("text", { x: right ? W - m.r - 4 : m.l + 6, y: ly, "text-anchor": right ? "end" : "start", fill: "#a5b0c6", "font-size": 11, "font-family": "IBM Plex Sans, sans-serif" }, root);
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

  function thin(n) { return Math.max(1, Math.floor(n / 1400)); }

  function renderCharts() {
    if (!R) return;
    var g = G, res = R, W = tWin(), series = [], bands = [], lo = Infinity, hi = 0;
    function grow(v) { if (isFinite(v) && v > 0) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
    if (g.spiral && W[0] < g.tHand) {
      var t = [], ra = [], rp = [];
      for (var i = 0; i < g.spiral.t.length; i++) if (g.spiral.t[i] >= W[0] - 1) { t.push(g.spiral.t[i]); ra.push(g.spiral.ra[i]); rp.push(g.spiral.rp[i]); grow(g.spiral.ra[i]); grow(g.spiral.rp[i]); }
      if (t.length > 1) {
        bands.push({ t: t, lo: rp, hi: ra, color: PH.spiral.color });
        series.push({ t: t, v: ra, color: PH.spiral.color });
        series.push({ t: t, v: rp, color: PH.spiral.color, width: 1.5 });
      }
    }
    g.segs.forEach(function (sg) {
      if (sg.t[sg.t.length - 1] < W[0]) return;
      var st = thin(sg.t.length), t = [], vE = [], vM = [];
      for (var i = 0; i < sg.t.length; i += st) { t.push(sg.t[i]); vE.push(sg.rE[i]); vM.push(sg.rM[i]); grow(sg.rE[i]); grow(sg.rM[i]); }
      var n = sg.t.length - 1; t.push(sg.t[n]); vE.push(sg.rE[n]); vM.push(sg.rM[n]);
      series.push({ t: t, v: vM, color: "#a5b0c6", width: 1.5, dashed: sg.key === "trim" || sg.est });
      series.push({ t: t, v: vE, color: PH[sg.key].color, dashed: sg.key === "trim" || sg.est });
    });
    if (!isFinite(lo)) lo = K.R_E; if (!(hi > 0)) hi = 4e5;
    var y0 = Math.max(1000, lo * 0.8), y1 = Math.max(6e5, hi * 1.3);
    chartDist.draw({
      x0: W[0], x1: W[1], ylog: true, y0: y0, y1: y1, yTicks: logTicks(y0, y1), yFmt: kmTick, yUnit: "km",
      bands: bands, series: series, refs: [{ y: K.D_EM, label: "Moon's distance" }],
      tooltip: function (t) {
        var p = phaseAt(t), rows = [];
        if (g.spiral && t <= g.tHand) {
          rows.push({ color: PH.spiral.color, value: fmt(lerpAt(g.spiral.t, g.spiral.ra, t)) + " km", label: "apogee" });
          rows.push({ color: PH.spiral.color, value: fmt(lerpAt(g.spiral.t, g.spiral.rp, t)) + " km", label: "perigee" });
        } else {
          var sg = segAt(t);
          if (sg) {
            rows.push({ color: PH[sg.key].color, dashed: sg.key === "trim" || sg.est, value: fmt(lerpAt(sg.t, sg.rE, t)) + " km", label: "from Earth" });
            rows.push({ color: "#a5b0c6", value: fmt(lerpAt(sg.t, sg.rM, t)) + " km", label: "from the Moon" });
          }
        }
        if (p) rows.push({ color: PH[p.key].color, dashed: p.key === "trim" || p.est, value: phaseText(p), label: "" });
        return rows;
      },
    });

    var tc = res.legs && res.legs.length ? res.legs[0].tDep : g.tHand;
    var x0 = Math.max(0, res.p1 ? tc - Math.max(20, 0.25 * (res.tEnd - tc)) : tc), cs = [], cmin = Infinity, cmax = -Infinity, clipped = false;
    if (g.spiral) {
      var ts = [], vs = [];
      for (var k = 0; k < g.spiral.t.length; k++) if (g.spiral.t[k] >= x0 && isFinite(g.spiral.C[k])) { ts.push(g.spiral.t[k]); vs.push(g.spiral.C[k]); cmax = Math.max(cmax, g.spiral.C[k]); }
      if (ts.length) cs.push({ t: ts, v: vs, color: PH.spiral.color });
    }
    g.segs.forEach(function (sg) {
      var st = thin(sg.t.length), t = [], v = [];
      for (var i = 0; i < sg.t.length; i += st) { t.push(sg.t[i]); v.push(sg.C[i]); if (isFinite(sg.C[i])) { cmin = Math.min(cmin, sg.C[i]); cmax = Math.max(cmax, sg.C[i]); } }
      t.push(sg.t[sg.t.length - 1]); v.push(sg.C[sg.C.length - 1]);
      cs.push({ t: t, v: v, color: PH[sg.key].color, dashed: sg.key === "trim" || sg.est });
    });
    var refs = [{ y: DATA.C_lagrange.L1, label: "L1 gateway 3.188" }], seen = {};
    var stations = (res.origin ? [res.origin.key] : []).concat((res.summary.legs || []).map(function (l) { return l.to; }));
    stations.forEach(function (key) {
      if (seen[key]) return; seen[key] = 1;
      var C = E.targetInfo(key).C; cmin = Math.min(cmin, C); cmax = Math.max(cmax, C);
      refs.push({ y: C, label: TSHORT[key] + " " + C.toFixed(3) });
    });
    if (!isFinite(cmax)) cmax = DATA.C_lagrange.L1 + 0.1;
    var cy1 = Math.min(3.45, Math.max(cmax, DATA.C_lagrange.L1 + 0.05) + 0.02), cy0 = cmin - 0.03;
    if (cmax > cy1) clipped = true;
    chartC.draw({
      x0: x0, x1: res.tEnd, ylog: false, y0: cy0, y1: cy1, yTicks: linTicks(cy0, cy1, 5), yFmt: function (v) { return v.toFixed(2); }, yUnit: "C",
      series: cs, refs: refs, notes: clipped && g.spiral ? ["Spiral values above " + cy1.toFixed(2) + " are off the top"] : [],
      tooltip: function (t) {
        var rows = [], p = phaseAt(t);
        if (g.spiral && t <= g.tHand) rows.push({ color: PH.spiral.color, value: lerpAt(g.spiral.t, g.spiral.C, t).toFixed(3), label: "approx., Moon ignored" });
        else { var sg = segAt(t); if (sg) rows.push({ color: PH[sg.key].color, dashed: sg.key === "trim" || sg.est, value: lerpAt(sg.t, sg.C, t).toFixed(3), label: sg.est ? "estimated" : sg.key === "trim" ? "modelled" : "Jacobi C" }); }
        if (p && p.leg != null && R.legs[p.leg]) rows.push({ color: "#5a6884", value: R.legs[p.leg].target.C.toFixed(3), label: TSHORT[R.legs[p.leg].target.key] + " value" });
        if (p) rows.push({ color: PH[p.key].color, dashed: p.key === "trim" || p.est, value: phaseText(p), label: "" });
        return rows;
      },
    });
  }

  // ------------------------------------------------------------------ cislunar transfer matrix
  var matrix = { busy: false, token: 0, cells: {}, kind: "sail" };
  function rampColor(f) {
    var a = [0x17, 0x31, 0x56], b = [0x6d, 0xa7, 0xec], c = a.map(function (v, i) { return Math.round(v + (b[i] - v) * clamp(f, 0, 1)); });
    return { css: "rgb(" + c.join(",") + ")", dark: (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) < 120 };
  }
  function drawMatrix() {
    var host = $("matrixWrap"); host.innerHTML = "";
    var ST = E.STATIONS, cells = matrix.cells, vals = [];
    Object.keys(cells).forEach(function (k) { if (cells[k].days != null) vals.push(cells[k].days); });
    var vmin = vals.length ? Math.min.apply(null, vals) : 0, vmax = vals.length ? Math.max.apply(null, vals) : 1;
    var study = DATA.study_transfers[matrix.kind] || {};
    var tbl = document.createElement("table"); tbl.className = "matrix";
    var thead = document.createElement("thead"), hr = document.createElement("tr"), h0 = document.createElement("th");
    h0.textContent = "From ↓  To →"; h0.className = "rowh"; hr.appendChild(h0);
    ST.forEach(function (d) { var th = document.createElement("th"); th.textContent = TSHORT[d]; th.scope = "col"; hr.appendChild(th); });
    thead.appendChild(hr); tbl.appendChild(thead);
    var tb = document.createElement("tbody");
    ST.forEach(function (o) {
      var tr_ = document.createElement("tr"), th = document.createElement("th"); th.className = "rowh"; th.scope = "row"; th.textContent = TSHORT[o]; tr_.appendChild(th);
      ST.forEach(function (d) {
        var td = document.createElement("td");
        if (o === d) { td.className = "diag"; td.textContent = "–"; tr_.appendChild(td); return; }
        var c = cells[o + ">" + d], b = document.createElement("button"); b.type = "button";
        var ref = study[o + ">" + d];
        if (c && c.days != null) {
          var col = rampColor(vmax > vmin ? (c.days - vmin) / (vmax - vmin) : 0.5);
          b.style.background = col.css; b.style.color = col.dark ? "#e8ecf4" : "#0b1220";
          b.textContent = (c.est ? "≈" : "") + fmt(c.days);
          var sm = document.createElement("small"); sm.textContent = ref != null ? "study " + fmt(ref) : ""; b.appendChild(sm);
          b.title = TNAME[o] + " → " + TNAME[d] + ": " + fmt(c.days, 1) + " days" + (c.est ? " (estimated from the reverse leg)" : "") +
            " · energy " + fmt(c.energy, 1) + ", phasing " + fmt(c.phasing, 1) + ", capture " + fmt(c.capture, 1) + (ref != null ? " · study median " + fmt(ref, 1) + " d" : "");
        } else if (c) {
          b.style.background = "#2a1416"; b.style.color = "#e66767"; b.textContent = "×";
          var sm2 = document.createElement("small"); sm2.textContent = statusShort({ status: c.status }); b.appendChild(sm2);
          b.title = TNAME[o] + " → " + TNAME[d] + ": " + statusShort({ status: c.status });
        } else {
          b.style.background = "#131b2d"; b.style.color = "#7a869e"; b.textContent = matrix.busy ? "…" : "–";
          if (ref != null) { var sm3 = document.createElement("small"); sm3.textContent = "study " + fmt(ref); b.appendChild(sm3); }
          b.title = "Fly " + TNAME[o] + " → " + TNAME[d];
        }
        b.setAttribute("aria-label", b.title);
        b.addEventListener("click", function () {
          $("orbit").value = "CIS:" + o; $("target").value = d; $("stop2").value = "none";
          syncVisibility(); syncSite(); runNow();
          document.querySelector(".stage").scrollIntoView({ behavior: "smooth", block: "start" });
        });
        td.appendChild(b); tr_.appendChild(td);
      });
      tb.appendChild(tr_);
    });
    tbl.appendChild(tb); host.appendChild(tbl);
    var key = document.createElement("div"); key.className = "mkey";
    var k1 = document.createElement("span"); k1.style.display = "inline-flex"; k1.style.alignItems = "center"; k1.style.gap = "8px";
    var r0 = document.createElement("span"); r0.textContent = vals.length ? fmt(vmin) + " d" : "fewer days";
    var rr = document.createElement("span"); rr.className = "ramp";
    var r1 = document.createElement("span"); r1.textContent = vals.length ? fmt(vmax) + " d" : "more days";
    k1.appendChild(r0); k1.appendChild(rr); k1.appendChild(r1); key.appendChild(k1);
    var k2 = document.createElement("span"); k2.textContent = "≈ estimated from the reverse leg · small figure: study median for " + (matrix.kind === "hybrid" ? "CR-H (hybrid)" : "CR-S (sail)");
    key.appendChild(k2); host.appendChild(key);
  }

  function startMatrix() {
    if (matrix.busy) { matrix.busy = false; matrix.token++; $("matrixBtn").textContent = "Fly all 30 transfers"; $("matrixMsg").textContent = "Stopped."; drawMatrix(); return; }
    var P0 = readParams(), err = validate(Object.assign({}, P0, { orbit: "CIS:L1H", target: "L2H", stop2: "none" }));
    if (err) { $("matrixMsg").textContent = err; return; }
    var ST = E.STATIONS, pairs = [];
    ST.forEach(function (o) { ST.forEach(function (d) { if (o !== d) pairs.push([o, d]); }); });
    matrix = { busy: true, token: matrix.token + 1, cells: {}, kind: P0.sepOn ? "hybrid" : "sail" };
    var token = matrix.token, i = 0, t0 = performance.now();
    $("matrixBtn").textContent = "Stop";
    drawMatrix();
    function next() {
      if (token !== matrix.token) return;
      if (i >= pairs.length) {
        matrix.busy = false; $("matrixBtn").textContent = "Fly all 30 transfers";
        var ratios = [], study = DATA.study_transfers[matrix.kind] || {}, est = 0, fail = 0;
        Object.keys(matrix.cells).forEach(function (k) { var c = matrix.cells[k]; if (c.days != null && study[k]) ratios.push(c.days / study[k]); if (c.est) est++; if (c.days == null) fail++; });
        ratios.sort(function (a, b) { return a - b; });
        $("matrixMsg").textContent = "Flew 30 transfers in " + ((performance.now() - t0) / 1000).toFixed(1) + " s, starting " + P0.launch + "." +
          (ratios.length ? " Median ratio to the study: " + ratios[Math.floor(ratios.length / 2)].toFixed(2) + "." : "") +
          (est ? " " + est + " estimated from the reverse leg." : "") + (fail ? " " + fail + " not completed (×)." : "");
        drawMatrix(); return;
      }
      var o = pairs[i][0], d = pairs[i][1];
      var prm = engineParams(Object.assign({}, P0, { orbit: "CIS:" + o, target: d, stop2: "none" }));
      prm.departureTries = [0, 6];
      $("matrixMsg").textContent = "Flying " + TNAME[o] + " → " + TNAME[d] + " (" + (i + 1) + " of 30)…";
      drive(E.runMission(prm), token, function () {}, function (res) {
        var l = res.summary.legs[0] || {};
        matrix.cells[o + ">" + d] = { days: res.status === "ok" ? res.summary.toTargetDays : null, status: res.status, est: !!l.reversed,
          energy: l.energy, phasing: l.phasing, capture: l.capture };
        i++; drawMatrix(); setTimeout(next, 0);
      }, function () { matrix.cells[o + ">" + d] = { days: null, status: "error" }; i++; setTimeout(next, 0); }, function (tk) { return tk === matrix.token; });
    }
    next();
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
      var o = { width: sg.key === "ops" ? 1.8 : 2.2, dashed: sg.key === "trim" || !!sg.est };
      S.tracks.push(trackOf(S.eciGroup, sg.t, fe, PH[sg.key].color, o));
      S.tracks.push(trackOf(S.rotOnly, sg.t, fr, PH[sg.key].color, o));
    });

    // stations of the itinerary (origin and every stop) are highlighted; the rest of the catalogue stays faint
    var keys = [], seen = {};
    (res.origin ? [res.origin.key] : []).concat((res.summary.legs || []).map(function (l) { return l.to; })).concat([res.target.key]).forEach(function (k) { if (!seen[k]) { seen[k] = 1; keys.push(k); } });
    Object.keys(S.catalog).forEach(function (k) { S.catalog[k].visible = !seen[k]; });
    (S.stopLabels || []).forEach(function (x) { if (x.el.parentNode) x.el.parentNode.removeChild(x.el); });
    S.stopLabels = [];
    keys.forEach(function (key) {
      var tg = E.targetInfo(key), obj;
      if (tg.kind === "orbit") {
        var flat = [];
        tg.states.forEach(function (X) { flat.push((X[0] + K.MU) * K.L / 1000, X[1] * K.L / 1000, X[2] * K.L / 1000); });
        var X0 = tg.states[0]; flat.push((X0[0] + K.MU) * K.L / 1000, X0[1] * K.L / 1000, X0[2] * K.L / 1000);
        var gg = new THREE.LineGeometry(); gg.setPositions(flat);
        obj = new THREE.Line2(gg, lineMat(PH.ops.color, 1.6, 0.8));
      } else {
        var L = S.lpts[key].raw, f = [], g2 = new THREE.LineGeometry();
        for (var q = 0; q <= 96; q++) { var an = 2 * Math.PI * q / 96; f.push(L[0] + 14 * Math.cos(an), L[1] + 14 * Math.sin(an), L[2]); }
        g2.setPositions(f); obj = new THREE.Line2(g2, lineMat(PH.ops.color, 1.6, 0.85));
      }
      S.rotGroup.add(obj); S.perResult.push(obj);
      var el = document.createElement("div"); el.className = "lbl"; el.textContent = TNAME[key]; $("labels").appendChild(el);
      S.stopLabels.push({ key: key, tg: tg, el: el });
    });
    S.labels.target.textContent = "";
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

  function aimCamera(view, distance) {
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
    if (distance) dist = distance;
    var tgt0 = focusMode === "moon" && S.moon ? S.moon.position : tgt;
    if (distance) tgt.copy(tgt0);
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
      var ph = phaseAt(t); out.phase = ph ? ph.key : "ops"; out.est = !!(ph && ph.est);
      if (q.n) {
        var n = q.n; out.n = [F.xh[0] * n[0] + F.yh[0] * n[1] + F.zh[0] * n[2], F.xh[1] * n[0] + F.yh[1] * n[1] + F.zh[1] * n[2], F.xh[2] * n[0] + F.yh[2] * n[1] + F.zh[2] * n[2]];
      } else out.n = s;
      out.attitude = out.est ? "Estimated leg" : out.phase === "energy" ? "Pumping energy" : out.phase === "approach" ? "Feathered" : out.phase === "trim" ? "Trimming" : "Station-keeping";
      var sg = segAt(t);
      out.C = sg ? lerpAt(sg.t, sg.C, t) : R.target.C; out.Capprox = !!(sg && (sg.key === "trim" || sg.est));
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
    if (p) { hudEls.sw.style.background = PH[p.key].color; hudEls.ph.textContent = phaseText(p); }
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
    L.target.style.visibility = "hidden";
    (S.stopLabels || []).forEach(function (x) {
      if (x.tg.kind === "orbit") {
        var far = x.tg.states[Math.floor(x.tg.states.length / 4)];
        project(v3(mv(Mrot, [(far[0] + K.MU) * K.L / 1000, far[1] * K.L / 1000, far[2] * K.L / 1000])), x.el, 0, -12);
      } else {
        project(S.lpts[x.key].mesh.getWorldPosition(new THREE.Vector3()), x.el, 0, 16);
        if (L[x.key]) L[x.key].style.visibility = "hidden";
      }
    });

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
    $("matrixBtn").addEventListener("click", startMatrix);
    $("matrixMsg").textContent = "Not flown yet. Fly all 30 (about ten seconds), or select one cell to fly that leg. Small figures are the study's medians.";
    document.querySelectorAll("[data-zoom]").forEach(function (b) { b.addEventListener("click", function () { setZoom(b.getAttribute("data-zoom")); }); });
    drawMatrix();
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
