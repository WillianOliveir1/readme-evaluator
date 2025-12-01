# Human vs AI Comparison Analysis: scipy

**Date:** 2025-11-30 12:40
**Runs Averaged:** 5
**Model:** Gemini 2.5 Flash (Temp 0.1)

## Executive Summary
This report compares the LLM's evaluations against the Human Gold Standard.

### Agreement Metrics
| Metric | Mean | Std Dev | Target |
|---|---|---|---|
| **Checklist Agreement** (Cohen's Kappa) | 0.448 | ±0.041 | > 0.6 |
| **Score Similarity** (MAE) | 4.000 | ±0.000 | < 0.5 |
| **Score Match Rate** (Diff ≤ 1) | 0.0% | - | > 80% |
| **Evidence Correspondence** (IoU) | 0.132 | ±0.012 | > 0.5 |

### Interpretation
- **Checklists:** There is significant disagreement on binary criteria.
- **Scores:** The model tends to rate differently than the human evaluator.
