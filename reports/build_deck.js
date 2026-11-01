// Build the companion PowerPoint briefing from results/*.json and figures/*.png.
//   NODE_PATH=<dir with pptxgenjs, react, react-dom, react-icons, sharp>/node_modules node reports/build_deck.js
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const ROOT = path.resolve(__dirname, "..");
const FIG = path.join(ROOT, "figures");
const RES = path.join(ROOT, "results");
const OUT = path.join(ROOT, "reports", "Cislunar_Solar_Sailing_Cattle_Run_Briefing.pptx");
const SKILL_THEME = process.env.APPLY_THEME_JS;

const J = (n) => JSON.parse(fs.readFileSync(path.join(RES, `${n}.json`), "utf8"));
const q1 = J("q1_transit"), q2 = J("q2_inclination"), q3 = J("q3_cislunar_transfers"), q4 = J("q4_pole_sitter");
const q5 = J("q5_in_irons"), q6 = J("q6_fov"), q7 = J("q7_hybrid"), q8 = J("q8_lowest_orbit");
const dt = J("design_trades"), D = J("designs");

const THEME = {
  name: "Cattle Run Sail",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: { dk1: "0B0B0B", lt1: "FFFFFF", dk2: "0D2340", lt2: "F3F5F9", accent1: "2A78D6", accent2: "EB6834",
            accent3: "1BAF7A", accent4: "EDA100", accent5: "6250D6", accent6: "E34948", hlink: "2A78D6", folHlink: "6250D6" },
};
const HEX = { ink: "0B0B0B", ink2: "52514E", muted: "898781", grid: "E1E0D9", navy: "0D2340", blue: "2A78D6",
              orange: "EB6834", aqua: "1BAF7A", yellow: "EDA100", violet: "6250D6", red: "E34948", tint: "EEF4FC" };

const f0 = (x) => (x === null || x === undefined ? "n/a" : Math.round(x).toLocaleString("en-US"));
const f1 = (x) => (x === null || x === undefined ? "n/a" : x.toFixed(1));
const f2 = (x) => (x === null || x === undefined ? "n/a" : x.toFixed(2));
const f3 = (x) => (x === null || x === undefined ? "n/a" : x.toFixed(3));
const pct = (x) => `${Math.round(100 * x)} %`;

function pngSize(p) {
  const b = fs.readFileSync(p);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

async function icon(name) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color: "#FFFFFF", size: 256 }));
  const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";            // 13.333 x 7.5 in
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "Cislunar Solar Sailing for DARPA Cattle Run - Simulation Study Briefing";
  pres.subject = "Mission simulation results";
  pres.author = "Cattle Run cislunar solar-sail study";
  const C = pres.SchemeColor;

  // ---------------------------------------------------------------- layouts
  pres.defineSlideMaster({
    title: "TITLE", background: { color: C.text2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.0, w: 11.7, h: 1.9, fontSize: 44, bold: true, align: "left",
                                  color: C.background1, valign: "bottom", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.05, w: 11.0, h: 1.2, fontSize: 20,
                                  color: "CDE2FB", valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "SECTION", background: { color: C.text2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.6, w: 11.7, h: 1.2, fontSize: 40, bold: true, align: "left",
                                  color: C.background1, valign: "bottom", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.95, w: 11.7, h: 1.2, fontSize: 20,
                                  color: "CDE2FB", valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
    slideNumber: { x: 12.4, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: "9EC5F4" },
  });
  pres.defineSlideMaster({
    title: "CONTENT", background: { color: C.background1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.3, w: 12.1, h: 0.75, fontSize: 32, bold: true, align: "left",
                                  color: C.text2, valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "Cattle Run cislunar solar-sail study  |  simulation results  |  1 November 2026",
                options: { x: 0.6, y: 7.0, w: 9.0, h: 0.3, fontSize: 10, color: HEX.muted, margin: 0 } } },
    ],
    slideNumber: { x: 12.4, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: HEX.muted },
  });

  const icons = {};
  for (const n of ["FaRocket", "FaGlobeAmericas", "FaRoute", "FaSatellite", "FaSun", "FaCamera", "FaExpandArrowsAlt",
                   "FaWind", "FaCogs", "FaLightbulb", "FaQuestionCircle", "FaCubes", "FaCheck", "FaFlask", "FaBalanceScale"]) {
    icons[n] = await icon(n);
  }

  let sec = "";
  function content(title, kicker, sectionTitle) {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: sectionTitle || sec });
    s.addText(title, { placeholder: "title" });
    if (kicker) {
      s.addText(kicker, { x: 0.6, y: 1.07, w: 12.1, h: 0.5, fontSize: 17, color: C.text2, italic: true, margin: 0,
                          isTextBox: true, objectName: "kicker" });
    }
    return s;
  }
  function badge(s, iconName, x, y, size, color) {
    s.addShape(pres.shapes.OVAL, { x, y, w: size, h: size, fill: { color }, line: { color, width: 0 }, objectName: "badge" });
    const pad = size * 0.24;
    s.addImage({ data: icons[iconName], x: x + pad, y: y + pad, w: size - 2 * pad, h: size - 2 * pad });
  }
  function img(s, name, x, y, w, maxH) {
    const p = path.join(FIG, name);
    const { w: pw, h: ph } = pngSize(p);
    let W = w, H = w * ph / pw;
    if (maxH && H > maxH) { H = maxH; W = H * pw / ph; }
    s.addImage({ path: p, x, y, w: W, h: H, altText: name.replace(/_/g, " ").replace(".png", "") });
    return { w: W, h: H };
  }
  function stat(s, value, label, x, y, w, color) {
    s.addText([{ text: value, options: { fontSize: 34, bold: true, color: color || C.text2, breakLine: true } },
               { text: label, options: { fontSize: 13, color: HEX.ink2 } }],
              { x, y, w, h: 1.25, margin: 0, valign: "top", isTextBox: true, objectName: "stat" });
  }
  function bullets(s, items, x, y, w, h, fs) {
    s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 6 } })),
              { x, y, w, h, fontSize: fs || 15, color: HEX.ink, valign: "top", margin: 0.02, isTextBox: true });
  }
  function card(s, x, y, w, h, title, body, color) {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: "F3F5F9" }, line: { color: "E1E0D9", width: 0.75 },
                                                rectRadius: 0.08, objectName: "card" });
    s.addText([{ text: title, options: { fontSize: 19, bold: true, color: color || C.text2, breakLine: true } },
               { text: body, options: { fontSize: 15.5, color: HEX.ink } }],
              { x: x + 0.18, y: y + 0.12, w: w - 0.36, h: h - 0.24, valign: "top", margin: 0, isTextBox: true });
  }
  const axisStyle = {
    catAxisLabelColor: HEX.ink2, valAxisLabelColor: HEX.ink2, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 11, valGridLine: { color: HEX.grid, size: 0.75 },
    catGridLine: { style: "none" }, legendFontFace: "+mn-lt", legendFontSize: 11, legendColor: HEX.ink2,
    titleFontFace: "+mn-lt", titleFontSize: 14, titleColor: HEX.ink, showTitle: true, catAxisLineShow: true,
    valAxisTitleFontFace: "+mn-lt", catAxisTitleFontFace: "+mn-lt", valAxisTitleFontSize: 11, catAxisTitleFontSize: 11,
    valAxisTitleColor: HEX.ink2, catAxisTitleColor: HEX.ink2,
  };

  // ---------------------------------------------------------------- data shortcuts
  const td = q1.transit_days;
  const LEO = "LEO 1,000 km (28.5 deg)", GTO = "GTO, perigee raised to 1,000 km", GEO = "GEO (35,786 km)";
  const names = q3.matrix_names, ms = q3.matrix_sail_days, mh = q3.matrix_hybrid_days;
  const M = (m, a, b) => m[names.indexOf(a)][names.indexOf(b)];
  const core = ["DRO", "EML1", "EML2", "NRHO"];
  const rng = (m, A, Bs) => { const v = []; A.forEach(a => Bs.forEach(b => { if (a !== b) v.push(M(m, a, b)); })); return [Math.min(...v), Math.max(...v)]; };
  const coreS = rng(ms, core, core), coreH = rng(mh, core, core), l45S = rng(ms, core, ["EML4"]), lloS = rng(ms, ["LLO (LRO)"], core.concat(["EML4"]));
  const lloH = rng(mh, ["LLO (LRO)"], core.concat(["EML4"]));
  const cfg = Object.fromEntries(q5.configs.map(c => [c.config, c]));
  const op = q5.operational_in_irons;
  const acc = q6.access["DRO 70k / maneuver"];
  const env = Object.fromEntries(q7.envelopes.map(e => [e.design, e]));
  const rs = q7.reachable_stats, rr = q7.response_days;
  const be = q8.break_even_alt_km, mg = q8.alt_drag_loss_le_25pct_km, fc = q8.f_criterion;
  const b60 = q4.budgets["below pole 60,000 km"], b100 = q4.budgets["below pole 100,000 km"];

  // ================================================================ 1 title
  pres.addSection({ title: "Overview" }); sec = "Overview";
  let s = pres.addSlide({ masterName: "TITLE", sectionTitle: sec });
  s.addText("Cislunar Solar Sailing for DARPA Cattle Run", { placeholder: "title" });
  s.addText("Simulation study results: transit, launch geometry, cislunar transfers, pole-sitting, 'in-irons' limits, " +
            "field of view, hybrid agility and the demonstration orbit", { placeholder: "body" });
  s.addText("Proposal-team briefing  |  DARPA-SN-27-03 Proposers Day 10 Nov 2026  |  1 November 2026",
            { x: 0.8, y: 6.55, w: 11.5, h: 0.4, fontSize: 13, color: "9EC5F4", margin: 0, isTextBox: true });
  s.addNotes("Purpose: brief the proposal team on what the mission simulator says about solar-sail and hybrid sail/SEP concepts for " +
             "DARPA Cattle Run. Companion to the PDF results report, which contains methods, tables and references.");

  // ================================================================ 2 bottom line
  s = content("Bottom line", "A hybrid sail flown first at ~1,000 km, then launched toward the lunar plane, meets every Cattle Run objective");
  stat(s, `${f1(td[GEO]["0.123"] / 365.25)} yr`, "GEO to lunar distance with a\nSolar Cruiser-class sail (CR-S)", 0.6, 1.85, 2.9, C.accent1);
  stat(s, `${f1(cfg["Al/CP1 sail (CR-S)"].nogo_half_angle_deg_tau0)} deg`, "sunward cone where a sail\nproduces no thrust at all", 3.65, 1.85, 2.9, C.accent2);
  stat(s, `${f1(rs["CR-H hybrid"]["7"].max_disp_km / rs["CR-S sail"]["7"].max_disp_km)}x`, "7-day reach of the hybrid\nvs the sail (from a DRO)", 6.7, 1.85, 2.9, C.accent3);
  stat(s, "~1,000 km", "lowest robust demo orbit\n(drag < 25 % of sail thrust)", 9.75, 1.85, 3.0, C.accent5);
  bullets(s, [
    "Baseline a hybrid: Solar Cruiser-class sail + 20 mN two-axis gimballed SEP (CR-H) removes the in-irons region and decouples pointing and power from thrust for 20 kg.",
    "Demonstrate below GEO at ~1,000 km dawn-dusk SSO (no eclipses, ~20 % faster raising); from a 550 km rideshare, climb with the sail stowed (18 days, 2 kg).",
    "Launch cislunar elements toward the lunar plane (Cape Canaveral 28.5 deg / 27 deg GTO); DRO, NRHO and L1/L2 halos are weeks apart, L4/L5 two months.",
    "Do not baseline a lunar pole-sitter: it needs 1.2-1.8 mm/s^2 continuously - an SEP mission. Use paired NRHO spacecraft for polar coverage.",
  ], 0.6, 3.45, 12.1, 3.3, 16);
  s.addNotes("Four numbers carry the story: transit takes years from Earth orbit with near-term sails; physics forbids sunward thrust over a " +
             "35 deg cone; a small gimballed SEP more than doubles agility; and drag sets the demo floor near 1,000 km for a robust test.");

  // ================================================================ 3 questions
  s = content("Eight questions, one simulator", "Each study question maps to an analysis module, a results file and figures in this deck");
  const qs = [["FaRocket", "Q1  Transit time from GTO, GEO, TLI, LEO"], ["FaGlobeAmericas", "Q2  Optimal launch inclination"],
              ["FaRoute", "Q3  Transfers among DRO, LLO, EML1/2/4/5"], ["FaSatellite", "Q4  Lunar pole-sitter requirements"],
              ["FaSun", "Q5  'In irons': sail vs hybrid"], ["FaCamera", "Q6  Field of view, fixed vs gimballed bus"],
              ["FaExpandArrowsAlt", "Q7  Hybrid manoeuvrability & acceleration"], ["FaWind", "Q8  Lowest acceptable demo orbit"]];
  const qcol = [C.accent1, C.accent1, C.accent1, C.accent5, C.accent2, C.accent5, C.accent3, C.accent2];
  qs.forEach(([ic, t], i) => {
    const col = i < 4 ? 0 : 1, row = i % 4;
    const x = 0.7 + col * 6.2, y = 1.9 + row * 1.2;
    badge(s, ic, x, y, 0.8, qcol[i]);
    s.addText(t, { x: x + 1.0, y: y + 0.08, w: 5.0, h: 0.64, fontSize: 18, color: HEX.ink, valign: "middle", margin: 0, isTextBox: true });
  });
  s.addNotes("The objectives document asked for an inclusive simulator from Earth to and within cislunar space, transit times, conventional vs hybrid " +
             "comparison, GPU use through PyTorch, pre-processed mission profiles and 2-D/3-D plots. All eight questions are answered with it.");

  // ================================================================ 4 simulator
  s = content("Simulator: GPU-batched, validated against flight data", "NumPy or PyTorch (CUDA) backend - thousands of trajectories propagated in lock-step");
  const mods = [["sail", "optical force model, materials, optimal steering, hybrid allocation"],
                ["environment", "Sun/Moon ephemerides, shadows, NRLMSIS drag tables"],
                ["earth_orbit", "orbit-averaged spirals (MEE), J2, eclipses, drag, SEP"],
                ["cr3bp", "Earth-Moon CR3BP + rotating Sun line, halos, NRHO, DRO"],
                ["designs", "mass model calibrated on ACS3 and Solar Cruiser"],
                ["analyses", "q1-q8 + design trades; run_all.py rebuilds everything"]];
  mods.forEach(([m, t], i) => {
    const y = 1.85 + i * 0.82;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 6.2, h: 0.68, fill: { color: "F3F5F9" }, line: { color: "E1E0D9", width: 0.75 }, rectRadius: 0.06 });
    s.addText([{ text: m + "  ", options: { bold: true, color: C.text2 } }, { text: t, options: { color: HEX.ink } }],
              { x: 0.8, y, w: 5.9, h: 0.68, fontSize: 14, valign: "middle", margin: 0, isTextBox: true });
  });
  const vrows = [["Benchmark", "Reference", "Simulator"],
                 ["Orbit-averaged thrust fraction", "0.4393 (McInnes)", "0.4393"],
                 ["ACS3 SMA rise, 900 km, 180 d", "+340 km (Dono)", "+353 km"],
                 ["Min. ACS3 raising altitude", "~691 km (Wilkie)", "647 km"],
                 ["Averaged vs Cowell (Sun+Moon), 60 d", "-", "0.1 % in apogee"],
                 ["9:2 NRHO period / perilune", "6.56 d / ~3,250 km", "6.56 d / 3,249 km"],
                 ["Lunar pole hover at 60,000 km", "Ozimek contours", "1.77 mm/s^2"]];
  s.addTable(vrows.map((r, i) => r.map(c => ({ text: c, options: { bold: i === 0, color: i === 0 ? C.text2 : HEX.ink,
                                                                   fill: { color: i === 0 ? "E8EEF7" : "FFFFFF" } } }))),
             { x: 7.1, y: 1.85, w: 5.65, colW: [2.45, 1.7, 1.5], fontSize: 12, border: { type: "solid", pt: 0.5, color: "E1E0D9" },
               rowH: 0.42, margin: 0.05 });
  s.addNotes("Validation: the steering tables reproduce McInnes exactly; the averaged LEO model matches the ACS3 flight-dynamics predictions within " +
             "4-30 % depending on the solar-activity assumption; averaged vs full Cowell differs by 0.1 % in apogee after 60 days; the NRHO matches Gateway's reference orbit.");

  // ================================================================ 5 design points
  s = content("Design points", "Heritage sails anchor the range; the study uses a Solar Cruiser-derived sail (CR-S), its hybrid (CR-H) and a far-term sail (CR-A)");
  const dkeys = ["LS2", "ACS3", "NEAS", "SC", "CR-S", "CR-H", "CR-A"];
  const drows = [["Design", "Mass (kg)", "Area (m^2)", "a_c (mm/s^2)", "SEP"]].concat(dkeys.map(k => {
    const d = D[k];
    return [d.name.replace(" (gimballed SEP)", "").replace("Cattle Run ", "CR "), f0(d.mass_kg), f0(d.area_m2), f3(d.a_c_mm_s2),
            d.sep_thrust_mN ? `${d.sep_thrust_mN} mN, ${d.isp_s} s, +/-${d.gimbal_deg} deg` : "-"];
  }));
  s.addTable(drows.map((r, i) => r.map(c => ({ text: String(c), options: { bold: i === 0, color: i === 0 ? C.text2 : HEX.ink,
                                                                           fill: { color: i === 0 ? "E8EEF7" : (i >= 5 ? "F7F9FC" : "FFFFFF") } } }))),
             { x: 0.6, y: 1.8, w: 5.75, colW: [1.95, 0.75, 0.75, 0.85, 1.45], fontSize: 12, rowH: 0.5,
               border: { type: "solid", pt: 0.5, color: "E1E0D9" }, margin: 0.05 });
  img(s, "dt_ac_vs_area.png", 6.55, 1.85, 6.2, 4.9);
  s.addNotes("a_c is quoted for the real film (about 9 % below the ideal 2PA/m formula). CR-H trades 18 % more mass for SEP agility; CR-A shows what 1 um film and 45 m booms buy.");

  // ================================================================ section: getting there
  pres.addSection({ title: "Getting there" }); sec = "Getting there";
  s = pres.addSlide({ masterName: "SECTION", sectionTitle: sec });
  s.addText("Getting there", { placeholder: "title" });
  s.addText("Q1 transit time  |  Q2 launch inclination  |  Q3 transfers between cislunar orbits", { placeholder: "body" });

  // ================================================================ Q1 chart
  s = content("Q1  Transit time scales as 1 / a_c", "Near-term sails need 1.3-5.5 years to climb from Earth orbit to lunar distance - start high");
  badge(s, "FaRocket", 12.05, 0.33, 0.68, C.accent1);
  const acs = ["0.07", "0.1", "0.123", "0.15", "0.2", "0.3", "0.5", "1"];
  s.addChart(pres.charts.LINE, [
    { name: "LEO 1,000 km", labels: acs.map(a => (a === "1" ? "1.0" : a)), values: acs.map(a => td[LEO][a]) },
    { name: "Raised GTO (1,000 km perigee)", labels: acs.map(a => (a === "1" ? "1.0" : a)), values: acs.map(a => td[GTO][a]) },
    { name: "GEO", labels: acs.map(a => (a === "1" ? "1.0" : a)), values: acs.map(a => td[GEO][a]) },
  ], Object.assign({}, axisStyle, {
    x: 0.6, y: 1.75, w: 7.6, h: 5.05, chartColors: [HEX.blue, HEX.orange, HEX.aqua], lineSize: 2, lineDataSymbol: "circle",
    lineDataSymbolSize: 7, valAxisLogScaleBase: 10, title: "Days to lunar-distance apogee vs a_c (mm/s^2)",
    showLegend: true, legendPos: "b", valAxisTitle: "days (log scale)", showValAxisTitle: true,
    catAxisTitle: "characteristic acceleration a_c (mm/s^2)", showCatAxisTitle: true,
  }));
  stat(s, `${f0(td[GEO]["0.123"])} d`, "GEO to lunar distance (CR-S)", 8.6, 1.85, 4.1, C.accent3);
  stat(s, `${f0(td[GTO]["0.123"])} d`, "raised GTO (1,000 x 35,786 km)", 8.6, 3.05, 4.1, C.accent2);
  stat(s, `${f0(td[LEO]["0.123"])} d`, "1,000 km LEO, 28.5 deg", 8.6, 4.25, 4.1, C.accent1);
  s.addText(`TLI: lunar distance in ${f1(q1.tli_ballistic_days_to_326000km)} d, then ~${f0(q3.tli_capture.sail.median_d)} d sail capture ` +
            `(~${f0(q3.tli_capture.hybrid.median_d)} d hybrid).`,
            { x: 8.6, y: 5.6, w: 4.15, h: 1.0, fontSize: 14, color: HEX.ink, margin: 0, isTextBox: true, valign: "top" });
  s.addNotes(`Medians over six launch seasons; arrival = osculating apogee at 326,000 km. CR-H with 6 kg of propellant: ${f0(td[GEO]["CR-H (6 kg prop)"])} d from GEO; ` +
             `with unlimited SEP ${f0(td[GEO]["CR-H unlimited prop"])} d but ${f0(td[GEO]["CR-H unlimited prop used kg"])} kg of propellant. ` +
             `A standard 250 km-perigee GTO is survivable only with edge-on perigee passes; a ${f0(q1.gto_standard.perigee_raise_dv_m_s)} m/s perigee raise is the robust choice.`);

  // ================================================================ Q1 3-D
  s = content("Q1  Spiralling out from GTO", "Apogee grows ~1 % per day; the arrival orbit reaches the Moon's distance after ~2.3 years");
  img(s, "q1_spiral_3d.png", 0.6, 1.7, 7.4, 5.2);
  bullets(s, [
    `Sail deployment in a standard 250 km-perigee GTO is survivable only if the sail stays edge-on through every 10 km/s perigee pass; then sunlight lifts perigee to ~${f0(q1.gto_standard.moderate.rp_final_km[1])} km in 120 days.`,
    `Robust option: raise perigee to 1,000 km first (${f0(q1.gto_standard.perigee_raise_dv_m_s)} m/s from the upper stage, a kick motor or SEP).`,
    `Hybrid SEP is least valuable here: with unlimited propellant CR-H cuts GTO transit to ${f0(td[GTO]["CR-H unlimited prop"])} d but burns ${f0(td[GTO]["CR-H unlimited prop used kg"])} kg.`,
    "Model check: averaged vs full Cowell with Sun and Moon gravity agree within 0.1 % in apogee after 60 days.",
  ], 8.2, 1.85, 4.55, 4.9, 14);
  s.addNotes("The figure shows osculating orbits light (early) to dark (late), with the arrival orbit highlighted in orange and the Moon's orbit in grey.");

  // ================================================================ Q2
  s = content("Q2  Launch toward the lunar plane: ~28.5 deg", "Spiral time is insensitive to inclination (+/-3 %); the cost is the plane mismatch at arrival");
  badge(s, "FaGlobeAmericas", 12.05, 0.33, 0.68, C.accent1);
  const incl = q2.inclinations.map(i => String(i));
  const plane = q2.total_days.map((t, i) => t - q2.raise_days_median[i]);
  s.addChart(pres.charts.LINE, [
    { name: "Spiral to lunar distance", labels: incl, values: q2.raise_days_median },
    { name: "Residual plane change", labels: incl, values: plane },
    { name: "Total", labels: incl, values: q2.total_days },
  ], Object.assign({}, axisStyle, {
    x: 0.6, y: 1.75, w: 7.4, h: 5.05, chartColors: [HEX.blue, HEX.orange, HEX.ink], lineSize: 2, lineDataSymbol: "circle",
    lineDataSymbolSize: 7, title: "CR-S days from raised GTO vs launch inclination (deg)", showLegend: true, legendPos: "b",
    valAxisMinVal: 0, valAxisMaxVal: 1000, valAxisTitle: "days", showValAxisTitle: true,
    catAxisTitle: "launch inclination (deg)", showCatAxisTitle: true,
  }));
  img(s, "q2_lunar_plane_cycle.png", 8.25, 1.8, 4.5, 2.4);
  bullets(s, [
    `Lunar plane: ${f1(q2.lunar_inclination_2028)} deg (2028) -> ${f1(q2.lunar_inclination_2030)} deg (2030) -> ${f1(q2.lunar_inclination_2034)} deg (2034).`,
    `Optimum ${q2.optimal_inclination_deg}-28.5 deg; SSO launches add ~${f0(q2.total_days[q2.total_days.length - 1] - Math.min(...q2.total_days))} d.`,
    "The sail itself drifts the plane toward the ecliptic: a 28.5 deg launch arrives near 21 deg.",
    "LEO demo: dawn-dusk SSO is ~20 % better than noon-midnight (no eclipses).",
  ], 8.25, 4.35, 4.5, 2.5, 13);
  s.addNotes(`Plane change near apogee costs ~${f1(q2.plane_change["10"].aligned)} d/deg when apsides align with the node line, ` +
             `~${f0(q2.plane_change["10"].perpendicular)} d/deg when perpendicular. RAAN can be phased by J2 (~0.3 deg/day in GTO).`);

  // ================================================================ Q3 matrix
  s = content("Q3  Cislunar slots are weeks apart; LLO is a year away", "Energy-change ensembles (12 start x 8 Sun phases) + natural coasts, CR3BP with rotating Sun line");
  badge(s, "FaRoute", 12.05, 0.33, 0.68, C.accent1);
  img(s, "q3_transfer_matrix.png", 0.6, 1.7, 8.6, 5.15);
  stat(s, `${f0(coreS[0])}-${f0(coreS[1])} d`, `halo / NRHO / DRO legs (sail)\nhybrid ${f0(coreH[0])}-${f0(coreH[1])} d`, 9.5, 1.85, 3.25, C.accent1);
  stat(s, `${f0(l45S[0])}-${f0(l45S[1])} d`, "to L4 / L5 sentinel slots\n(drift-dominated)", 9.5, 3.35, 3.25, C.accent3);
  stat(s, `${f0(lloS[0])}-${f0(lloS[1])} d`, `any leg touching 100 km LLO\nhybrid ${f0(lloH[0])}-${f0(lloH[1])} d`, 9.5, 4.85, 3.25, C.accent2);
  s.addNotes(`Energy-change rates near these orbits: ~0.003-0.008 per day in Jacobi constant for a 0.12 mm/s^2 sail. L1-L2 coast computed along the halo unstable manifold ` +
             `(${f0(q3.l1_l2_manifold_tof.median_d)} d). Lowering energy from the NRHO drives perilune into the Moon; those legs use the reverse transfer. ` +
             `LLO legs: ${f0(q3.lunar_spiral.sail.up_days)} d lunar spiral for the sail, ${f0(q3.lunar_spiral.hybrid.up_days)} d hybrid (needs ~0.6 km/s of SEP).`);

  // ================================================================ Q3 catalog
  s = content("Q3  Destination orbits for a cislunar constellation", "Computed by differential correction and continuation; the 9:2 NRHO matches Gateway's reference orbit");
  img(s, "q3_orbit_catalog_3d.png", 0.6, 1.65, 7.6, 5.25);
  const cat = q3.catalog;
  const crow = [["Orbit", "Jacobi C", "Period (d)", "Stability"]].concat(["EML1 halo", "EML2 halo", "NRHO 9:2", "DRO 70k", "EML4", "LLO 100 km polar"].map(k =>
    [k, cat[k].C.toFixed(4), cat[k].period_d ? f1(cat[k].period_d) : "-", cat[k].stability ? f1(cat[k].stability) : "-"]));
  s.addTable(crow.map((r, i) => r.map(c => ({ text: String(c), options: { bold: i === 0, color: i === 0 ? C.text2 : HEX.ink,
                                                                          fill: { color: i === 0 ? "E8EEF7" : "FFFFFF" } } }))),
             { x: 8.45, y: 1.85, w: 4.3, colW: [1.6, 0.95, 0.95, 0.8], fontSize: 12, rowH: 0.45,
               border: { type: "solid", pt: 0.5, color: "E1E0D9" }, margin: 0.05 });
  s.addText("Lower C = higher energy. The DRO is neutrally stable (index 1.0) - an ideal parking slot needing almost no station keeping.",
            { x: 8.45, y: 5.25, w: 4.3, h: 1.4, fontSize: 13, color: HEX.ink, margin: 0, isTextBox: true, valign: "top" });
  s.addNotes("Halo orbits are strongly unstable (stability index in the hundreds) and need regular small corrections - a natural job for the sail; the NRHO is mildly unstable (1.3) and the DRO neutrally stable. LLO here is a 100 km polar orbit representing LRO.");

  // ================================================================ section: operating there
  pres.addSection({ title: "Operating there" }); sec = "Operating there";
  s = pres.addSlide({ masterName: "SECTION", sectionTitle: sec });
  s.addText("Operating there", { placeholder: "title" });
  s.addText("Q4 lunar pole-sitter  |  Q5 in-irons limits  |  Q6 field of view  |  Q7 hybrid manoeuvrability", { placeholder: "body" });

  // ================================================================ Q4
  s = content("Q4  A lunar pole-sitter is an SEP mission", "Hovering below the south pole needs 1.2-1.8 mm/s^2 continuously; the sail pushes the wrong way");
  badge(s, "FaSatellite", 12.05, 0.33, 0.68, C.accent5);
  img(s, "q4_hover_requirement.png", 0.6, 1.7, 7.3, 5.2);
  stat(s, `${f2(b100.a_req_mm_s2)}-${f2(b60.a_req_mm_s2)}`, "mm/s^2 required, 100,000-60,000 km\nbelow the pole (10-14x CR-S a_c)", 8.25, 1.8, 4.5, C.accent5);
  stat(s, `${f0(b100.by_ac["0.000"].dv_km_s_per_yr)}-${f0(b60.by_ac["0.000"].dv_km_s_per_yr)} km/s`, `SEP delta-v per year (${pct(b100.by_ac["0.000"].prop_frac_1yr_isp3000)}-${pct(b60.by_ac["0.000"].prop_frac_1yr_isp3000)}\nof mass per year at Isp 3,000 s)`, 8.25, 3.1, 4.5, C.accent2);
  bullets(s, [
    "A sail alone never holds a static hover (0 % of the month); even a 1.7 mm/s^2 sail removes only 10-40 % of the SEP demand.",
    "Sail-only coverage orbits need 0.58-1.7 mm/s^2 (Ozimek, Wawrzyniak): 5-14x CR-S.",
    "Recommendation: polar coverage from two NRHO / L2-halo spacecraft.",
  ], 8.25, 4.45, 4.5, 2.4, 13);
  s.addNotes("The requirement is dominated by lunar gravity along the polar axis, while sail thrust lies near the Earth-Moon plane. Grebow et al. needed a 500 kg spacecraft " +
             "with 450 kg of propellant for 387-554 days of pole-sitting, consistent with these numbers.");

  // ================================================================ Q5
  s = content("Q5  Sails are 'in irons' within ~35 deg of the Sun", "A real film can tilt its force at most 50-56 deg from sunlight; any hybrid removes the dead zone");
  badge(s, "FaSun", 12.05, 0.33, 0.68, C.accent2);
  img(s, "q5_force_bubbles.png", 0.6, 1.7, 7.0, 3.45);
  const k5 = ["Ideal sail", "Al/CP1 sail (CR-S)", "Al/PEN/Cr sail (ACS3)"];
  const cats5 = ["Orbit raising", "NRHO energy", "DRO energy", "Station keeping"];
  const keys5 = ["orbit_raising", "NRHO_jacobi", "DRO_jacobi", "isotropic_SK"];
  s.addChart(pres.charts.BAR, k5.map(k => ({ name: k.replace(" sail", ""), labels: cats5, values: keys5.map(q => Math.round(100 * op[k][q])) })),
             Object.assign({}, axisStyle, {
               x: 7.85, y: 1.7, w: 4.9, h: 3.6, barDir: "col", barGrouping: "clustered", chartColors: ["898781", HEX.blue, HEX.orange],
               title: "% of time in irons (< 5 % of a_c)", showLegend: true, legendPos: "b", showValue: true, dataLabelPosition: "outEnd",
               dataLabelFontSize: 10, dataLabelColor: HEX.ink2, dataLabelFontFace: "+mn-lt", valAxisMinVal: 0, valAxisMaxVal: 40,
               barGapWidthPct: 60,
             }));
  stat(s, `${f1(cfg["Al/CP1 sail (CR-S)"].nogo_half_angle_deg_tau0)} deg`, "no-thrust cone (Al/CP1);\n50.8 deg below 5 % of a_c", 0.6, 5.4, 3.3, C.accent2);
  stat(s, `${f2(cfg["Hybrid, +/-30 deg gimbal (CR-H)"].sunward_capability_over_ac)} a_c`, "sunward thrust of CR-H\n(+/-30 deg gimbal)", 4.1, 5.4, 3.3, C.accent3);
  s.addText("All hybrid variants: 0 % in irons. Even a fixed SEP thruster gives " + f2(cfg["Hybrid, fixed SEP (0 deg)"].sunward_capability_over_ac) + " a_c toward the Sun.",
            { x: 7.85, y: 5.5, w: 4.9, h: 1.1, fontSize: 14, color: HEX.ink, margin: 0, isTextBox: true, valign: "top" });
  s.addNotes("Left: force bubbles of ideal and real films and the Al/CP1 no-go cone; right panel of the figure: useful acceleration vs direction. " +
             "In operations the sail is in irons 28 % of the time during Earth-orbit raising and 18 % for arbitrary station-keeping corrections.");

  // ================================================================ Q6
  s = content("Q6  Gimbal the bus: Earth access 3 % -> 39 %", "Propulsion owns the sail attitude, so body-fixed instruments point wherever thrust demands");
  badge(s, "FaCamera", 12.05, 0.33, 0.68, C.accent5);
  const cfg6 = ["Fixed, boresight on sail normal", "Fixed, best tilt (design-time)", "Gimbal +/-30 deg", "Gimbal +/-60 deg", "Gimbal +/-90 deg (hemisphere)"];
  const tg6 = ["Earth (HGA, 10 deg beam)", "Lunar south pole (camera, 10 deg)", "SDA field, anti-Sun hemisphere (camera, 15 deg)", "Solar array power (fraction of max)"];
  s.addChart(pres.charts.BAR, cfg6.map(c => ({ name: c.replace(" (design-time)", "").replace(" (hemisphere)", ""), labels: ["Earth link", "Lunar south pole", "SDA, anti-Sun", "Array power"],
                                               values: tg6.map(t => Math.round(100 * acc[t][c])) })),
             Object.assign({}, axisStyle, {
               x: 0.6, y: 1.7, w: 8.2, h: 5.15, barDir: "col", barGrouping: "clustered",
               chartColors: ["898781", HEX.blue, HEX.aqua, HEX.orange, HEX.violet], title: "% of time in view / % of peak array power (DRO operations)",
               showLegend: true, legendPos: "b", showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 9, dataLabelColor: HEX.ink2,
               dataLabelFontFace: "+mn-lt", valAxisMinVal: 0, valAxisMaxVal: 110, barGapWidthPct: 45,
             }));
  img(s, "q6_fov_schematic_3d.png", 9.0, 1.7, 3.75, 3.6);
  bullets(s, [
    "Fixed arrays average 75 % of peak power and fall to zero when the sail feathers; +/-30 deg recovers 94 %.",
    "The sail blocks half the sky: carry antennas on both faces.",
  ], 9.0, 5.35, 3.75, 1.55, 12.5);
  s.addNotes("Four months of DRO operations with random manoeuvre demands every 12 hours; free roll about the sail normal assumed; membrane blocks +/-5 deg about its plane.");

  // ================================================================ Q7 reach
  s = content("Q7  The hybrid reaches every direction", "Constant-direction steering ensembles from a 70,000 km DRO (Sun initially at +x)");
  badge(s, "FaExpandArrowsAlt", 12.05, 0.33, 0.68, C.accent3);
  img(s, "q7_reachable_2d.png", 0.6, 1.65, 8.6, 4.0);
  stat(s, `${f0(rs["CR-H hybrid"]["7"].max_disp_km / 1000)}k km`, `7-day reach, hybrid\n(sail ${f0(rs["CR-S sail"]["7"].max_disp_km / 1000)}k km, lopsided)`, 9.5, 1.8, 3.25, C.accent3);
  stat(s, `${f2(rr["CR-H"]["10_at_0"])}-${f2(rr["CR-H"]["10_at_180"])} d`, `10 m/s in any direction (hybrid)\nsail ${f2(rr["CR-S"]["10_at_0"])}-${f2(rr["CR-S"]["10_at_90"])} d, never sunward`, 9.5, 3.15, 3.25, C.accent1);
  stat(s, `${f3(env["CR-H"].isotropic_mean)}`, `mm/s^2 mean in all directions\n(sail ${f3(env["CR-S"].isotropic_mean)})`, 9.5, 4.5, 3.25, C.accent2);
  s.addText(`Hybrid acceleration: ${f3(env["CR-H"].away_from_sun)} away from the Sun, ${f3(env["CR-H"].perpendicular)} perpendicular, ${f3(env["CR-H"].toward_sun)} toward it (mm/s^2).`,
            { x: 0.6, y: 5.85, w: 8.6, h: 0.9, fontSize: 14, color: HEX.ink, margin: 0, isTextBox: true, valign: "top" });
  s.addNotes("Each dot is the end point of a constant-direction steering command (400 directions on a sphere). The sail cannot push toward the Sun at all in the first days; Coriolis effects and the rotating Sun line open some sunward displacement after a week. The hybrid's SEP closes the gap immediately.");

  // ================================================================ Q7 mass
  s = content("Q7  When does a sail pay for itself?", "Sails win for long, manoeuvre-intensive missions - the Cattle Run constellation use case");
  img(s, "q7_mass_trade.png", 0.6, 1.7, 6.2, 3.8);
  img(s, "q7_response_time.png", 6.95, 1.7, 5.8, 3.8);
  bullets(s, [
    `Sail system ~${f0(q7.mass_trade.notes.sail_system_kg)} kg: sail-only beats SEP-only after ~${f1(q7.mass_trade.notes.sail_beats_sep_above_km_s)} km/s of cumulative manoeuvring, the hybrid after ~${f1(q7.mass_trade.notes.hybrid_beats_sep_above_km_s)} km/s.`,
    "Use SEP tactically (in-irons gaps, fast response, fine station keeping) and let the sail supply the bulk delta-v: CR-H's 6 kg then lasts for years.",
  ], 0.6, 5.65, 12.15, 1.25, 14);
  s.addNotes("Mass trade: 60 kg bus; 1,653 m^2 sail system ~33 kg; SEP dry ~12.5 kg (20 mN, Isp 1,500 s); hybrid SEP supplies only the in-irons share (18 %) of the delta-v. Right: days to deliver 10 or 50 m/s versus manoeuvre direction.");

  // ================================================================ section: demonstrating
  pres.addSection({ title: "Demonstrating it" }); sec = "Demonstrating it";
  s = pres.addSlide({ masterName: "SECTION", sectionTitle: sec });
  s.addText("Demonstrating it", { placeholder: "title" });
  s.addText("Q8 lowest acceptable orbit for the below-GEO demonstrator", { placeholder: "body" });

  // ================================================================ Q8 chart
  s = content("Q8  Drag sets the floor at 650-800 km", "Drag and sail thrust both scale with area/mass: no sail is big enough to fly below the break-even altitude");
  badge(s, "FaWind", 12.05, 0.33, 0.68, C.accent2);
  const nd = q8.sma_sweep_no_drag["No drag"]["SSO dawn-dusk"];
  const i0 = nd.alt_km.indexOf(700);
  const alts = nd.alt_km.slice(i0).map(a => String(a));
  const sw = q8["sma_sweep_CR-S"];
  s.addChart(pres.charts.LINE, [
    { name: "No drag", labels: alts, values: nd.rate_km_day.slice(i0) },
    { name: "Solar minimum", labels: alts, values: sw["Solar minimum (F10.7=70)"]["SSO dawn-dusk"].rate_km_day.slice(i0) },
    { name: "Moderate", labels: alts, values: sw["Moderate (F10.7=150)"]["SSO dawn-dusk"].rate_km_day.slice(i0) },
    { name: "Solar maximum", labels: alts, values: sw["Solar maximum (F10.7=230)"]["SSO dawn-dusk"].rate_km_day.slice(i0) },
  ], Object.assign({}, axisStyle, {
    x: 0.6, y: 1.75, w: 7.4, h: 5.05, chartColors: ["898781", HEX.aqua, HEX.blue, HEX.orange], lineSize: 2, lineDataSymbol: "none",
    title: "CR-S net SMA change in a dawn-dusk SSO (km/day, 30-day average)", showLegend: true, legendPos: "b",
    valAxisMinVal: -4, valAxisMaxVal: 9, valAxisTitle: "km/day", showValAxisTitle: true, catAxisTitle: "altitude (km)", showCatAxisTitle: true,
  }));
  const qrows = [["Criterion (km)", "Min", "Mod.", "Max"],
                 ["Drag = thrust (orbit mean)", f0(fc["Solar minimum (F10.7=70)"].h_mean), f0(fc["Moderate (F10.7=150)"].h_mean), f0(fc["Solar maximum (F10.7=230)"].h_mean)],
                 ["Break-even, dawn-dusk", f0(be["Solar minimum (F10.7=70)"]["SSO dawn-dusk"]), f0(be["Moderate (F10.7=150)"]["SSO dawn-dusk"]), f0(be["Solar maximum (F10.7=230)"]["SSO dawn-dusk"])],
                 ["Break-even, noon-midnight", f0(be["Solar minimum (F10.7=70)"]["SSO noon-midnight"]), f0(be["Moderate (F10.7=150)"]["SSO noon-midnight"]), f0(be["Solar maximum (F10.7=230)"]["SSO noon-midnight"])],
                 ["Drag <= 25 %, dawn-dusk", f0(mg["Solar minimum (F10.7=70)"]["SSO dawn-dusk"]), f0(mg["Moderate (F10.7=150)"]["SSO dawn-dusk"]), f0(mg["Solar maximum (F10.7=230)"]["SSO dawn-dusk"])],
                 ["Drag <= 25 %, noon-midnight", f0(mg["Solar minimum (F10.7=70)"]["SSO noon-midnight"]), f0(mg["Moderate (F10.7=150)"]["SSO noon-midnight"]), f0(mg["Solar maximum (F10.7=230)"]["SSO noon-midnight"])]];
  s.addTable(qrows.map((r, i) => r.map(c => ({ text: String(c), options: { bold: i === 0, color: i === 0 ? C.text2 : HEX.ink,
                                                                           fill: { color: i === 0 ? "E8EEF7" : "FFFFFF" } } }))),
             { x: 8.3, y: 1.85, w: 4.45, colW: [2.35, 0.7, 0.7, 0.7], fontSize: 12, rowH: 0.48,
               border: { type: "solid", pt: 0.5, color: "E1E0D9" }, margin: 0.05 });
  s.addText("Cycle 25 is declining in 2028: plan for F10.7 ~ 150 with excursions above 200.",
            { x: 8.3, y: 5.0, w: 4.45, h: 0.9, fontSize: 13, color: HEX.ink, italic: true, margin: 0, isTextBox: true, valign: "top" });
  s.addNotes("Mengali-Quarta criterion f = rho v^2 / P_ideal <= 2/C_D gives the orbit-mean altitudes; the simulated break-even uses drag-aware locally optimal steering with " +
             "NRLMSIS densities and a 1 % edge-on residual area.");

  // ================================================================ Q8 recommendation
  s = content("Q8  Lowest acceptable orbit: ~1,000 km dawn-dusk SSO", "Robust at solar maximum, 400x less atomic oxygen than 550 km, ~220 km of raising per month for CR-S");
  img(s, "q8_gravity_gradient.png", 0.6, 1.7, 6.6, 3.9);
  const envt = Object.fromEntries(q8.environment.map(e => [e.alt_km, e]));
  const erows = [["Altitude (km)", "AO erosion, ram face (um/yr)", "Passive decay, CR-S"]].concat([550, 700, 800, 900, 1000].map(h =>
    [String(h), (envt[h].AO_fluence_mod * 3e-20).toFixed(h >= 900 ? 2 : 1), `${f0(365.25 * q8.decay_years[String(h)]["CR-S deployed (yr)"])} d`]));
  s.addTable(erows.map((r, i) => r.map(c => ({ text: String(c), options: { bold: i === 0, color: i === 0 ? C.text2 : HEX.ink,
                                                                           fill: { color: i === 0 ? "E8EEF7" : "FFFFFF" } } }))),
             { x: 7.5, y: 1.8, w: 5.25, colW: [1.35, 2.15, 1.75], fontSize: 12, rowH: 0.42,
               border: { type: "solid", pt: 0.5, color: "E1E0D9" }, margin: 0.05 });
  bullets(s, [
    `Full-size 1,653 m^2 sail: gravity gradient exceeds 10 cm CM-trim authority below ~${f0(q8.gravity_gradient["CR-S"].h_gg_equals_amt_km)} km - size wheels/magnetorquers or demo a 100-500 m^2 sail.`,
    `550 km rideshare: CR-H climbs to 1,000 km with the sail stowed in ${f0(q8.sep_climb_550_to_1000km.moderate.days)} days using ${f1(q8.sep_climb_550_to_1000km.moderate.propellant_kg)} kg.`,
  ], 7.5, 4.55, 5.25, 2.3, 13);
  s.addNotes("AO erosion assumes a ram-facing polyimide surface at 3e-24 cm^3/atom with moderate solar activity. Passive decay assumes the sail deployed, 50 % average projected area, F10.7 = 150. A large sail is also an excellent de-orbit device.");
  s.addText("Left: gravity-gradient torque (worst-case attitude) vs sail trim authority.",
            { x: 0.6, y: 5.75, w: 6.6, h: 0.5, fontSize: 12, color: HEX.ink2, italic: true, margin: 0, isTextBox: true });

  // ================================================================ design options
  pres.addSection({ title: "Design and next steps" }); sec = "Design and next steps";
  s = content("Design options scorecard", "Every option in the outline was simulated; recommendations in the right-hand column");
  badge(s, "FaCubes", 12.05, 0.33, 0.68, C.accent1);
  const rf = dt.reefing, rc = dt.rcd;
  const orows = [["Option", "Quantified benefit", "Cost / risk", "Call"],
    ["Hybrid sail + SEP", "No in-irons; 2-4x agility; SEP climb from low rideshare", "+20 kg (18 %), propellant", "Adopt"],
    ["Gimballed SEP (+/-30 deg)", `Sunward ${f2(cfg["Hybrid, +/-30 deg gimbal (CR-H)"].sunward_capability_over_ac)} vs ${f2(cfg["Hybrid, fixed SEP (0 deg)"].sunward_capability_over_ac)} a_c; CM trim 4e-3 N m`, "Gimbal mass, plume limits", "Adopt"],
    ["Retractable sail", `Throttle: ${pct(rf.reefable_sail)} vs ${pct(rf.fixed_area_sail)} of demands met exactly; drag/debris avoidance`, "+30 % deployer mass, wear", "Ground-mature, fly on demo"],
    ["Electrochromic RCD (2 % area)", `${rc.pitch_2pct_at_0.toExponential(1)} N m pitch/yaw, wheel-free roll`, "Authority nulls near 60 deg incidence", "Adopt for roll"],
    ["Double-sided film", `Efficiency ${f3(dt.efficiency["Al/CP1/Al double-sided 2.5 um"])} vs ${f3(dt.efficiency["Al/CP1 2.5 um (NEA Scout, Solar Cruiser)"])}`, `Runs ${f0(dt.thermal_peak_C["Al/CP1/Al double-sided 2.5 um"])} C at normal incidence`, "Keep single-sided"],
    ["Spin / yo-yo deployment", `~${f0(dt.sail_system_mass_rigid.SC.total - dt.sail_system_mass_spin.SC.total)} kg lighter sail system`, "Too slow for LEO steering (needs ~0.06 deg/s)", "Rigid booms"]];
  s.addTable(orows.map((r, i) => r.map((c, j) => ({ text: String(c), options: { bold: i === 0 || j === 3, color: i === 0 ? C.text2 : (j === 3 ? C.accent1 : HEX.ink),
                                                                                fill: { color: i === 0 ? "E8EEF7" : "FFFFFF" } } }))),
             { x: 0.6, y: 1.8, w: 12.15, colW: [2.6, 4.65, 3.1, 1.8], fontSize: 13, rowH: 0.62,
               border: { type: "solid", pt: 0.5, color: "E1E0D9" }, margin: 0.06 });
  s.addNotes(`A 5 cm CM-CP offset on the 1,653 m^2 sail accumulates ${f0(rc.momentum_per_day_5cm_Nms)} N m s per day, so continuous propellant-free trim (mass shift, RCDs) is mandatory.`);

  // ================================================================ momentum management
  s = content("Propellant-free attitude and momentum control", `A 5 cm CM-CP offset builds ${f0(rc.momentum_per_day_5cm_Nms)} N m s of momentum per day on the full-size sail - trim continuously`);
  img(s, "dt_momentum_actuators.png", 0.6, 1.7, 7.4, 5.1);
  img(s, "dt_reefing.png", 8.2, 1.75, 4.55, 2.4);
  bullets(s, [
    "Bus gimbal (+/-30 deg, 1 m arm) gives ~3x the authority of a 10 cm mass translator.",
    "RCD panels at 2-5 % of area match the disturbance at low incidence and meet Solar Cruiser's roll requirement.",
    "Partial retraction throttles the sail: 5x more control demands met exactly.",
  ], 8.2, 4.35, 4.55, 2.5, 13);
  s.addNotes("RCD = reflectivity-control device (electrochromic / PDLC film). Differential switching of tip panels gives pitch/yaw torque; canted panels give roll torque. Authority nulls near 60 deg incidence for the assumed optical states, matching Heaton's 'loss of control authority at high SIA'.");

  // ================================================================ additional questions
  s = content("Questions the proposal should also answer", "Surfaced by the analyses; ordered by priority for the Cattle Run proposal");
  badge(s, "FaQuestionCircle", 12.05, 0.33, 0.68, C.accent5);
  const aq = ["Film and coating life at the demo altitude and through the radiation belts",
              "Collision and conjunction risk of a 1,653 m^2 sail at ~1,000 km; screening with continuous thrust",
              "Orbit determination with attitude-dependent SRP; force-model calibration in flight",
              "Autonomy architecture: safe feathering, momentum management, fault recovery",
              "LEO gravity-gradient and aerodynamic torques for a large sail",
              "Sail billow, wrinkles and boom thermal deflection effects on force and torque",
              "Survival of lunar and Earth eclipses (thermal snap, boom contraction loads)",
              "Constellation deployment and phasing from a single launch",
              "Antenna placement when the sail blocks half the sky",
              "SEP plume impingement on the film and resulting gimbal limits",
              "Station-keeping cost in the full ephemeris model with solar gravity",
              "End of life: drag-sail disposal in LEO, heliocentric escape from cislunar space"];
  const half = Math.ceil(aq.length / 2);
  [aq.slice(0, half), aq.slice(half)].forEach((col, ci) => {
    s.addText(col.map((t, i) => ({ text: `${String.fromCharCode(65 + ci * half + i)}.  ${t}`, options: { breakLine: i < col.length - 1, paraSpaceAfter: 9 } })),
              { x: 0.6 + ci * 6.2, y: 1.85, w: 5.95, h: 4.95, fontSize: 14.5, color: HEX.ink, valign: "top", margin: 0, isTextBox: true });
  });
  s.addNotes("The objectives document asked the study to 'find other questions that should be addressed'. These twelve came out of the analyses; A, B and E bear directly on the Phase 1 demonstrator.");

  // ================================================================ recommendations
  s = content("Recommended concept and next steps", "A hybrid sailcraft, demonstrated at ~1,000 km and deployed to DRO, NRHO, L1/L2 and L4/L5 slots");
  badge(s, "FaLightbulb", 12.05, 0.33, 0.68, C.accent4);
  card(s, 0.6, 1.85, 5.95, 2.4, "Architecture (CR-H class)", "Solar Cruiser-heritage 1,653 m^2 single-sided CP1 sail on rigid booms; RCD roll control; two-axis gimballed bus (+/-30-60 deg) with a 15-25 mN Hall thruster, arrays and instruments; antennas on both faces.", C.accent1);
  card(s, 6.8, 1.85, 5.95, 2.4, "Phase 1 demonstrator", "~1,000 km dawn-dusk SSO (or 550 km rideshare + 18-day SEP climb). Success: measured a_c within 10 %, ~5-7 km/day raising, autonomous steering and momentum management, safe feathering.", C.accent2);
  card(s, 0.6, 4.45, 5.95, 2.4, "Phase 2 cislunar operations", "Launch toward the lunar plane (28.5 deg) to GTO/GEO or TLI; slots in DRO, NRHO and L1/L2 halos with L4/L5 sentinels; polar coverage by paired NRHO spacecraft.", C.accent3);
  s.addNotes("The concept follows directly from the eight answers: hybrid for omnidirectional agility, ~1,000 km for a convincing demo, 28.5 deg launches for the lunar plane, and NRHO pairs rather than a pole-sitter.");
  card(s, 6.8, 4.45, 5.95, 2.4, "Simulator next steps", "Trajectory optimisation for transfers, full-ephemeris / BCR4BP station keeping with a sail-aware controller, slew-limited attitude dynamics, sail-shape uncertainty, GPU Monte Carlo of autonomy faults.", C.accent5);

  // ================================================================ backup
  s = content("Backup: assumptions and reproduction", "All results are reproducible from the repository");
  bullets(s, [
    "Flat sail, nominal optics, no degradation (real performance typically 5-15 % lower)",
    "Instantaneous attitude changes in trajectory runs; agility treated separately",
    "Averaged Earth-orbit dynamics without lunisolar perturbations (0.1 % after 60 days)",
    "CR3BP with rotating Sun line; transfer times = energy change + natural coast (+/-30 %)",
    "NRLMSIS 2.x equatorial densities, C_D 2.2, 1 % edge-on residual area",
    "Mass model calibrated on ACS3 and Solar Cruiser; SEP sizing after Ceriotti & McInnes",
  ], 0.6, 1.85, 6.4, 4.9, 14);
  const cmd = [["Command", "Effect"], ["python simulator/run_all.py", "All analyses -> results/*.json, figures/*.png"],
               ["CISLUNAR_BACKEND=torch python simulator/run_all.py", "Same on PyTorch (CUDA GPU when present)"],
               ["python reports/build_report.py", "Rebuild the PDF report"], ["node reports/build_deck.js", "Rebuild this deck"]];
  s.addTable(cmd.map((r, i) => r.map((c, j) => ({ text: c, options: Object.assign({ bold: i === 0, color: i === 0 ? C.text2 : HEX.ink,
                                                                 fill: { color: i === 0 ? "E8EEF7" : "FFFFFF" } }, (i > 0 && j === 0) ? { fontFace: "Courier New" } : {}) }))),
             { x: 7.25, y: 1.85, w: 5.5, colW: [3.2, 2.3], fontSize: 11, rowH: 0.55, border: { type: "solid", pt: 0.5, color: "E1E0D9" }, margin: 0.05 });

  await pres.writeFile({ fileName: OUT });
  if (SKILL_THEME) {
    const { applyTheme } = require(SKILL_THEME);
    await applyTheme(OUT, THEME);
  }
  console.log(OUT);
}

main().catch((e) => { console.error(e); process.exit(1); });
