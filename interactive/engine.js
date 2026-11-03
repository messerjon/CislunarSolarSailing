/* Cislunar solar-sail mission engine (JavaScript port of simulator/cislunar_sail).
 *
 * Phase 1  Earth departure spiral: orbit-averaged Gauss equations in modified
 *          equinoctial elements with J2, eclipses, NRLMSIS orbit-mean drag, sail
 *          (non-ideal optics, locally optimal apogee-raising steering) and SEP.
 * Phase 2  Cislunar energy matching: Earth-Moon CR3BP in the rotating frame with
 *          the Sun line from the ephemeris, solar tidal gravity (BCR4BP), Earth and
 *          Moon shadows and locally optimal Jacobi-constant steering.
 * Phase 3  Approach and insertion: sail/SEP guidance toward the nearest state of the
 *          target periodic orbit (or L4/L5), then operations on the target orbit.
 *
 * Works in the browser (global SailEngine) and in Node (module.exports).
 */
(function (root) {
  "use strict";
  var DATA = (typeof SAIL_DATA !== "undefined") ? SAIL_DATA : (typeof require !== "undefined" ? require("./data.js") : null);

  // ------------------------------------------------------------------ constants
  var K = {
    P_SRP: 1361 / 299792458, MU_E: 398600.4418, MU_M: 4902.800066, MU_S: 1.32712440018e11,
    R_E: 6378.137, R_M: 1737.4, J2: 1.08262668e-3, OMEGA_E: 7.2921159e-5, AU: 149597870.7,
    DAY: 86400, G0: 9.80665, D_EM: 384400,
  };
  K.MU = DATA.mu; K.L = DATA.L_km; K.T = DATA.T_s; K.V = K.L / K.T;
  K.A_MM = K.L * 1e6 / (K.T * K.T);             // mm/s^2 per non-dimensional acceleration unit
  K.MASS_SUN = K.MU_S / (K.MU_E + K.MU_M);
  K.A_SUN = K.AU / K.L;
  K.W = 1 / K.T;                                  // rotating-frame rate (rad/s)
  var PI = Math.PI, TWO_PI = 2 * Math.PI, RAD = PI / 180;

  // ------------------------------------------------------------------ vectors
  function add(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
  function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
  function scl(a, s) { return [a[0] * s, a[1] * s, a[2] * s]; }
  function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
  function crs(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
  function nrm(a) { return Math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]); }
  function unit(a) { var n = nrm(a); return n > 1e-30 ? [a[0] / n, a[1] / n, a[2] / n] : [0, 0, 0]; }
  function clamp(x, lo, hi) { return x < lo ? lo : (x > hi ? hi : x); }

  // ------------------------------------------------------------------ time & ephemerides
  function jdFromDate(d) { return d.getTime() / 86400000 + 2440587.5; }
  function dateFromJd(jd) { return new Date((jd - 2440587.5) * 86400000); }

  function sunEci(jd) {
    var n = jd - 2451545.0;
    var L = (280.460 + 0.9856474 * n) * RAD, g = (357.528 + 0.9856003 * n) * RAD;
    var lam = L + 1.915 * RAD * Math.sin(g) + 0.020 * RAD * Math.sin(2 * g);
    var eps = (23.439 - 4e-7 * n) * RAD;
    var R = 1.00014 - 0.01671 * Math.cos(g) - 0.00014 * Math.cos(2 * g);
    return { u: [Math.cos(lam), Math.cos(eps) * Math.sin(lam), Math.sin(eps) * Math.sin(lam)], R: R };
  }

  function moonEci(jd) {
    var n = jd - 2451545.0;
    var Lm = (218.316 + 13.176396 * n) * RAD, Om = (125.045 - 0.0529538 * n) * RAD, i = 5.145 * RAD;
    var u = Lm - Om, eps = 23.4393 * RAD, nM = 13.176396 * RAD / K.DAY;
    var cO = Math.cos(Om), sO = Math.sin(Om), cu = Math.cos(u), su = Math.sin(u), ci = Math.cos(i), si = Math.sin(i);
    var x = cO * cu - sO * su * ci, y = sO * cu + cO * su * ci, z = su * si;
    var vx = (-cO * su - sO * cu * ci) * nM, vy = (-sO * su + cO * cu * ci) * nM, vz = cu * si * nM;
    var ce = Math.cos(eps), se = Math.sin(eps), D = K.D_EM;
    return { r: [x * D, (ce * y - se * z) * D, (se * y + ce * z) * D], v: [vx * D, (ce * vy - se * vz) * D, (se * vy + ce * vz) * D] };
  }

  function moonInclination(jd) {
    var Om = (125.045 - 0.0529538 * (jd - 2451545.0)) * RAD, i = 5.145 * RAD, eps = 23.4393 * RAD;
    return Math.acos(Math.cos(eps) * Math.cos(i) - Math.sin(eps) * Math.sin(i) * Math.cos(Om)) / RAD;
  }

  /** Rotating-frame axes (x Earth->Moon, z orbit normal) at jd. */
  function frameAt(jd) {
    var m = moonEci(jd);
    var xh = unit(m.r), zh = unit(crs(m.r, m.v)), yh = crs(zh, xh);
    return { xh: xh, yh: yh, zh: zh, rM: m.r, vM: m.v };
  }

  /** Earth-centred inertial state (km, km/s) -> rotating barycentric non-dimensional state. */
  function eciToRot(r, v, jd) {
    var F = frameAt(jd), mu = K.MU;
    var rb = sub(r, scl(F.rM, mu)), vb = sub(v, scl(F.vM, mu));
    var x = dot(rb, F.xh), y = dot(rb, F.yh), z = dot(rb, F.zh);
    var vx = dot(vb, F.xh), vy = dot(vb, F.yh), vz = dot(vb, F.zh);
    return [x / K.L, y / K.L, z / K.L, (vx + K.W * y) / K.V, (vy - K.W * x) / K.V, vz / K.V];
  }

  /** Rotating non-dimensional state -> Earth-centred inertial position (km) and velocity (km/s). */
  function rotToEci(X, jd, F) {
    F = F || frameAt(jd);
    var x = X[0] * K.L, y = X[1] * K.L, z = X[2] * K.L;
    var vx = X[3] * K.V - K.W * y, vy = X[4] * K.V + K.W * x, vz = X[5] * K.V;
    var rb = add(add(scl(F.xh, x), scl(F.yh, y)), scl(F.zh, z));
    var vb = add(add(scl(F.xh, vx), scl(F.yh, vy)), scl(F.zh, vz));
    return { r: add(rb, scl(F.rM, K.MU)), v: add(vb, scl(F.vM, K.MU)) };
  }

  /** Earth-centred inertial position (km) -> Earth-centred rotating coordinates (km). */
  function eciToRotPos(r, jd, F) {
    F = F || frameAt(jd);
    return [dot(r, F.xh), dot(r, F.yh), dot(r, F.zh)];
  }

  function sunRot(jd, F) {
    F = F || frameAt(jd);
    var s = sunEci(jd);
    return { u: [dot(s.u, F.xh), dot(s.u, F.yh), dot(s.u, F.zh)], R: s.R };
  }

  // ------------------------------------------------------------------ sail optics and steering
  function faceCoeffs(f, derate) {
    var e = f.ef + f.eb;
    var therm = e > 0 ? (1 - f.r) * (f.ef * f.Bf - f.eb * f.Bb) / e : 0;
    var c = { a1: 2 * f.r * f.s, a2: f.Bf * (1 - f.s) * f.r + therm, a3: 1 - f.r * f.s };
    c.tot = c.a1 + c.a2 + c.a3;
    c.derate = derate || 1;
    return c;
  }

  var _tables = {};
  function steeringTable(fc, key) {
    if (_tables[key]) return _tables[key];
    var NT = 721, NA = 361, th = new Float64Array(NT), al = new Float64Array(NT), g = new Float64Array(NT);
    for (var i = 0; i < NT; i++) {
      var t = PI * i / (NT - 1), best = -1e9, ba = PI / 2;
      for (var j = 0; j < NA; j++) {
        var a = (PI / 2) * j / (NA - 1), c = Math.cos(a);
        var v = c * (fc.a3 * Math.cos(t) + (fc.a1 * c + fc.a2) * Math.cos(t - a));
        if (v > best) { best = v; ba = a; }
      }
      best /= fc.tot;
      if (best <= 0) { best = 0; ba = PI / 2; }
      th[i] = t; al[i] = ba; g[i] = best;
    }
    _tables[key] = { th: th, al: al, g: g, dth: PI / (NT - 1) };
    return _tables[key];
  }

  function interp(tab, arr, t) {
    var u = clamp(t / tab.dth, 0, arr.length - 1.000001), i0 = Math.floor(u), w = u - i0;
    return arr[i0] * (1 - w) + arr[i0 + 1] * w;
  }

  /** In-plane basis: e2 = component of d normal to s (unit), theta = angle(s, d) in [0, pi]. */
  function perpBasis(s, d) {
    var cs = dot(s, d);
    var e2 = [d[0] - cs * s[0], d[1] - cs * s[1], d[2] - cs * s[2]], n = nrm(e2);
    if (n < 1e-9) {
      var ref = Math.abs(s[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
      e2 = unit(crs(s, ref));
    } else e2 = [e2[0] / n, e2[1] / n, e2[2] / n];
    return { e2: e2, theta: Math.atan2(Math.abs(dot(d, e2)), cs) };
  }

  /** Locally optimal sail normal maximising the force component along d (feather when nothing useful). */
  function optimalNormal(fc, tab, s, d) {
    var b = perpBasis(s, d), a = interp(tab, tab.al, b.theta), g = interp(tab, tab.g, b.theta);
    if (g <= 0) return { n: unit(crs(s, b.e2)), g: 0 };
    var ca = Math.cos(a), sa = Math.sin(a);
    return { n: [ca * s[0] + sa * b.e2[0], ca * s[1] + sa * b.e2[1], ca * s[2] + sa * b.e2[2]], g: g };
  }

  /** Sail acceleration (units of ac) for front-face normal n; back face used when n points sunward. */
  function sailAccel(film, s, n, ac) {
    var c = dot(s, n), F = [0, 0, 0];
    if (c > 0) {
      var f = film.front, k = c * (f.a1 * c + f.a2);
      F = [c * f.a3 * s[0] + k * n[0], c * f.a3 * s[1] + k * n[1], c * f.a3 * s[2] + k * n[2]];
    } else if (c < 0) {
      var b = film.back, cb = -c, kb = cb * (b.a1 * cb + b.a2);
      F = [cb * b.a3 * s[0] - kb * n[0], cb * b.a3 * s[1] - kb * n[1], cb * b.a3 * s[2] - kb * n[2]];
    }
    var sc = ac / film.front.tot;
    return [F[0] * sc, F[1] * sc, F[2] * sc];
  }

  /** In-plane search for the sail normal (and SEP pointing) maximising the total useful component along d.
   *  asep: SEP acceleration magnitude (0 = off); gimbal: SEP may point within this angle of +/-n.
   *  dragK, vh: optional drag penalty (acceleration per unit projected-area fraction, along -vh). */
  function bestHybrid(fc, s, d, ac, asep, gimbalDeg, nA, dragK, vh) {
    var b = perpBasis(s, d), cth = Math.cos(b.theta), sth = Math.sin(b.theta), e2 = b.e2;
    var G = Math.min(gimbalDeg, 180) * RAD, cG = Math.cos(G), sG = Math.sin(G);
    var cnv1 = vh ? dot(s, vh) : 0, cnv2 = vh ? dot(e2, vh) : 0, dvd = vh ? dot(vh, d) : 0;
    var best = -1e30, bA = 0, bSail = 0, bSep = 0;
    nA = nA || 61;
    for (var j = 0; j < nA; j++) {
      var a = -PI / 2 + PI * j / (nA - 1), ca = Math.cos(a), sa = Math.sin(a);
      var fn = ca * (fc.a1 * ca + fc.a2);
      var Fs = (ca * fc.a3 + fn * ca) / fc.tot, Fp = fn * sa / fc.tot;
      var cs = ac * (Fs * cth + Fp * sth), sep = 0;
      if (asep > 0) {
        var cnd = ca * cth + sa * sth, snd = Math.sqrt(Math.max(1 - cnd * cnd, 0));
        if (gimbalDeg >= 90) sep = 1;
        else {
          var cp = cnd >= cG ? 1 : cnd * cG + snd * sG;
          var cm = -cnd >= cG ? 1 : -cnd * cG + snd * sG;
          sep = Math.max(cp, cm, 0);
        }
        sep *= asep;
      }
      var tot = cs + sep;
      if (dragK) tot -= dragK * Math.abs(ca * cnv1 + sa * cnv2) * dvd;
      if (tot > best) { best = tot; bA = a; bSail = cs; bSep = sep; }
    }
    var cb = Math.cos(bA), sb = Math.sin(bA);
    return { n: [cb * s[0] + sb * e2[0], cb * s[1] + sb * e2[1], cb * s[2] + sb * e2[2]], comp: best, compSail: bSail, compSep: bSep };
  }

  function makeFilm(key, derate) {
    var f = DATA.films[key];
    var film = { key: key, name: f.name, front: faceCoeffs(f.front), back: faceCoeffs(f.back), areal: f.areal_gm2 };
    film.table = steeringTable(film.front, key);
    film.derate = derate == null ? 1 : derate;
    return film;
  }

  // ------------------------------------------------------------------ atmosphere and solar cycle
  /** Approximate F10.7 from the Solar Cycle 25 / 26 timing (maxima ~2024.9 and ~2035.9). */
  function f107ForYear(y) {
    var ph = TWO_PI * (y - 2024.9) / 11.0;
    return 70 + 115 * (0.5 + 0.5 * Math.cos(ph));
  }
  /** NRLMSIS density (kg/m^3) at altitude and local solar time; log-interpolated across F10.7 tables. */
  function rhoLst(altKm, lstH, f107) {
    var T = DATA.density_lst, alt = T.alt, lst = T.lst;
    if (!(altKm <= 2000)) return 0;
    var u = clamp((altKm - alt[0]) / (alt[1] - alt[0]), 0, alt.length - 1.000001), i0 = Math.floor(u), wi = u - i0;
    var v = clamp(lstH / (lst[1] - lst[0]), 0, lst.length - 1.000001), j0 = Math.floor(v), wj = v - j0;
    function lr(key) {
      var a = T[key];
      return a[i0][j0] * (1 - wi) * (1 - wj) + a[i0 + 1][j0] * wi * (1 - wj) + a[i0][j0 + 1] * (1 - wi) * wj + a[i0 + 1][j0 + 1] * wi * wj;
    }
    var lo = lr("70"), mid = lr("150"), hi = lr("230"), x;
    if (f107 <= 150) x = lo + (mid - lo) * clamp((f107 - 70) / 80, -0.5, 1);
    else x = mid + (hi - mid) * clamp((f107 - 150) / 80, 0, 1.5);
    return Math.exp(x);
  }
  function rhoMean(altKm, f107) {
    var Dn = DATA.density_log, alt = Dn.alt;
    if (altKm > 2000) return 0;
    var u = clamp((altKm - alt[0]) / (alt[1] - alt[0]), 0, alt.length - 1.000001), i0 = Math.floor(u), w = u - i0;
    function lr(key) { var a = Dn[key]; return a[i0] * (1 - w) + a[i0 + 1] * w; }
    var lo = lr("70"), mid = lr("150"), hi = lr("230"), v;
    if (f107 <= 150) v = lo + (mid - lo) * clamp((f107 - 70) / 80, -0.5, 1);
    else v = mid + (hi - mid) * clamp((f107 - 150) / 80, 0, 1.5);
    return Math.exp(v);
  }

  // ------------------------------------------------------------------ orbital elements
  function coeToMee(a, e, i, raan, argp, nu) {
    var p = a * (1 - e * e);
    return [p, e * Math.cos(argp + raan), e * Math.sin(argp + raan), Math.tan(i / 2) * Math.cos(raan),
            Math.tan(i / 2) * Math.sin(raan), raan + argp + (nu || 0)];
  }
  function meeToRV(p, f, g, h, k, L, mu) {
    var cL = Math.cos(L), sL = Math.sin(L), al2 = h * h - k * k, s2 = 1 + h * h + k * k, w = 1 + f * cL + g * sL;
    var r = p / w, sq = Math.sqrt(mu / p);
    return {
      r: [r / s2 * (cL + al2 * cL + 2 * h * k * sL), r / s2 * (sL - al2 * sL + 2 * h * k * cL), 2 * r / s2 * (h * sL - k * cL)],
      v: [-sq / s2 * (sL + al2 * sL - 2 * h * k * cL + g - 2 * f * h * k + al2 * g),
          -sq / s2 * (-cL + al2 * cL + 2 * h * k * sL - f + 2 * g * h * k + al2 * f),
          2 * sq / s2 * (h * cL + k * sL + f * h + g * k)],
      w: w, s2: s2, rm: r,
    };
  }
  function meeInfo(y) {
    var e = Math.sqrt(y[1] * y[1] + y[2] * y[2]), a = y[0] / (1 - e * e);
    return { e: e, a: a, ra: a * (1 + e), rp: a * (1 - e), inc: 2 * Math.atan(Math.sqrt(y[3] * y[3] + y[4] * y[4])) / RAD,
             raan: Math.atan2(y[4], y[3]), lonper: Math.atan2(y[2], y[1]) };
  }
  /** Orbit normal of an MEE state (unit). */
  function meeNormal(y) {
    var h = y[3], k = y[4], s2 = 1 + h * h + k * k;
    return [2 * k / s2, -2 * h / s2, (1 - h * h - k * k) / s2];
  }
  /** Approximate Earth-Moon Jacobi constant of an Earth-centred osculating orbit (Moon potential neglected). */
  function jacobiFromMee(y, jd) {
    var I = meeInfo(y), F = frameAt(jd), hn = meeNormal(y);
    var aN = I.a / K.L, hND = Math.sqrt(K.MU_E * y[0]) / (K.L * K.V);
    return (1 - K.MU) / aN + 2 * hND * dot(hn, F.zh);
  }
  function trueFromMean(M, e) {
    var E = M + e * Math.sin(M);
    for (var it = 0; it < 30; it++) {
      var dE = (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
      E -= dE;
      if (Math.abs(dE) < 1e-12) break;
    }
    return 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(E / 2), Math.sqrt(1 - e) * Math.cos(E / 2));
  }

  // ------------------------------------------------------------------ phase 1: orbit-averaged rates
  function averagedRates(y, jd, sc, opt) {
    var mu = K.MU_E, Rb = K.R_E, Kn = opt.K || 48;
    var p = Math.max(y[0], 1000), f = y[1], g = y[2], h = y[3], k = y[4], m = Math.max(y[5], 1e-3);
    var ecc = Math.sqrt(f * f + g * g);
    if (ecc > 0.99) { f *= 0.99 / ecc; g *= 0.99 / ecc; ecc = 0.99; }
    var e = ecc, lonper = Math.atan2(g, f), a = p / (1 - e * e), hmom = Math.sqrt(mu * p);
    var sun = sunEci(jd), us = sun.u, s = [-us[0], -us[1], -us[2]];
    var acNow = sc.acMM * 1e-6 * (sc.m0 / m) / (sun.R * sun.R);                   // km/s^2 (derate included)
    var rpNow = p / (1 + e);
    var sepAvail = sc.sepThrust > 0 && m > sc.mDry + 1e-6;
    var deployed = !(sepAvail && rpNow < K.R_E + sc.deployAlt);        // stowed while SEP climbs; deploy once the tank is empty
    var area = deployed ? sc.area : sc.stowedArea;
    var acEff = deployed ? acNow : 0;
    var lam = 0;
    if (opt.rpSafe) lam = clamp((opt.rpSafe - rpNow) / Math.max(opt.rpSafe - (Rb + 150), 1), 0, 1) * 4;
    var dp = 0, df = 0, dg = 0, dh = 0, dk = 0, sepFrac = 0, lit_ = 0, useful = 0;
    var drag = opt.f107 != null;
    for (var j = 0; j < Kn; j++) {
      var E = (j + 0.5) * TWO_PI / Kn;
      var nu = 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(E / 2), Math.sqrt(Math.max(1 - e, 1e-12)) * Math.cos(E / 2));
      var L = nu + lonper, wt = (1 - e * Math.cos(E)) / Kn;
      var st = meeToRV(p, f, g, h, k, L, mu), rv = st.r, vv = st.v, rm = st.rm, w = st.w, s2 = st.s2;
      var Rh = scl(rv, 1 / rm), Nh = unit(crs(rv, vv)), Th = crs(Nh, Rh), vh = unit(vv);
      var proj = dot(rv, us), perp = nrm(sub(rv, scl(us, proj)));
      var lit = (proj >= 0 || perp >= Rb) ? 1 : 0;
      // objective: apogee-raising gradient blended with perigee protection
      var sn = Math.sin(nu), cn = Math.cos(nu);
      var daR = 2 * a * a / hmom * e * sn, daT = 2 * a * a / hmom * p / rm;
      var deR = p * sn / hmom, deT = ((p + rm) * cn + rm * e) / hmom;
      var ga = add(scl(Rh, (1 + e) * daR + a * deR), scl(Th, (1 + e) * daT + a * deT));
      var d;
      if (opt.objective === "energy") d = vh;
      else if (opt.objective === "energy_down") d = scl(vh, -1);
      else {
        d = unit(ga);
        if (lam > 0) {
          var gp = add(scl(Rh, (1 - e) * daR - a * deR), scl(Th, (1 - e) * daT - a * deT));
          d = unit(add(d, scl(unit(gp), lam)));
        }
      }
      var asep = (sepAvail && (lit || sc.sepInShadow)) ? sc.sepThrust / m * 1e-3 : 0;
      var dragK = 0, vrh = null, alt = rm - Rb;
      if (drag && alt < 2000) {
        var vrel = [vv[0] + K.OMEGA_E * rv[1], vv[1] - K.OMEGA_E * rv[0], vv[2]];
        var lst = (((Math.atan2(rv[1], rv[0]) - Math.atan2(us[1], us[0])) * 12 / PI + 12) % 24 + 24) % 24;
        var vr = nrm(vrel) * 1e3, q = 0.5 * rhoLst(alt, lst, opt.f107) * vr * vr;
        dragK = q * sc.cd * area / m * 1e-3;
        vrh = scl(vrel, 1 / nrm(vrel));
      }
      var nh, acc = [0, 0, 0], comp_sep = 0;
      var acLit = acEff * lit;
      if (asep === 0 && dragK === 0) {
        if (acLit > 0) {
          var on = optimalNormal(sc.film.front, sc.film.table, s, d);
          nh = on.n;
          acc = sailAccel(sc.film, s, nh, acLit);
        }
      } else {
        var bh = bestHybrid(sc.film.front, s, d, acLit, asep, sc.gimbal, opt.nAlpha || (dragK > 0 && asep === 0 ? 41 : 61), dragK > 0 ? dragK : 0, vh);
        nh = bh.n;
        if (acLit > 0) acc = sailAccel(sc.film, s, nh, acLit);
        comp_sep = bh.compSep;
        if (comp_sep > 0) { acc = add(acc, scl(d, comp_sep)); sepFrac += wt; }
        if (dragK > 0) {
          var pr = deployed ? Math.abs(dot(nh, vrh)) * (1 - sc.minAreaFrac) + sc.minAreaFrac : 1;
          acc = sub(acc, scl(vrh, dragK * pr));
        }
      }
      if (acLit > 0) useful += dot(sailAccel(sc.film, s, nh, acLit), d) / acEff * wt;
      lit_ += lit * wt;
      // J2
      var z2 = (rv[2] / rm) * (rv[2] / rm), cj = -1.5 * K.J2 * mu * Rb * Rb / Math.pow(rm, 4);
      acc = add(acc, [cj * (1 - 5 * z2) * rv[0] / rm, cj * (1 - 5 * z2) * rv[1] / rm, cj * (3 - 5 * z2) * rv[2] / rm]);
      var Rc = dot(acc, Rh), Tc = dot(acc, Th), Nc = dot(acc, Nh);
      var cL = Math.cos(L), sL = Math.sin(L), sqp = Math.sqrt(p / mu);
      dp += wt * (2 * p / w * sqp * Tc);
      df += wt * sqp * (Rc * sL + ((w + 1) * cL + f) * Tc / w - (h * sL - k * cL) * g * Nc / w);
      dg += wt * sqp * (-Rc * cL + ((w + 1) * sL + g) * Tc / w + (h * sL - k * cL) * f * Nc / w);
      dh += wt * sqp * s2 * Nc * cL / (2 * w);
      dk += wt * sqp * s2 * Nc * sL / (2 * w);
    }
    var dm = sepAvail ? -sc.sepThrust / (sc.isp * K.G0) * sepFrac : 0;
    return { dy: [dp, df, dg, dh, dk, dm], lit: lit_, useful: useful, deployed: deployed };
  }

  function rk4Mee(y, jd, dtDays, sc, opt) {
    var dt = dtDays * K.DAY;
    function f(yy, jj) { return averagedRates(yy, jj, sc, opt); }
    var k1 = f(y, jd), y2 = y.map(function (v, i) { return v + 0.5 * dt * k1.dy[i]; });
    var k2 = f(y2, jd + dtDays / 2), y3 = y.map(function (v, i) { return v + 0.5 * dt * k2.dy[i]; });
    var k3 = f(y3, jd + dtDays / 2), y4 = y.map(function (v, i) { return v + dt * k3.dy[i]; });
    var k4 = f(y4, jd + dtDays);
    var yn = y.map(function (v, i) { return v + dt / 6 * (k1.dy[i] + 2 * k2.dy[i] + 2 * k3.dy[i] + k4.dy[i]); });
    if (yn[5] < sc.mDry) yn[5] = sc.mDry;
    return { y: yn, info: k1 };
  }

  // ------------------------------------------------------------------ CR3BP with sail / SEP
  function shadowRot(r, u) {
    var mu = K.MU, re = K.R_E / K.L, rmn = K.R_M / K.L;
    var rE = [r[0] + mu, r[1], r[2]], pE = dot(rE, u);
    if (pE < 0 && nrm(sub(rE, scl(u, pE))) < re) return 0;
    var rM = [r[0] - 1 + mu, r[1], r[2]], pM = dot(rM, u);
    if (pM < 0 && nrm(sub(rM, scl(u, pM))) < rmn) return 0;
    return 1;
  }

  function gravRot(X) {
    var mu = K.MU, x = X[0], y = X[1], z = X[2];
    var r1 = Math.sqrt((x + mu) * (x + mu) + y * y + z * z), r2 = Math.sqrt((x - 1 + mu) * (x - 1 + mu) + y * y + z * z);
    var a1 = (1 - mu) / (r1 * r1 * r1), a2 = mu / (r2 * r2 * r2);
    return { a: [x - a1 * (x + mu) - a2 * (x - 1 + mu) + 2 * X[4], y - a1 * y - a2 * y - 2 * X[3], -a1 * z - a2 * z], r1: r1, r2: r2 };
  }

  function jacobi(X) {
    var mu = K.MU, x = X[0], y = X[1], z = X[2];
    var r1 = Math.sqrt((x + mu) * (x + mu) + y * y + z * z), r2 = Math.sqrt((x - 1 + mu) * (x - 1 + mu) + y * y + z * z);
    return x * x + y * y + 2 * (1 - mu) / r1 + 2 * mu / r2 - (X[3] * X[3] + X[4] * X[4] + X[5] * X[5]);
  }

  /** Control acceleration (non-dimensional) for a law at state X and time jd. */
  function controlRot(X, jd, ctx) {
    var F = frameAt(jd), sr = sunRot(jd, F), u = sr.u, s = [-u[0], -u[1], -u[2]], r = [X[0], X[1], X[2]];
    var lit = shadowRot(r, u);
    var mr = ctx.m0 / ctx.m;
    var ac = ctx.acND * mr / (sr.R * sr.R) * lit;
    var asep = (ctx.sepND > 0 && ctx.m > ctx.mDry + 1e-6 && (lit || ctx.sepInShadow)) ? ctx.sepND * mr : 0;
    var a = [0, 0, 0], n = null, sepOn = 0, d = null;
    if (ctx.law === "jacobi") d = scl(unit([X[3], X[4], X[5]]), ctx.sign);
    else if (ctx.law === "dir") d = ctx.dir;
    if (d && (ac > 0 || asep > 0)) {
      if (asep > 0) {
        var bh = bestHybrid(ctx.film.front, s, d, ac, asep, ctx.gimbal, 31);
        n = bh.n;
        if (ac > 0) a = sailAccel(ctx.film, s, n, ac);
        if (bh.compSep > 0) { a = add(a, scl(d, bh.compSep)); sepOn = 1; }
      } else {
        var on = optimalNormal(ctx.film.front, ctx.film.table, s, d);
        n = on.n;
        a = sailAccel(ctx.film, s, n, ac);
      }
    }
    if (!n) n = unit(crs(s, Math.abs(s[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0]));   // feathered (edge-on)
    if (ctx.solarGravity) {
      var rs = scl(u, K.A_SUN * sr.R), dd = sub(rs, r), dn = nrm(dd), rsn = nrm(rs);
      a = add(a, scl(sub(scl(dd, 1 / (dn * dn * dn)), scl(rs, 1 / (rsn * rsn * rsn))), K.MASS_SUN));
    }
    return { a: a, n: n, sepOn: sepOn, s: s, lit: lit };
  }

  function derivRot(X, jd, ctx) {
    var g = gravRot(X), c = controlRot(X, jd, ctx);
    return { d: [X[3], X[4], X[5], g.a[0] + c.a[0], g.a[1] + c.a[1], g.a[2] + c.a[2]], c: c, r1: g.r1, r2: g.r2 };
  }

  function stepSize(X, h0) {
    var mu = K.MU, x = X[0], y = X[1], z = X[2];
    var r1 = Math.sqrt((x + mu) * (x + mu) + y * y + z * z), r2 = Math.sqrt((x - 1 + mu) * (x - 1 + mu) + y * y + z * z);
    var P1 = TWO_PI * Math.sqrt(r1 * r1 * r1 / (1 - mu)), P2 = TWO_PI * Math.sqrt(r2 * r2 * r2 / mu);
    return Math.max(Math.min(h0, P1 / 200, P2 / 200), 2e-6);
  }

  function rk4Rot(X, jd, h, ctx) {
    var dj = h * K.T / K.DAY;
    var k1 = derivRot(X, jd, ctx);
    var X2 = X.map(function (v, i) { return v + 0.5 * h * k1.d[i]; });
    var k2 = derivRot(X2, jd + dj / 2, ctx);
    var X3 = X.map(function (v, i) { return v + 0.5 * h * k2.d[i]; });
    var k3 = derivRot(X3, jd + dj / 2, ctx);
    var X4 = X.map(function (v, i) { return v + h * k3.d[i]; });
    var k4 = derivRot(X4, jd + dj, ctx);
    return { X: X.map(function (v, i) { return v + h / 6 * (k1.d[i] + 2 * k2.d[i] + 2 * k3.d[i] + k4.d[i]); }), c: k1.c,
             r1: k1.r1, r2: k1.r2 };
  }

  // ------------------------------------------------------------------ targets
  function targetInfo(key) {
    var o = null;
    DATA.orbits.forEach(function (q) { if (q.key === key) o = q; });
    if (o) return { key: key, label: o.label, C: o.C, period: o.period, periodDays: o.period_days, states: o.states,
                    stability: o.stability, kind: "orbit" };
    var Lp = DATA.lagrange[key];
    return { key: key, label: key === "L4" ? "Earth-Moon L4 (leading)" : "Earth-Moon L5 (trailing)", C: DATA.C_lagrange[key],
             period: null, states: [[Lp[0], Lp[1], Lp[2], 0, 0, 0]], kind: "point" };
  }

  function nearestOnTarget(X, tgt, Rs, Vs) {
    var best = 1e30, bi = 0, S = tgt.states;
    for (var i = 0; i < S.length; i++) {
      var q = S[i];
      var dr = Math.hypot(X[0] - q[0], X[1] - q[1], X[2] - q[2]) / Rs;
      var dv = Math.hypot(X[3] - q[3], X[4] - q[4], X[5] - q[5]) / Vs;
      var v = dr + dv;
      if (v < best) { best = v; bi = i; }
    }
    var q = S[bi];
    return { i: bi, d: best, dr: Math.hypot(X[0] - q[0], X[1] - q[1], X[2] - q[2]), dv: Math.hypot(X[3] - q[3], X[4] - q[4], X[5] - q[5]) };
  }

  // ------------------------------------------------------------------ phase 3: phasing coast and modelled capture
  /** Weighted phase-space distance |dr|/Rs + |dv|/Vs to the nearest sampled target state. */
  function wdist(X, S, stride, Rs, Vs) {
    var best = 1e30, bi = 0;
    for (var i = 0; i < S.length; i += stride) {
      var q = S[i], a = X[0] - q[0], b = X[1] - q[1], c = X[2] - q[2], u = X[3] - q[3], v = X[4] - q[4], w = X[5] - q[5];
      var d = Math.sqrt(a * a + b * b + c * c) / Rs + Math.sqrt(u * u + v * v + w * w) / Vs;
      if (d < best) { best = d; bi = i; }
    }
    var p = S[bi];
    return { d: best, i: bi, dr: Math.hypot(X[0] - p[0], X[1] - p[1], X[2] - p[2]), dv: Math.hypot(X[3] - p[3], X[4] - p[4], X[5] - p[5]) };
  }

  function smoothstep(x) { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); }

  /** State on a sampled periodic orbit, starting at (fractional) index i0 and advanced by tau (ND). */
  function orbitState(tgt, i0, tau) {
    var S = tgt.states, N = S.length;
    if (tgt.kind === "point") return S[0].slice();
    var u = ((i0 + tau / tgt.period * N) % N + N) % N, a = Math.floor(u), b = (a + 1) % N, w = u - a;
    return S[a].map(function (v, k) { return v * (1 - w) + S[b][k] * w; });
  }

  /** Phase 3. After the energy match the sail is feathered and the spacecraft coasts (full model) for up to one
   *  synodic lap while its geometry relative to the target drifts; the best point of the coast (weighted
   *  position/velocity distance to the target orbit, earlier preferred) starts the capture leg. The capture leg is
   *  not optimised here; as in the study (Q3, T = T_energy + T_coast) its duration is the natural coast time for
   *  the target, extended when the sail (+SEP) needs longer to null the velocity mismatch, and it is drawn as the
   *  target orbit plus a smoothly decaying offset. */
  function* approach(X0, jdA0, tA0, ctx, tgt, sc, mdot) {
    var point = tgt.kind === "point", S = tgt.states;
    var Rs = 40000 / K.L, Vs = 0.15 / K.V, win = (point ? 45 : 30) * K.DAY / K.T;
    var coastD = DATA.coast_days[tgt.key] || 14;
    var rCrash = (K.R_M + 50) / K.L, rCrashE = (K.R_E + 200) / K.L;
    var X = X0.slice(), tA = 0, rec = 0, nStep = 0, best = null, stop = null;
    var p3 = { t: [], X: [], n: [], m: [], d: [] };
    ctx.law = "feather";
    while (tA < win) {
      var jd = jdA0 + tA * K.T / K.DAY, h = Math.min(stepSize(X, 2e-3), win - tA);
      var st = rk4Rot(X, jd, h, ctx), nr = wdist(X, S, point ? 1 : 2, Rs, Vs);
      if ((rec++ & 1) === 0) { p3.t.push(tA0 + tA * K.T / K.DAY); p3.X.push(X.slice()); p3.n.push(st.c.n); p3.m.push(ctx.m); p3.d.push(nr.d); }
      var score = nr.d * (1 + tA * K.T / K.DAY / 60);
      if (!best || score < best.score) best = { score: score, d: nr.d, i: nr.i, dr: nr.dr, dv: nr.dv, t: tA, X: X.slice(), k: p3.t.length };
      X = st.X; tA += h;
      if (st.r2 < rCrash) { stop = "Moon"; break; }
      if (st.r1 < rCrashE) { stop = "Earth"; break; }
      if (Math.hypot(X[0], X[1], X[2]) > 3) { stop = "escape"; break; }
      if (++nStep % 600 === 0) yield { phase: "Phasing", frac: tA / win, msg: "Phasing toward " + tgt.label + ": day " + Math.round(tA0 + tA * K.T / K.DAY) };
    }
    ["t", "X", "n", "m", "d"].forEach(function (k) { p3[k].length = Math.max(best.k, 1); });
    var tCapStart = tA0 + best.t * K.T / K.DAY;
    // capture duration: the study's coast time, or the time to null the velocity mismatch at 35 % of a_c plus 80 %
    // of the SEP acceleration, whichever is longer (capped at 120 days)
    var dvT = best.dv * K.V * 1000;
    var sepA = ctx.m > ctx.mDry ? 0.8 * ctx.sepND * K.A_MM * 1e-3 * ctx.m0 / ctx.m : 0;
    var aEff = 0.35 * ctx.acND * K.A_MM * 1e-3 * ctx.m0 / ctx.m + sepA;
    var trimD = dvT / Math.max(aEff, 1e-12) / K.DAY, capD = clamp(Math.max(coastD, trimD), coastD, 120);
    if (sepA > 0) ctx.m = Math.max(ctx.m - mdot * capD * K.DAY * (sepA / aEff) * Math.min(trimD / capD, 1), ctx.mDry);
    var TT = capD * K.DAY / K.T, p4 = { t: [], X: [] }, NB = Math.max(60, Math.ceil(capD * 10));
    var err = best.X.map(function (v, k) { return v - S[best.i][k]; });
    for (var j = 0; j <= NB; j++) {
      var tau = TT * j / NB, Q = orbitState(tgt, best.i, tau), w = 1 - smoothstep(tau / TT);
      p4.t.push(tCapStart + tau * K.T / K.DAY); p4.X.push(Q.map(function (v, k) { return v + w * err[k]; }));
    }
    return { outcome: "captured", p3: p3, p4: p4, tCap: tCapStart, tIns: tCapStart + capD, coastStop: stop,
             trim: { dv: dvT, days: trimD, coastDays: coastD, captureDays: capD }, dr: best.dr, dv: best.dv,
             iIns: point ? 0 : ((best.i + TT / tgt.period * S.length) % S.length) };
  }

  // ------------------------------------------------------------------ mission
  function departureState(prm, jd0) {
    var R = K.R_E, a, e, inc = prm.inc * RAD, raan = (prm.raan || 0) * RAD, argp = (prm.argp || 0) * RAD;
    if (prm.orbit === "LEO") { a = R + prm.alt; e = 1e-4; }
    else if (prm.orbit === "GEO") { a = R + 35786; e = 1e-4; }
    else { var rp = R + prm.perigee, ra = R + prm.apogee; a = (rp + ra) / 2; e = (ra - rp) / (ra + rp); }
    return coeToMee(a, e, inc, raan, argp, 0);
  }

  /** TLI departure: perigee state whose apogee points at the Moon's position on arrival. */
  function tliState(prm, jd0) {
    var rp = K.R_E + prm.perigee, ra = prm.apogee;
    var a = (rp + ra) / 2, e = (ra - rp) / (ra + rp), p = a * (1 - e * e);
    var r384 = K.D_EM * 0.97, nu = Math.acos(clamp((p / r384 - 1) / e, -1, 1));
    var E = 2 * Math.atan(Math.sqrt((1 - e) / (1 + e)) * Math.tan(nu / 2)), M = E - e * Math.sin(E);
    var tof = M / Math.sqrt(K.MU_E / (a * a * a)) / K.DAY;
    var F = frameAt(jd0 + tof), aim = F.xh, hn = F.zh;
    var lead = (prm.tliLead || 0) * RAD;
    var dirA = add(scl(aim, Math.cos(lead)), scl(crs(hn, aim), Math.sin(lead)));        // apsis direction at arrival
    // perigee direction: rotate the arrival direction back by nu about the orbit normal
    var cn = Math.cos(-nu), sn = Math.sin(-nu), w = crs(hn, dirA);
    var rph = unit(add(scl(dirA, cn), scl(w, sn)));
    var vph = unit(crs(hn, rph));
    var vp = Math.sqrt(K.MU_E * (2 / rp - 1 / a));
    return { r: scl(rph, rp), v: scl(vph, vp), tof: tof };
  }

  /** Spacecraft from UI parameters: mass (kg), area (m^2), film key, derate (%), SEP (mN, s, kg, deg).
   *  prm.acMM (mm/s^2) overrides the area (used by tests to fly a given characteristic acceleration). */
  function makeCraft(prm) {
    var film = makeFilm(prm.film, (prm.derate == null ? 100 : prm.derate) / 100);
    var mass = prm.mass, area = prm.area;
    if (prm.acMM != null) area = prm.acMM * 1e-3 * mass / (K.P_SRP * film.front.tot * film.derate);
    var acMM = K.P_SRP * area / mass * film.front.tot * film.derate * 1e3;   // mm/s^2 at launch mass, 1 AU
    var sepOn = !!prm.sepOn && prm.sepThrust > 0;
    return {
      film: film, m0: mass, area: area, acMM: acMM,
      sepThrust: sepOn ? prm.sepThrust * 1e-3 : 0, isp: prm.isp || 1500, mDry: sepOn ? mass - (prm.prop || 0) : mass,
      gimbal: prm.gimbal == null ? 180 : prm.gimbal, sepInShadow: !!prm.sepInShadow, cd: 2.2, minAreaFrac: 0.01,
      stowedArea: 2.5, deployAlt: sepOn ? (prm.deployAlt || 0) : 0,
    };
  }

  var C_HANDOVER = 3.29;     // phase 1 -> phase 2 hand-over: approximate Jacobi constant of the osculating orbit

  function wrapPi(a) { return Math.atan2(Math.sin(a), Math.cos(a)); }

  /** Ascending node (deg) of the lunar orbit on Earth's equator. */
  function moonNode(jd) {
    var m = moonEci(jd), hz = unit(crs(m.r, m.v)), n = crs([0, 0, 1], hz);
    return Math.atan2(n[1], n[0]) / RAD;
  }

  /** Inclination (deg) of an MEE orbit relative to the lunar orbit plane. */
  function relInclination(y, jd) {
    var F = frameAt(jd);
    return Math.acos(clamp(dot(meeNormal(y), F.zh), -1, 1)) / RAD;
  }

  /** Phase 1: orbit-averaged spiral from the departure orbit until the osculating orbit reaches the cislunar
   *  hand-over energy (C ~ 3.29, just above the L1 gateway value 3.19). */
  function* spiral(prm, sc, jd0, f107, raanDeg, msg) {
    var y = departureState(Object.assign({}, prm, { raan: raanDeg }), jd0);
    y.length = 5; y.push(sc.m0);
    var I0 = meeInfo(y);
    var rpSafe = Math.max(K.R_E + Math.min(prm.orbit === "LEO" ? prm.alt : prm.perigee, 35786) - 100, K.R_E + 300);
    if (prm.orbit === "GEO") rpSafe = K.R_E + 20000;
    var opt = { K: 48, rpSafe: rpSafe, f107: (I0.rp - K.R_E) < 2500 ? f107 : null, objective: "apogee" };
    var maxD = (prm.maxYears || 8) * 365.25, n = 0, tDays = 0, status = "ok";
    // step: 1 day above the atmosphere; shorter while drag acts, so strong decay stays resolved
    function stepFor(I) {
      if (opt.f107 == null) return 1.0;
      var h = I.rp - K.R_E;
      return h < 500 ? 0.1 : h < 1300 ? 0.25 : 0.5;                     // 0.1 d matches the study's drag runs
    }
    var p1 = { t: [], y: [], lam: [], C: [], lit: [], dep: [], drag: [] }, lam = Math.atan2(y[2], y[1]);
    while (true) {
      var jd = jd0 + tDays, C = jacobiFromMee(y, jd), Iy = meeInfo(y), dtD = stepFor(Iy);
      var stp = rk4Mee(y, jd, dtD, sc, opt);
      p1.t.push(tDays); p1.y.push(y.slice()); p1.lam.push(lam); p1.C.push(C); p1.lit.push(stp.info.lit);
      p1.dep.push(stp.info.deployed); p1.drag.push(opt.f107 != null);
      if (C <= C_HANDOVER) break;
      if (Iy.rp < K.R_E + 130) { status = "decayed"; break; }
      if (tDays >= maxD) { status = "timeout"; break; }
      var yN = stp.y, IN = meeInfo(yN);
      if (!yN.every(isFinite) || !(yN[0] > 0) || !(IN.e < 0.99) || IN.rp < K.R_E + 130) { status = "decayed"; tDays += dtD; break; }
      var a1 = Math.max(Iy.a, 6500), a2 = Math.max(IN.a, 6500);
      lam += 0.5 * (Math.sqrt(K.MU_E / (a1 * a1 * a1)) + Math.sqrt(K.MU_E / (a2 * a2 * a2))) * dtD * K.DAY;
      y = yN; tDays += dtD; n++;
      if (opt.f107 != null && IN.rp - K.R_E > 2600) opt.f107 = null;
      if (n % 40 === 0) yield { phase: "Earth spiral", frac: Math.min(tDays / maxD, 0.99), msg: msg + ": day " + Math.round(tDays) };
    }
    return { p1: p1, status: status, tDays: tDays, y: y, info: meeInfo(y), rpSafe: rpSafe };
  }

  /** Run a complete mission as a generator (yields progress so a UI can stay responsive). */
  function* runMission(prm) {
    var t0 = Date.now();
    var jd0 = jdFromDate(new Date(prm.launch + "T00:00:00Z"));
    var sc = makeCraft(prm);
    var year0 = 2000 + (jd0 - 2451545.0) / 365.25;
    var f107 = prm.solar === "auto" ? f107ForYear(year0) : ({ low: 70, moderate: 150, high: 230 })[prm.solar];
    var tgt = targetInfo(prm.target);
    var res = { prm: prm, jd0: jd0, craft: { acMM: sc.acMM, sepMM: sc.sepThrust > 0 ? sc.sepThrust / sc.m0 * 1e3 : 0,
                loading: sc.m0 / sc.area * 1e3, film: sc.film.name, m0: sc.m0 }, target: tgt, f107: f107,
                moonIncl: moonInclination(jd0), phases: [], events: [], sc: sc };
    var CHAND = C_HANDOVER, tDays = 0, X0 = null, jdH = jd0;

    // ---------------- phase 1: Earth spiral (RAAN optionally aligned with the lunar orbit plane at hand-over)
    if (prm.orbit !== "TLI") {
      var raan = prm.raan || 0, sp;
      if (prm.raanMode === "auto") {
        var nodeL = moonNode(jd0);
        sp = yield* spiral(prm, sc, jd0, f107, nodeL, "Aligning launch plane");
        if (sp.status === "ok") {
          var drift = wrapPi(sp.info.raan - nodeL * RAD);                      // J2 + sail drift of the node (rad)
          raan = (moonNode(jd0 + sp.tDays) * RAD - drift) / RAD;
        } else raan = nodeL;
      }
      res.raan = ((raan % 360) + 360) % 360;
      sp = yield* spiral(prm, sc, jd0, f107, res.raan, "Spiralling out");
      tDays = sp.tDays;
      res.p1 = sp.p1; res.rpSafe = sp.rpSafe;
      res.phases.push({ key: "spiral", label: "Earth departure spiral", t0: 0, t1: tDays });
      if (sp.status !== "ok") {
        res.status = sp.status; res.tEnd = tDays; res.summary = summarize(res, sc); res.runtimeMs = Date.now() - t0;
        return res;
      }
      var stH = phase1State(res, tDays);
      jdH = jd0 + tDays;
      X0 = eciToRot(stH.r, stH.v, jdH);
      res.handover = { t: tDays, ra: sp.info.ra, rp: sp.info.rp, incMoon: relInclination(sp.y, jdH) };
      res.events.push({ t: tDays, label: "Cislunar gateway energy (C ≈ " + CHAND + ")" });
    } else {
      var tl = tliState(prm, jd0);
      X0 = eciToRot(tl.r, tl.v, jd0);
      res.events.push({ t: 0, label: "Trans-lunar injection" });
      res.p1 = null;
      res.raan = null;
    }

    // ---------------- phase 2: energy matching in the Earth-Moon system
    var m = sc.m0 - (res.p1 ? (sc.m0 - res.p1.y[res.p1.y.length - 1][5]) : 0);
    var ctx = { film: sc.film, acND: sc.acMM / K.A_MM, sepND: sc.sepThrust > 0 ? sc.sepThrust / sc.m0 * 1e3 / K.A_MM : 0,
                m0: sc.m0, m: m, mDry: sc.mDry, gimbal: sc.gimbal, sepInShadow: sc.sepInShadow,
                solarGravity: prm.solarGravity !== false, law: "jacobi", sign: 1 };
    var p2 = { t: [], X: [], n: [], C: [], m: [], sep: [] };
    var Cn = jacobi(X0), Ct = tgt.C;
    ctx.sign = Cn > Ct ? 1 : -1;
    var X = X0.slice(), tN = 0, tStart = tDays, maxND = 420 * K.DAY / K.T, h0 = 2e-3, nStep = 0, rec = 0;
    var mdot = sc.sepThrust > 0 ? sc.sepThrust / (sc.isp * K.G0) : 0;
    var outcome = "matched";
    while (true) {
      var jd2 = jdH + tN * K.T / K.DAY, Cc = jacobi(X);
      if ((Cc - Ct) * ctx.sign <= 0) break;
      var h = stepSize(X, h0);
      var st2 = rk4Rot(X, jd2, h, ctx);
      if (rec++ % 4 === 0) { p2.t.push(tStart + tN * K.T / K.DAY); p2.X.push(X.slice()); p2.n.push(st2.c.n); p2.C.push(Cc); p2.m.push(ctx.m); p2.sep.push(st2.c.sepOn); }
      X = st2.X; tN += h;
      if (st2.c.sepOn) ctx.m = Math.max(ctx.m - mdot * h * K.T, ctx.mDry);
      if (st2.r2 < (K.R_M + 30) / K.L) { outcome = "impact"; break; }
      if (st2.r1 < (K.R_E + 120) / K.L) { outcome = "reentry"; break; }
      if (Math.hypot(X[0], X[1], X[2]) > 3.0) { outcome = "escape"; break; }
      if (tN > maxND) { outcome = "timeout"; break; }
      if (++nStep % 400 === 0) yield { phase: "Energy matching", frac: Math.min(tN / maxND, 0.99), msg: "Matching target energy: day " + Math.round(tStart + tN * K.T / K.DAY) };
    }
    p2.t.push(tStart + tN * K.T / K.DAY); p2.X.push(X.slice()); p2.n.push(p2.n.length ? p2.n[p2.n.length - 1] : [1, 0, 0]); p2.C.push(jacobi(X)); p2.m.push(ctx.m); p2.sep.push(0);
    tDays = tStart + tN * K.T / K.DAY;
    res.p2 = p2;
    res.phases.push({ key: "energy", label: "Energy matching (" + (ctx.sign > 0 ? "raise" : "lower") + " energy)", t0: tStart, t1: tDays });
    if (outcome !== "matched") {
      res.status = outcome; res.tEnd = tDays; res.summary = summarize(res, sc); res.runtimeMs = Date.now() - t0;
      return res;
    }
    res.events.push({ t: tDays, label: "Target energy reached (C = " + Ct.toFixed(3) + ")" });

    // ---------------- phase 3: phasing coast and modelled capture
    var ap = yield* approach(X, jdH + tN * K.T / K.DAY, tDays, ctx, tgt, sc, mdot);
    res.p3 = ap.p3;
    if (ap.outcome !== "captured" && ap.outcome !== "estimated") {
      res.status = ap.outcome; res.tEnd = ap.tEnd;
      res.phases.push({ key: "approach", label: "Approach", t0: tDays, t1: ap.tEnd });
      res.summary = summarize(res, sc); res.runtimeMs = Date.now() - t0; return res;
    }
    res.phases.push({ key: "approach", label: "Phasing coast", t0: tDays, t1: ap.tCap });
    res.phases.push({ key: "trim", label: "Capture and trim (modelled)", t0: ap.tCap, t1: ap.tIns });
    res.p4 = ap.p4;
    tDays = ap.tIns;
    res.insertion = { t: tDays, tCap: ap.tCap, i: ap.iIns, drKm: ap.dr * K.L, dvMs: ap.dv * K.V * 1000, trim: ap.trim,
                      captured: ap.outcome === "captured", date: dateFromJd(jd0 + tDays) };
    res.events.push({ t: ap.tCap, label: "Capture leg begins" });
    res.events.push({ t: tDays, label: "On station: " + tgt.label });
    // ---------------- operations on target
    var opsDays = tgt.period ? Math.max(30, 3 * tgt.period * K.T / K.DAY) : 45;
    res.phases.push({ key: "ops", label: "On station", t0: tDays, t1: tDays + opsDays });
    res.ops = { t0: tDays, i0: ap.iIns, days: opsDays };
    res.tEnd = tDays + opsDays;
    res.status = "ok";
    res.mFinal = ctx.m;
    res.summary = summarize(res, sc);
    res.runtimeMs = Date.now() - t0;
    return res;
  }

  function summarize(res, sc) {
    var s = { status: res.status };
    var ph = {}; res.phases.forEach(function (p) { ph[p.key] = p.t1 - p.t0; });
    s.spiralDays = ph.spiral || 0; s.energyDays = ph.energy || 0; s.approachDays = ph.approach || 0; s.trimDays = ph.trim || 0;
    s.toTargetDays = res.insertion ? res.insertion.t : null;
    s.arrival = res.insertion ? res.insertion.date : null;
    var mEnd = res.mFinal != null ? res.mFinal : (res.p2 ? res.p2.m[res.p2.m.length - 1] : (res.p1 ? res.p1.y[res.p1.y.length - 1][5] : sc.m0));
    s.propUsed = sc.m0 - mEnd;
    s.propLoaded = sc.m0 - sc.mDry;
    return s;
  }

  // ------------------------------------------------------------------ display helpers
  function bracket(arr, t) {
    var lo = 0, hi = arr.length - 1;
    if (t <= arr[0]) return [0, 0, 0];
    if (t >= arr[hi]) return [hi, hi, 0];
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (arr[mid] <= t) lo = mid; else hi = mid; }
    return [lo, hi, (t - arr[lo]) / (arr[hi] - arr[lo])];
  }

  /** Earth-centred inertial state during phase 1 at mission day t (osculating elements + display phase). */
  function phase1State(res, t) {
    var p1 = res.p1, b = bracket(p1.t, t), i = b[0], j = b[1], w = b[2];
    var y = p1.y[i].map(function (v, k) { return v * (1 - w) + p1.y[j][k] * w; });
    var I = meeInfo(y), nMean = Math.sqrt(K.MU_E / (I.a * I.a * I.a));
    var lam = p1.lam[i] + nMean * (t - p1.t[i]) * K.DAY;
    var M = lam - I.lonper, nu = trueFromMean(((M % TWO_PI) + TWO_PI) % TWO_PI, I.e);
    var st = meeToRV(y[0], y[1], y[2], y[3], y[4], nu + I.lonper, K.MU_E);
    return { r: st.r, v: st.v, y: y, info: I };
  }

  /** Osculating ellipse (ECI, km) of the phase-1 orbit at day t. */
  function phase1Ellipse(res, t, nPts) {
    var p1 = res.p1, b = bracket(p1.t, t), y = p1.y[b[0]], pts = [];
    for (var j = 0; j <= nPts; j++) {
      var L = TWO_PI * j / nPts, st = meeToRV(y[0], y[1], y[2], y[3], y[4], L, K.MU_E);
      pts.push(st.r);
    }
    return pts;
  }

  /** Rotating non-dimensional state at mission day t for phases 2-4. */
  function rotState(res, t) {
    function pick(P) {
      var b = bracket(P.t, t), i = b[0], j = b[1], w = b[2];
      return { X: P.X[i].map(function (v, k) { return v * (1 - w) + P.X[j][k] * w; }), n: P.n[i] };
    }
    if (res.p2 && t <= res.p2.t[res.p2.t.length - 1]) return pick(res.p2);
    if (res.p3 && res.p3.t.length && t <= res.p3.t[res.p3.t.length - 1]) return pick(res.p3);
    if (res.p4 && t <= res.p4.t[res.p4.t.length - 1]) {
      var b4 = bracket(res.p4.t, t);
      return { X: res.p4.X[b4[0]].map(function (v, k) { return v * (1 - b4[2]) + res.p4.X[b4[1]][k] * b4[2]; }), n: null, trim: true };
    }
    if (res.insertion && res.ops) return { X: orbitState(res.target, res.ops.i0, (t - res.ops.t0) * K.DAY / K.T), n: null, ops: true };
    if (res.p3 && res.p3.t.length) return pick(res.p3);
    if (res.p2) return pick(res.p2);
    return null;
  }

  /** Display state during the Earth spiral: ECI position/velocity, sail normal from the same apogee-raising law
   *  (with perigee protection) used by the averaged dynamics, illumination and SEP state. */
  function phase1Display(res, t) {
    var st = phase1State(res, t), sc = res.sc, jd = res.jd0 + t, rv = st.r, vv = st.v, y = st.y, I = st.info;
    var sun = sunEci(jd), us = sun.u, s = [-us[0], -us[1], -us[2]];
    var rm = nrm(rv), Rh = scl(rv, 1 / rm), Nh = unit(crs(rv, vv)), Th = crs(Nh, Rh);
    var p = y[0], e = I.e, a = I.a, hmom = Math.sqrt(K.MU_E * p);
    var cnu = clamp((p / rm - 1) / Math.max(e, 1e-9), -1, 1), nu = Math.acos(cnu) * (dot(rv, vv) >= 0 ? 1 : -1);
    var sn = Math.sin(nu), cn = Math.cos(nu);
    var daR = 2 * a * a / hmom * e * sn, daT = 2 * a * a / hmom * p / rm, deR = p * sn / hmom, deT = ((p + rm) * cn + rm * e) / hmom;
    var d = unit(add(scl(Rh, (1 + e) * daR + a * deR), scl(Th, (1 + e) * daT + a * deT)));
    var lam = res.rpSafe ? clamp((res.rpSafe - I.rp) / Math.max(res.rpSafe - (K.R_E + 150), 1), 0, 1) * 4 : 0;
    if (lam > 0) d = unit(add(d, scl(unit(add(scl(Rh, (1 - e) * daR - a * deR), scl(Th, (1 - e) * daT - a * deT))), lam)));
    var proj = dot(rv, us), lit = (proj >= 0 || nrm(sub(rv, scl(us, proj))) >= K.R_E) ? 1 : 0;
    var b = bracket(res.p1.t, t), deployed = res.p1.dep[b[0]], m = y[5];
    var sepOn = sc.sepThrust > 0 && m > sc.mDry + 1e-6 && (lit || sc.sepInShadow);
    var n;
    if (sepOn) n = bestHybrid(sc.film.front, s, d, lit ? sc.acMM : 0, sc.sepThrust / m * 1e3, sc.gimbal, 61).n;
    else n = optimalNormal(sc.film.front, sc.film.table, s, d).n;
    return { r: rv, v: vv, n: n, s: s, d: d, lit: lit, sepOn: sepOn, deployed: deployed, m: m, info: I, jd: jd,
             cone: Math.acos(clamp(Math.abs(dot(n, s)), -1, 1)) / RAD };
  }

  var api = {
    K: K, DATA: DATA, jdFromDate: jdFromDate, dateFromJd: dateFromJd, sunEci: sunEci, moonEci: moonEci, frameAt: frameAt,
    moonInclination: moonInclination, eciToRot: eciToRot, rotToEci: rotToEci, eciToRotPos: eciToRotPos, sunRot: sunRot,
    faceCoeffs: faceCoeffs, steeringTable: steeringTable, optimalNormal: optimalNormal, sailAccel: sailAccel,
    bestHybrid: bestHybrid, makeFilm: makeFilm, f107ForYear: f107ForYear, rhoMean: rhoMean, rhoLst: rhoLst, coeToMee: coeToMee,
    meeToRV: meeToRV, meeInfo: meeInfo, jacobiFromMee: jacobiFromMee, averagedRates: averagedRates, rk4Mee: rk4Mee,
    jacobi: jacobi, rk4Rot: rk4Rot, stepSize: stepSize, targetInfo: targetInfo, makeCraft: makeCraft,
    runMission: runMission, phase1State: phase1State, phase1Ellipse: phase1Ellipse, rotState: rotState,
    phase1Display: phase1Display, orbitState: orbitState, wdist: wdist, moonNode: moonNode, relInclination: relInclination, C_HANDOVER: C_HANDOVER, bracket: bracket, unit: unit, crs: crs, dot: dot, nrm: nrm, sub: sub, add: add, scl: scl,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.SailEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
