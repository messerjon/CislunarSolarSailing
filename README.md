# Cislunar Solar Sailing — DARPA Cattle Run study

Distributed solar sails (conventional and hybrid sail + SEP) operating in cislunar space for situational awareness of
cislunar space and the lunar surface. Objectives, outline and study questions: `CislunarSolarSailing/ObjectivesAndOutline.docx`;
reference library: `CislunarSolarSailing/Resources/`.

## Deliverables

| File | Content |
|---|---|
| `reports/Cislunar_Solar_Sailing_Cattle_Run_Study_Report.pdf` | Complete results report (34 pages): methods, validation, answers to the eight questions, design trades, additional questions, recommendations, references |
| `reports/Cislunar_Solar_Sailing_Cattle_Run_Briefing.pptx` | Complementary 25-slide briefing with native charts, 2-D/3-D figures and speaker notes |
| `figures/` | All 2-D and 3-D figures (16:9 PNG, 200 dpi) |
| `results/` | Machine-readable results (JSON) for every analysis and design point |
| `simulator/` | The simulator package and analyses (NumPy or PyTorch/GPU backend) — see `simulator/README.md` |

## Reproduce

```bash
pip install -r simulator/requirements.txt
python simulator/run_all.py
python reports/build_report.py
```
