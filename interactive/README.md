# Cislunar Sail Explorer — interactive mission model

An in-browser, 3-D model that flies a solar sail (or a sail + solar-electric hybrid) from Earth orbit to a station in
cislunar space. Every control re-flies the whole mission with a JavaScript port of the study simulator, so you can see how
the spacecraft, the propulsion, the destination and **the launch date** change the trajectory and the timeline.

**Open it:** double-click `cislunar_sail_explorer.html` (one self-contained file; it needs an internet connection for
three.js and the web fonts). A hosted copy was published as a claude.ai artifact during the study.

## What you can change

| Group | Controls |
|---|---|
| Launch and destination | launch date (±1-month buttons), departure orbit (GTO with any perigee/apogee, circular LEO, GEO, TLI with aim angle), inclination with launch-site presets, RAAN aligned with the lunar plane or set by hand, destination (EML1 halo, EML2 halo, 9:2 NRHO, 70,000 km DRO, EML4, EML5) |
| Sailcraft | design presets (CR-S, CR-H, CR-HR, CR-A, Solar Cruiser, NEA Scout, ACS3, LightSail 2), mass, sail area, sail film (optical model), optical efficiency |
| Solar-electric propulsion | on/off, thrust, Isp, propellant, gimbal range, thrust in eclipse, sail deploy altitude (sail stays stowed while SEP climbs) |
| Environment | solar activity for drag (solar-cycle model from the launch year, or fixed F10.7), solar gravity on/off |

The view shows the spiral as a family of osculating orbits, the cislunar trajectory coloured by phase, the destination
orbit, the Lagrange points, the Sun direction and the sail attitude. Switch between the inertial frame (lunar orbit plane
horizontal) and the Earth–Moon rotating frame, play or scrub the timeline, and read the HUD, the summary tiles and two
charts (distance from Earth; Jacobi constant on arrival). **Launch-date scan** re-flies twelve monthly launch dates and
plots days to station; select a column to load that date.

## How the mission is flown (`engine.js`)

1. **Earth spiral.** Orbit-averaged Gauss equations in modified equinoctial elements (RK4; 48 samples per orbit) with the
   locally optimal apogee-raising sail attitude, perigee protection, non-ideal film optics, Earth shadow, J2, NRLMSIS drag
   with drag-aware attitude, and gimballed SEP. The spiral ends at the cislunar gateway energy (C ≈ 3.29).
2. **Energy matching.** Earth–Moon CR3BP in the rotating frame, ephemeris Sun line, optional solar gravity (bicircular
   model), Earth and Moon shadows; the sail changes the Jacobi constant as fast as it can until it equals the destination's.
3. **Phasing and capture.** The sail feathers and the spacecraft coasts up to one synodic lap; the best point of the coast
   starts the capture leg. The capture leg is **modelled, not optimised**, as in the study (Q3: T = T_energy + T_coast):
   its length is the study's coast time for the destination or the time to null the velocity mismatch at 35 % of a_c plus
   80 % of the SEP acceleration, whichever is longer. It is drawn dashed.
4. **On station.** The destination orbit is flown for three periods (45 days at L4/L5).

With "Align with lunar plane" the RAAN is chosen by flying the spiral twice: the second flight starts at the lunar node
corrected for the J2 and sail drift of the first, so the spiral arrives in the Moon's orbit plane.

## Validation (`node interactive/test_engine.js`)

The engine is checked against the Python simulator (`simulator/cislunar_sail`) for identical inputs:

* steering tables: McInnes' 35.26° / 0.385 and the 0.4393 orbit average (Al/CP1: 0.4182);
* Sun and Moon ephemerides: identical to 1e-9;
* orbit-averaged rates (sail, gimballed hybrid, drag-aware at 700 km): within 0.06 %;
* complete spirals to a 326,000 km apogee: 491 d (LEO, 0.5 mm/s²), **841 d (CR-S from a perigee-raised GTO, report
  Table 4.1)**, 343 d (GEO, 0.2 mm/s²) — the same day counts as Python;
* CR3BP: Jacobi drift < 1e-9 over a period, DRO / EML2 halo / NRHO closure within 2 km;
* the default mission (CR-S, GTO, 1 Jan 2028, EML2 halo) completes in about 870 days.

## Files

| File | Role |
|---|---|
| `cislunar_sail_explorer.html` | the built, self-contained page |
| `engine.js` | flight-dynamics engine (browser global `SailEngine`, or `require` in Node) |
| `data.js` | periodic orbits, Lagrange points, NRLMSIS tables, film optics and design presets exported from the Python simulator |
| `src/explorer.html`, `src/app.js` | page template and interface (three.js r128 scene, timeline, SVG charts, scan) |
| `export_data.py` | regenerates `data.js` from the simulator |
| `build.py` | inlines `data.js`, `engine.js` and `src/app.js` into the page |
| `test_engine.js` | regression tests against Python reference values |

```bash
python interactive/export_data.py     # only after changing the simulator's orbits, films or designs
python interactive/build.py
node interactive/test_engine.js
```

Limits: the Moon follows the study's circular inclined orbit; shadows are cylindrical; the capture leg is modelled; times
are first-order estimates for concept studies, not flight trajectories.
