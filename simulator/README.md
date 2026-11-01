# cislunar_sail — mission simulator for distributed solar sails (DARPA Cattle Run study)

An inclusive simulator, built from `CislunarSolarSailing/ObjectivesAndOutline.docx`, that propagates
conventional and hybrid (sail + solar-electric) sailcraft from Earth orbit to and within cislunar space,
and answers the eight study questions. Every batched propagator and steering law runs on **NumPy** or on
**PyTorch** tensors (CPU or CUDA GPU), so thousands of trajectories (Sun phases, launch seasons, design
points, steering commands) are propagated in lock-step.

## Quick start

```bash
pip install -r simulator/requirements.txt          # torch optional (GPU backend)
python simulator/run_all.py                         # all analyses -> results/*.json, figures/*.png
CISLUNAR_BACKEND=torch python simulator/run_all.py  # same on PyTorch (CUDA when available)
python simulator/run_all.py q3_cislunar_transfers   # one analysis
python reports/build_report.py                      # PDF report
NODE_PATH=<node_modules with pptxgenjs react react-dom react-icons sharp> node reports/build_deck.js   # PPTX briefing
```

## Package layout

| Module | Content |
|---|---|
| `cislunar_sail/constants.py` | physical constants, Earth–Moon CR3BP units |
| `cislunar_sail/backend.py` | NumPy / PyTorch array backend (`get_backend('torch')`) |
| `cislunar_sail/sail.py` | non-ideal optical force model (McInnes; Rios-Reyes & Scheeres), film catalogue (Al/CP1, Al/PEN/Cr, Al/Mylar, double-sided, 1 µm CP1, RCD states), locally optimal steering tables, hybrid sail+SEP allocation with gimbal limits and drag-aware steering, membrane temperature |
| `cislunar_sail/environment.py` | Sun/Moon ephemerides (18.6-yr nodal cycle), cylindrical shadows, NRLMSIS 2.x density tables (F10.7 = 70/150/230) |
| `cislunar_sail/earth_orbit.py` | orbit-averaged Gauss equations in modified equinoctial elements (J2, eclipses, drag, SEP mass flow), batched RK4, Moon-centred variant, Cowell integrator with Sun+Moon gravity |
| `cislunar_sail/cr3bp.py` | Earth–Moon CR3BP with rotating Sun line (+ optional solar gravity, BCR4BP), shadows, Lagrange points, differential correction/continuation for Lyapunov, halo (Richardson seed), NRHO, DRO; batched RK4 with Jacobi-constant and custom steering laws |
| `cislunar_sail/designs.py` | heritage sailcraft and study design points (CR-S, CR-H, CR-HR, CR-A); sail-system and SEP mass models |
| `cislunar_sail/plotting.py` | figure style (validated palette, 16:9 figures for slides and report) |
| `analyses/q1..q8, design_trades.py` | one module per study question |

## Validation (see report §2.2)

* steering tables reproduce McInnes' 35.26° / 0.385 and the 0.4393 orbit-average exactly;
* ACS3 180-day SMA rise (Dono 2023: +301/+340 km at 715/900 km) reproduced within 4–30 % depending on solar activity;
* orbit-averaged vs Cowell (Sun+Moon gravity) agree to 0.1 % in apogee after 60 days;
* the 9:2 NRHO (x0 1.0220, z0 −0.1821, vy0 −0.1033, 6.56 d, perilune 3,249 km) matches the Gateway reference.
