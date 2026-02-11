"""Generate a comparative quality report from manual and Gemini evaluations.

Reads evaluation JSON files from data/samples/ directories, extracts dimension
scores from ``dimensions_summary``, and produces a Markdown comparison table.

Dependencies: Only uses Python stdlib (json, glob, os, statistics).
"""
import json
import glob
import os
from statistics import mean
from typing import Any, Dict, List, Optional, Set, Tuple


def load_evaluations(directory: str, source_label: str) -> List[Dict[str, Any]]:
    """Load all JSON evaluation files from *directory*."""
    evaluations: list[dict] = []
    files = sorted(glob.glob(os.path.join(directory, "*.json")))
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if "metadata" not in data:
                    data["metadata"] = {}
                data["metadata"]["source"] = source_label
                evaluations.append(data)
        except Exception as e:
            print(f"⚠️ Error reading {f}: {e}")
    return evaluations


def _extract_dimension_score(value: Any) -> Optional[float]:
    """Extract a numeric score from a dimension value.

    Dimensions can be stored as plain numbers or as dicts with ``note``
    or ``score`` keys.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("note", "score"):
            v = value.get(key)
            if isinstance(v, (int, float)):
                return float(v)
    return None


def calculate_averages(
    evaluations: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return per-repo score dicts and the sorted list of dimension names."""
    repo_data: list[dict] = []
    all_dimensions: Set[str] = set()

    # Keys that are global notes, not numeric dimensions
    exclude_keys = {"global_notes", "global_observations"}

    for eval_data in evaluations:
        meta = eval_data.get("metadata", {})
        repo_name_raw = meta.get("repository_name", "Unknown")
        source = meta.get("source", "Unknown")

        dimensions_summary = eval_data.get("dimensions_summary", {})

        target_dims = [k for k in dimensions_summary if k not in exclude_keys]
        all_dimensions.update(target_dims)

        repo_avgs: Dict[str, Any] = {"Repository": repo_name_raw, "Source": source}
        scores: list[float] = []

        for dim in target_dims:
            score = _extract_dimension_score(dimensions_summary[dim])
            if score is not None:
                repo_avgs[dim] = round(score, 2)
                scores.append(score)
            else:
                repo_avgs[dim] = None  # will be ignored in averages

        repo_avgs["Overall"] = round(mean(scores), 2) if scores else 0.0
        repo_data.append(repo_avgs)

    return repo_data, sorted(all_dimensions)


def _build_markdown_table(
    headers: List[str], rows: List[List[str]], align: Optional[List[str]] = None
) -> str:
    """Build a simple Markdown table from headers and rows."""
    if align is None:
        align = ["left"] + ["right"] * (len(headers) - 1)
    sep_map = {"left": ":---", "right": "---:", "center": ":---:"}

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(sep_map.get(a, "---") for a in align) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def generate_markdown_report(
    repo_data: List[Dict[str, Any]], dimensions: List[str], output_file: str
) -> None:
    """Write a Markdown quality comparison report to *output_file*."""
    # Group scores by source and compute mean per dimension
    source_scores: Dict[str, Dict[str, list]] = {}
    for entry in repo_data:
        src = entry["Source"]
        if src not in source_scores:
            source_scores[src] = {d: [] for d in dimensions + ["Overall"]}
        for dim in dimensions + ["Overall"]:
            val = entry.get(dim)
            if val is not None and isinstance(val, (int, float)):
                source_scores[src][dim].append(val)

    # Determine column order (Manual first if present)
    sources = sorted(source_scores.keys())
    if "Manual" in sources:
        sources.remove("Manual")
        sources = ["Manual"] + sources

    headers = ["Dimensão"] + [f"Média {s}" for s in sources]
    rows: list[list[str]] = []

    for dim in dimensions + ["Overall"]:
        row = [dim]
        for src in sources:
            vals = source_scores.get(src, {}).get(dim, [])
            avg = round(mean(vals), 2) if vals else "-"
            row.append(str(avg))
        rows.append(row)

    markdown_table = _build_markdown_table(headers, rows)

    content = f"""# Relatório de Qualidade dos READMEs (Comparativo)

## Metodologia
- **Nota por biblioteca**: Nota direta da seção `dimensions_summary` (avaliação holística).
- **Médias**: Média aritmética das notas de todos os repositórios para cada fonte.
- **Fontes**:
    - `Manual`: Avaliação humana.
    - `Gemini`: Avaliação automatizada pelo modelo.

## Tabela Comparativa de Médias

{markdown_table}
"""

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Report generated at: {output_file}")
    print(markdown_table)


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    manual_eval_dir = os.path.join(base_dir, "data", "samples", "manual-evaluation")
    gemini_eval_dir = os.path.join(base_dir, "data", "samples", "gemini-evaluation")

    output_report = os.path.join(base_dir, "data", "reports", "combined_quality_report.md")

    all_evals: list[dict] = []

    print(f"Reading Manual evaluations from: {manual_eval_dir}")
    all_evals.extend(load_evaluations(manual_eval_dir, "Manual"))

    print(f"Reading Gemini evaluations from: {gemini_eval_dir}")
    all_evals.extend(load_evaluations(gemini_eval_dir, "Gemini"))

    if all_evals:
        data, dims = calculate_averages(all_evals)
        generate_markdown_report(data, dims, output_report)
    else:
        print("⚠️ No evaluation files found.")
