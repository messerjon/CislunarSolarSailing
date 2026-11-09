/* Regression tests for interactive/engine.js against the Python simulator (simulator/cislunar_sail).
 * Run:  node interactive/test_engine.js
 * REF holds values computed with the Python package (epoch 2028-01-01T00:00Z) for identical inputs. */
"use strict";
const E = require("./engine.js");
const K = E.K, D2R = Math.PI / 180;
const REF = {"steer_avg_IDEAL":0.4393563350359123,"steer_avg_AL_CP1":0.41823581132194937,"sun":[[0.1749022289679405,-0.9033697645825008,-0.391576657552775],0.9833174434645618],"moon":[[320884.63663350133,-199191.32649804503,-71548.76253671355],[0.5581362903351178,0.7494042958628416,0.41681398646970497]],"rates_sail":{"y0":[12558.679856833745,-0.7021478263189936,8.598830880298272e-17,0.24007875908011603,0.0,111.0],"dy":[0.0007855313772330132,1.6219639377512575e-08,-2.4877090269248713e-08,-8.504381711419335e-10,-1.4532474977991574e-08,0.0],"ac_mm":0.12279417038714308},"rates_hybrid":{"y0":[12558.679856833745,-0.7021478263189936,8.598830880298272e-17,0.24007875908011603,0.0,131.0],"dy":[0.0009041449564260285,5.5375284262086725e-09,-2.588484367880326e-08,-4.4233670200306245e-10,-1.4565569041551083e-08,-1.286398029387333e-06],"ac_mm":0.1040469688013197,"sep_mN":20.0,"isp":1500.0,"gimbal":30.0,"m0":131.0,"prop":6.0,"film":"AL_CP1"},"rates_drag":{"y0":[7078.136929218629,-0.0001,1.2246467991473533e-20,0.8390996311772799,0.0,16.0],"dy":[-2.8402475288657515e-06,-3.100972114966925e-12,5.889106214933634e-10,-3.3964587973989317e-10,-2.0312161024520513e-07,0.0],"area":88.78277450003246},"spirals":[{"label":"LEO1000_ac0.5","rp":7378.137,"ra":7378.137,"inc":28.5,"rp_safe":7278.137,"ac_mm":0.5,"days":491.0},{"label":"GTOr_CRS","rp":7378.137,"ra":42164.137,"inc":27.0,"rp_safe":7278.137,"ac_mm":0.12279417038714308,"days":841.0},{"label":"GEO_ac0.2","rp":42164.137,"ra":42164.137,"inc":0.0,"rp_safe":26378.137,"ac_mm":0.2,"days":343.0}],"steer_IDEAL_90":[35.25,0.3849001066227203],"steer_AL_CP1_60":[21.149999999999995,0.6570289406832406]};
let fails = 0;
function check(name, got, want, tol, rel) {
  const err = rel ? Math.abs(got - want) / Math.abs(want) : Math.abs(got - want);
  const ok = err <= tol;
  if (!ok) fails++;
  console.log((ok ? "ok   " : "FAIL ") + name + ": " + (+got.toPrecision(6)) + " vs " + (+want.toPrecision(6)) + (rel ? "  (rel " : "  (abs ") + err.toExponential(2) + ")");
}
function interpTab(tab, arr, deg) { const u = deg * D2R / tab.dth, i = Math.floor(u), w = u - i; return arr[i] * (1 - w) + arr[Math.min(i + 1, arr.length - 1)] * w; }

// 1. optical model and locally optimal steering
for (const key of ["IDEAL", "AL_CP1"]) {
  const tab = E.makeFilm(key, 1).table; let s = 0; for (const g of tab.g) s += g;
  check(key + " mean g*(theta)", s / tab.g.length, REF["steer_avg_" + key], 2e-3, true);
}
const ti = E.makeFilm("IDEAL", 1).table, tc = E.makeFilm("AL_CP1", 1).table;
check("IDEAL g*(90 deg) (McInnes 0.385)", interpTab(ti, ti.g, 90), REF.steer_IDEAL_90[1], 1e-3);
check("IDEAL alpha*(90 deg) (35.26 deg)", interpTab(ti, ti.al, 90) / D2R, REF.steer_IDEAL_90[0], 0.3);
check("AL_CP1 g*(60 deg)", interpTab(tc, tc.g, 60), REF.steer_AL_CP1_60[1], 1e-3);

// 2. ephemerides
const jd = E.jdFromDate(new Date("2028-01-01T00:00:00Z"));
const su = E.sunEci(jd), mo = E.moonEci(jd);
for (let i = 0; i < 3; i++) check("Sun unit vector [" + i + "]", su.u[i], REF.sun[0][i], 1e-9);
for (let i = 0; i < 3; i++) check("Moon position km [" + i + "]", mo.r[i], REF.moon[0][i], 1e-3);

// 3. orbit-averaged Gauss rates (sail; hybrid with gimballed SEP; drag-aware steering at 700 km)
function rates(name, prm, opt, comps, tol) {
  const r = REF[name], sc = E.makeCraft(prm), dy = E.averagedRates(r.y0.slice(), jd, sc, opt).dy;
  comps.forEach(i => check(name + " d/dt[" + ["p", "f", "g", "h", "k", "m"][i] + "]", dy[i], r.dy[i], tol, true));
}
rates("rates_sail", { mass: 111, acMM: REF.rates_sail.ac_mm, film: "AL_CP1" }, { K: 64, rpSafe: K.R_E + 900 }, [0, 1, 2, 4], 3e-3);
const h = REF.rates_hybrid;
rates("rates_hybrid", { mass: h.m0, acMM: h.ac_mm, film: "AL_CP1", sepOn: true, sepThrust: h.sep_mN, isp: h.isp, prop: h.prop, gimbal: h.gimbal },
      { K: 64, rpSafe: K.R_E + 900, nAlpha: 121 }, [0, 1, 2, 4, 5], 3e-3);
rates("rates_drag", { mass: 16, area: REF.rates_drag.area, film: "AL_PEN_CR" }, { K: 96, rpSafe: K.R_E + 600, f107: 150, nAlpha: 121 }, [0, 2, 4], 3e-3);

// 4. complete spirals to a lunar-distance apogee (326,000 km), as in report Table 4.1
for (const c of REF.spirals) {
  const a = (c.rp + c.ra) / 2, e = Math.max((c.ra - c.rp) / (c.ra + c.rp), 1e-4);
  let y = E.coeToMee(a, e, c.inc * D2R, 0, Math.PI, 0); y.length = 5; y.push(100);
  const sc = E.makeCraft({ mass: 100, acMM: c.ac_mm, film: "AL_CP1" });
  let t = 0;
  while (t < 3650) { y = E.rk4Mee(y, jd + t, 1.0, sc, { K: 64, rpSafe: c.rp_safe }).y; t += 1; if (E.meeInfo(y).ra >= 326000) break; }
  check("spiral days " + c.label, t, c.days, 0.01, true);
}

// 5. CR3BP: Jacobi conservation and periodic-orbit closure without control
for (const key of ["DRO", "L2H", "NRHO"]) {
  const tg = E.targetInfo(key), ctx = { film: E.makeFilm("AL_CP1", 1), acND: 0, sepND: 0, m0: 1, m: 1, mDry: 1, gimbal: 30, solarGravity: false, law: "feather" };
  let X = tg.states[0].slice(), t = 0; const C0 = E.jacobi(X);
  while (t < tg.period - 1e-12) { const hh = Math.min(E.stepSize(X, 5e-4), tg.period - t); X = E.rk4Rot(X, jd, hh, ctx).X; t += hh; }
  check(key + " Jacobi drift over one period", E.jacobi(X) - C0, 0, key === "NRHO" ? 1e-7 : 1e-9);
  const dr = Math.hypot(X[0] - tg.states[0][0], X[1] - tg.states[0][1], X[2] - tg.states[0][2]) * K.L;
  check(key + " closure after one period (km)", dr, 0, key === "DRO" ? 5 : 200);
}

// 6. end-to-end default mission (CR-S, perigee-raised GTO, 2028-01-01, EML2 halo)
const prm = { launch: "2028-01-01", orbit: "GTO", perigee: 1000, apogee: 35786, alt: 1000, inc: 27, raanMode: "auto", mass: 111, area: 1653,
  film: "AL_CP1", derate: 100, sepOn: false, target: "L2H", solar: "auto", solarGravity: true, maxYears: 8 };
const t0 = Date.now(), g = E.runMission(prm); let res; for (;;) { const s = g.next(); if (s.done) { res = s.value; break; } }
check("default mission completes", res.status === "ok" ? 1 : 0, 1, 0);
check("default mission days to station (report: ~841 d spiral + cislunar legs)", res.summary.toTargetDays, 860, 0.1, true);
check("default mission relative inclination at hand-over (deg)", res.handover.incMoon, 0, 12);
console.log("runtime " + (Date.now() - t0) + " ms");

// 7. cislunar legs against the study's transfer matrix (report Table 6.2, CR-S); NRHO -> EML1 is estimated from the
//    reverse leg, as in the study; an itinerary's drawn path has no discontinuities
const study = require("./data.js").study_transfers.sail;
function fly(p) { const gg = E.runMission(p); for (;;) { const s = gg.next(); if (s.done) return s.value; } }
const craft = { launch: "2030-01-01", mass: 111, area: 1653, film: "AL_CP1", derate: 100, sepOn: false, solar: "auto", solarGravity: true };
[["L1H", "L2H"], ["L2H", "DRO"], ["DRO", "NRHO"], ["NRHO", "L1H"], ["L4", "L5"]].forEach(function (od) {
  const r = fly(Object.assign({}, craft, { orbit: "CIS", origin: od[0], stops: [{ key: od[1] }], departureTries: [0, 6] }));
  check(od[0] + " -> " + od[1] + " days vs study median" + (r.summary.legs[0].reversed ? " (reverse-leg estimate)" : ""),
        r.status === "ok" ? r.summary.toTargetDays : 1e9, study[od[0] + ">" + od[1]], 0.25, true);
});
const it = fly(Object.assign({}, craft, { orbit: "CIS", origin: "NRHO", stops: [{ key: "L2H", dwell: 10 }, { key: "L4", dwell: 10 }, { key: "L1H" }] }));
let jumps = 0;
for (let t = it.legs[0].tDep; t < it.tEnd - 0.02; t += 0.01) {
  const a = E.rotState(it, t).X, b = E.rotState(it, t + 0.01).X, c = E.rotState(it, t + 0.001).X;
  const d1 = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]) * K.L, d2 = Math.hypot(c[0] - a[0], c[1] - a[1], c[2] - a[2]) * K.L;
  if (d2 > 200 && d1 / d2 < 3) jumps++;
}
check("three-leg itinerary NRHO -> EML2 -> EML4 -> EML1 completes", it.status === "ok" ? 1 : 0, 1, 0);
check("three-leg itinerary path discontinuities", jumps, 0, 0);
console.log(fails ? fails + " check(s) FAILED" : "all checks passed");
process.exit(fails ? 1 : 0);
