# Cislunar Sail Explorer — interactive mission model

An in-browser, 3-D model that flies a solar sail (or a sail + solar-electric hybrid) from Earth orbit into cislunar space
and **between cislunar stations** (EML1/EML2 halos, the 9:2 NRHO, a DRO, EML4, EML5). Every control re-flies the whole mission
with a JavaScript port of the study simulator, so you can see how the spacecraft, the propulsion, the itinerary and **the
launch date** change the trajectory and the timeline.

**Open it:** double-click `cislunar_sail_explorer.html` (one self-contained file; it needs an internet connection for
three.js and the web fonts). A hosted copy was published as a claude.ai artifact during the study.

## What you can change

| Group | Controls |
|---|---|
| Departure | launch (or start) date with ±1-month buttons; start from GTO (any perigee/apogee), circular LEO, GEO, TLI (aim angle) or **already in cislunar space** on any of the six stations; inclination with launch-site presets; RAAN aligned with the lunar plane or set by hand |
| Cislunar itinerary | up to three stops among EML1 halo, EML2 halo, 9:2 NRHO, 70,000 km DRO, EML4 and EML5, with the stay at each intermediate stop |
| Sailcraft | design presets (CR-S, CR-H, CR-HR, CR-A, Solar Cruiser, NEA Scout, ACS3, LightSail 2), mass, sail area, sail film (optical model), optical efficiency |
| Solar-electric propulsion | on/off, thrust, Isp, propellant, gimbal range, thrust in eclipse, sail deploy altitude (sail stays stowed while SEP climbs) |
| Environment | solar activity for drag (solar-cycle model from the launch year, or fixed F10.7), solar gravity on/off |
| Payload and link | bus-fixed EO/IR camera (face, tilt, field of view, target: Moon / lunar south pole / Earth, Sun exclusion, azimuth from the antenna); S-band antenna (fixed to the bus, ±60° or ±90° gimbal, or always on Earth; face, tilt; patch / helix / 0.5 m / 1 m dish; transmit power; data rate; DSN 34 m, 13 m or 5 m ground station) |

The view shows the spiral as a family of osculating orbits, the cislunar trajectory coloured by phase, the destination
orbit, the Lagrange points, the Sun direction and the sail attitude. Switch between the inertial frame (lunar orbit plane
horizontal) and the Earth–Moon rotating frame, play or scrub the timeline, and read the HUD, the summary tiles and two
charts (distance from Earth and from the Moon; Jacobi constant in cislunar space). The **Cislunar legs** range button
zooms the timeline and charts onto the legs and switches to the rotating frame centred on the Moon. The **Cislunar legs**
table lists every transfer (departure, arrival, energy / phasing / capture days, stay). **Cislunar transfer times** flies
all 30 station-to-station transfers for the current sailcraft and start date and shows them next to the study's medians
(report Table 6.2); select a cell to fly that leg. **Launch-date scan** re-flies twelve monthly launch dates and plots days
to the final stop; select a column to load that date.

## Payload fields of view and S-band link (`src/app.js`)

The sail attitude comes from the propulsion law, so bus-fixed instruments point wherever the sail does. Following the
study's Q6 conventions, each instrument sits on the anti-Sun (+n) or Sun (−n) face, tilted from the sail normal; the
membrane blocks ±5° about the sail plane; and the bus rolls freely about the normal (thrust does not depend on roll). With
a fixed antenna the roll aims the antenna's azimuth at Earth and the camera sits at its set azimuth from it; with a gimbal
or ideal pointing the roll aims the camera at its target. The 3-D view draws both fields of view as cones from the sailcraft
plus the line of sight to Earth (red when the link closes, amber when it is open below the selected rate, grey when blocked).

The downlink budget at 2.25 GHz: transmit power − 1 dB line loss + antenna gain − pointing loss 12 (θ/θ3dB)² dB (no link
beyond 1.5 beamwidths, behind the sail or when the Moon occults the Earth) − free-space loss − 0.8 dB atmosphere and
polarization + ground-station G/T + 228.6 dB → C/N0; Eb/N0 required 2.5 dB (BPSK, concatenated coding, BER 1e-6) with a
3 dB margin; rates capped at 10 Mbps for the S-band channel. Example: a 5 W, 12 dBi helix to a DSN 34 m antenna at
lunar distance gives C/N0 ≈ 76 dB-Hz. The panel shows the share of time the Earth is in the beam, the link closes at the
selected rate, the camera sees its target and the Sun is inside the camera's exclusion cone; a capacity chart (pointed at
Earth vs as mounted) with visibility strips; and the full budget at the moment shown. For the default CR-S itinerary the
fixed helix sees Earth about 20 % of the time and a ±60° gimbal about 45 %, in line with the study's Q6 access figures.

## How the mission is flown (`engine.js`)

1. **Earth spiral.** Orbit-averaged Gauss equations in modified equinoctial elements (RK4; 48 samples per orbit) with the
   locally optimal apogee-raising sail attitude, perigee protection, non-ideal film optics, Earth shadow, J2, NRLMSIS drag
   with drag-aware attitude, and gimballed SEP. The spiral ends at the cislunar gateway energy (C ≈ 3.29).
2. **Energy matching.** Earth–Moon CR3BP in the rotating frame, ephemeris Sun line, optional solar gravity (bicircular
   model), Earth and Moon shadows; the sail changes the Jacobi constant as fast as it can until it equals the destination's.
3. **Phasing and capture.** The sail feathers and the spacecraft coasts; the best point of the coast starts the capture
   leg. The capture leg is **modelled, not optimised**: phasing plus capture take the study's natural coast time for the pair
   of regions (Q3: T = T_energy + T_coast; e.g. 21 d EML1↔EML2, 10 d halo↔NRHO, 20 d to/from the DRO, 45 d to/from L4/L5,
   90 d L4↔L5). It is drawn dashed, arcing around the Earth (the long way round when the short way would hit the Moon).
4. **Stays and further legs.** After each stay the next leg leaves the station on the best of five departure days (0, 3, 6,
   9 or 12 days after the planned stay). Two kinds of leg defeat the locally optimal Jacobi law: leaving the NRHO toward a
   halo drives perilune into the Moon, and legs from L4/L5 stall. When a leg fails or takes over 150 days, the engine flies
   the reverse leg and maps it with the CR3BP time-reversal symmetry (x, y, z, vx, vy, vz, t) → (x, −y, z, −vx, vy, −vz, −t),
   the method the study used for those cells; such legs are marked "estimated" and drawn dashed.
5. **On station.** The final stop is flown for three periods (45 days at L4/L5).

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
* the default single-stop mission (CR-S, GTO, 1 Jan 2028, EML2 halo) completes in about 870 days;
* station-to-station legs agree with the study's transfer matrix (report Table 6.2): for a 1 Jan 2030 start, the median
  ratio over all 30 transfers is 1.05 for CR-S and 1.01 for CR-H (e.g. EML1→EML2 30 vs 28 d, EML2→DRO 50 vs 48 d,
  L4→L5 90 vs 90 d; NRHO→EML1 38 vs 35 d as a reverse-leg estimate);
* a three-leg itinerary (NRHO → EML2 → EML4 → EML1) is drawn without discontinuities.

## Files

| File | Role |
|---|---|
| `cislunar_sail_explorer.html` | the built, self-contained page |
| `engine.js` | flight-dynamics engine (browser global `SailEngine`, or `require` in Node) |
| `data.js` | periodic orbits, Lagrange points, NRLMSIS tables, film optics, design presets and the study's transfer matrix exported from the Python simulator and `results/` |
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
