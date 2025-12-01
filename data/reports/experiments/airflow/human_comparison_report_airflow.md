# Human vs AI Comparison Analysis: airflow

**Date:** 2025-11-30 12:13
**Runs Averaged:** 5
**Model:** Gemini 2.5 Flash (Temp 0.1)

## Executive Summary
This report compares the LLM's evaluations against the Human Gold Standard.

### Agreement Metrics
| Metric | Mean | Std Dev | Target |
|---|---|---|---|
| **Checklist Agreement** (Cohen's Kappa) | 0.456 | ±0.091 | > 0.6 |
| **Score Similarity** (MAE) | 0.000 | ±0.000 | < 0.5 |
| **Score Match Rate** (Diff ≤ 1) | 100.0% | - | > 80% |
| **Evidence Correspondence** (IoU) | 0.240 | ±0.026 | > 0.5 |

### Interpretation
- **Checklists:** There is significant disagreement on binary criteria.
- **Scores:** The model's quality ratings are highly similar to human ratings.
