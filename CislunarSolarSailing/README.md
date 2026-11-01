# Cislunar Solar-Sail Mission Simulator

Trade-study simulator for the DARPA **Cattle Run** program (DARPA-SN-27-03): distributed, autonomous
solar-sail (and hybrid sail + solar-electric) spacecraft for cislunar situational awareness. It covers
Earth departure through operations in cislunar space. It compares conventional, double-sided,
spin-stabilised, retractable and hybrid (fixed or gimballed SEP) sails, and answers each question in
`ObjectivesAndOutline.docx` with tables and presentation-ready 2D and 3D figures.

## Quick start

```bash
pip install torch numpy scipy pandas matplotlib plotly
python -m cislunar_sail.run_all --quick          # coarse grids, ~8 min on a laptop CPU
python -m cislunar_sail.run_all                  # full study (~1 h CPU; much faster on CUDA)
python -m cislunar_sail.run_all --only q3 --device cuda
python -m pytest tests
```

Outputs:
- `figures/<question>/` holds each chart as a 16:9 PNG (200 dpi, full-bleed for PowerPoint) and an SVG, plus interactive 3D Plotly `.html` for trajectories.
- `results/*.csv` holds every case, and `results/summary.md` gives a direct answer per question.

## What answers each question

| Outline question | Module | Method |
|---|---|---|
| Transit from GTO / GEO / TLI / LEO to cislunar | `analyses/q1_earth_to_cislunar.py` | Orbit-averaged spirals, 5 start orbits × 6 a_c × 5 architectures × 4 Sun geometries |
| Optimal launch inclination | `analyses/q2_launch_inclination.py` | Inclination × RAAN (launch time) sweep; transit time and arrival plane offset from the Moon |
| Transit to/between DRO, LLO, EML1/2/4/5 | `analyses/q3_cislunar_transfers.py` | Minimum-time multiple shooting in the sail-augmented CR3BP; lunar spiral for LLO |
| Lunar pole-sitter requirements | `analyses/q4_pole_sitter.py` | Hover acceleration map; best sail attitude per Sun phase; SEP residual and Xe per year |
| "In irons" region, sail vs hybrid | `analyses/q5_in_irons.py` | Exhaustive control sampling, giving 2D and 3D acceleration envelopes |
| FOV for camera / antenna / array, fixed vs gimballed bus | `analyses/q6_field_of_view.py` | 180 d of L2 halo / DRO with operational sail attitudes |
| Hybrid maneuverability and acceleration | `analyses/q7_maneuverability.py` | Direction-resolved agility; GEO/LEO maneuvers by Lyapunov targeting |
| Lowest acceptable orbit for the DARPA demo | `analyses/q8_lowest_orbit.py` | 30-day drag-vs-SRP runs across altitude × a_c × solar cycle × plane × architecture |
| Electrochromic film vs gimbal momentum management | `analyses/attitude_momentum.py` | Trim authority against CP/CM offset |

## Physics and numerics

- **Sail force**: McInnes non-ideal optical model with separate front and back optics (Al front, Cr back).
  Double-sided sails use Al on both faces. Spacecraft mass scales with sail area: film areal density plus
  boom mass, or spin hardware, retraction mechanism and electrochromic film (`spacecraft.py`). Materials
  and heritage spacecraft are in `spacecraft.py` and `presets.py`.
- **Environment**: Earth J2, analytic Sun and Moon ephemerides (including the 18.6-year lunar node
  cycle), lunar and solar third-body perturbations, Earth and Moon cylindrical eclipses, and atmospheric
  drag at solar minimum, moderate and maximum. Drag is attitude-dependent, with a residual edge-on
  floor of 3.5%.
- **Control**: a candidate-attitude search picks, at every node, the sail normal (Fibonacci sphere plus
  feather and stow states, then refined) that maximises the rate of a guidance objective. SEP uses the
  same search and is gimballed within its cone. One search handles optical sails, drag, SEP gimbals,
  retraction and spin constraints, and it is a single large tensor operation.
- **Orbit-averaged propagation** (`averaged.py`): Gauss equations in modified equinoctial elements are
  averaged over 36 nodes per orbit, which makes multi-year LEO-to-Moon spirals tractable for thousands
  of cases at once.
- **Cislunar transfers** (`shooting.py`): Fourier models of the periodic orbits let departure and
  arrival phases slide continuously. Each solve uses 32 segments with piecewise-constant sail and SEP
  controls, block Jacobians from `torch.func.vmap(jacfwd)`, a batched Levenberg–Marquardt solver, and
  thrust homotopy (8× down to 1×). A time-of-flight grid × Sun phase × multi-start batch runs at once.
  Every solution is re-validated at 4× finer integration.
- **GPU**: all propagators batch over scenarios. Use `--device cuda` (float64). Apple MPS runs only in
  float32 and is fine for exploration, not for final numbers.

## Key assumptions and limitations

- Reference craft: 60 kg bus, a_c = 0.2 mm/s² (about a 44 m CP1 sail). Hybrids add 10 mN / 1500 s SEP
  with 8 kg Xe. With CP1 film and booms, a_c above ~1.5 mm/s² is out of reach at any sail size.
- SEP is solar powered and off in eclipse. Sail degradation, wrinkling, and finite slew rates are not
  modelled. Locally optimal LEO steering needs about 2°/min slews, which large sails may not reach.
- Q1 counts "arrival" as apogee ≥ 300,000 km. Lunar capture into a specific orbit is handled in Q3.
- The CR3BP uses a planar Sun (the 5° lunar inclination is ignored) and circular Earth–Moon motion.
  Q3 transfer times are feasible upper bounds on a discrete TOF grid, not proven optima. LLO times
  chain a DRO transfer with an averaged spiral from a 15,000 km capture orbit.
- The atmosphere uses tabulated density ranges. Swap in NRLMSISE for lifetime-grade predictions.
