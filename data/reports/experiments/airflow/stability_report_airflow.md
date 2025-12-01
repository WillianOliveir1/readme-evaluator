# Model Consistency Analysis: airflow

**Date:** 2025-11-30 12:13
**Runs:** 5
**Model:** Gemini 2.5 Flash (Temp 0.1)

## Executive Summary
This report analyzes the internal consistency of the LLM when evaluating the same repository multiple times.

### Key Metrics
| Metric | Value | Interpretation |
|---|---|---|
| **Checklist Consistency** (Avg Pairwise Kappa) | 0.687 | Substantial |
| **Score Stability** (Avg Variance) | 0.000 | Lower is better (0 = Perfect) |
| **Evidence Stability** (Avg Pairwise IoU) | 0.464 | Higher is better (1 = Perfect) |

### Detailed Variance by Category
High variance in scores indicates categories where the model is uncertain or sensitive to prompt/sampling noise.
