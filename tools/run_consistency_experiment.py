import argparse
import json
import os
import sys
import time
import numpy as np
from pathlib import Path
from datetime import datetime

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.download.download import ReadmeDownloader
from backend.evaluate.extractor import extract_json_from_readme
from backend.config import SCHEMA_PATH, DEFAULT_MODEL
from tools.analysis.consistency_analysis import (
    flatten_checklist, flatten_scores, flatten_evidences,
    calculate_kappa, calculate_mae, calculate_token_overlap
)

def run_evaluation(readme_text, model_name, run_index, output_dir):
    """Run a single evaluation and save the result."""
    print(f"--- Starting Run {run_index} ---")
    
    max_retries = 3
    retry_delay = 60
    
    for attempt in range(max_retries):
        result = extract_json_from_readme(
            readme_text=readme_text,
            schema_path=SCHEMA_PATH,
            model=model_name,
            temperature=0.1 # Deterministic setting from article
        )
        
        if result.success and result.parsed:
            timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
            filename = f"run_{run_index}_{timestamp}.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result.parsed, f, indent=2, ensure_ascii=False)
                
            print(f"Run {run_index} completed. Saved to {filepath}")
            return result.parsed
        
        # Check if it's a rate limit error to retry
        error_msg = "; ".join(result.recovery_suggestions) if result.recovery_suggestions else "Unknown error"
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            print(f"Run {run_index} failed (Attempt {attempt+1}/{max_retries}) due to Rate Limit. Waiting {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 1.5 # Exponential backoff
        else:
            print(f"Run {run_index} failed: {error_msg}")
            return None # Don't retry on non-rate-limit errors
            
    print(f"Run {run_index} failed after {max_retries} attempts.")
    return None

def analyze_stability(runs_data):
    """Calculate stability metrics across N runs."""
    n = len(runs_data)
    if n < 2:
        return None

    # 1. Checklist Stability (Average Pairwise Kappa)
    kappas = []
    for i in range(n):
        for j in range(i + 1, n):
            list1 = flatten_checklist(runs_data[i])
            list2 = flatten_checklist(runs_data[j])
            k = calculate_kappa(list1, list2)
            kappas.append(k)
    avg_kappa = np.mean(kappas) if kappas else 0.0

    # 2. Score Stability (Average Variance)
    # Group scores by ID
    score_map = {}
    for run in runs_data:
        scores = flatten_scores(run)
        for item in scores:
            if item['id'] not in score_map:
                score_map[item['id']] = []
            score_map[item['id']].append(item['value'])
    
    variances = []
    for val_list in score_map.values():
        if len(val_list) > 1:
            variances.append(np.var(val_list))
    avg_variance = np.mean(variances) if variances else 0.0

    # 3. Evidence Stability (Average Pairwise Token IoU)
    ious = []
    for i in range(n):
        for j in range(i + 1, n):
            ev1 = flatten_evidences(runs_data[i])
            ev2 = flatten_evidences(runs_data[j])
            iou = calculate_token_overlap(ev1, ev2)
            ious.append(iou)
            
    avg_iou = np.mean(ious) if ious else 0.0

    return {
        "avg_pairwise_kappa": avg_kappa,
        "avg_score_variance": avg_variance,
        "avg_pairwise_iou": avg_iou
    }

def analyze_accuracy(runs_data, human_data, repo_name):
    """Calculate accuracy metrics against Human Gold Standard."""
    metrics = {
        "kappas": [],
        "maes": [],
        "matches": [],
        "ious": []
    }
    
    human_checklist = flatten_checklist(human_data)
    human_scores = flatten_scores(human_data)
    human_evs = flatten_evidences(human_data)
    
    for run in runs_data:
        # Kappa
        run_check = flatten_checklist(run)
        metrics["kappas"].append(calculate_kappa(run_check, human_checklist))
        
        # MAE
        run_scores = flatten_scores(run)
        mae, match = calculate_mae(run_scores, human_scores)
        metrics["maes"].append(mae)
        metrics["matches"].append(match)
        
        # IoU (Token-based)
        run_evs = flatten_evidences(run)
        iou = calculate_token_overlap(run_evs, human_evs)
        metrics["ious"].append(iou)

    return {
        "mean_kappa": np.mean(metrics["kappas"]),
        "std_kappa": np.std(metrics["kappas"]),
        "mean_mae": np.mean(metrics["maes"]),
        "std_mae": np.std(metrics["maes"]),
        "mean_match": np.mean(metrics["matches"]),
        "mean_iou": np.mean(metrics["ious"]),
        "std_iou": np.std(metrics["ious"])
    }

def generate_stability_report(repo_name, n_runs, stability, output_path):
    """Generate the Stability/Consistency report."""
    report = f"# Model Consistency Analysis: {repo_name}\n\n"
    report += f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    report += f"**Runs:** {n_runs}\n"
    report += f"**Model:** Gemini 2.5 Flash (Temp 0.1)\n\n"
    
    report += "## Executive Summary\n"
    report += "This report analyzes the internal consistency of the LLM when evaluating the same repository multiple times.\n\n"
    
    if stability:
        report += "### Key Metrics\n"
        report += "| Metric | Value | Interpretation |\n"
        report += "|---|---|---|\n"
        report += f"| **Checklist Consistency** (Avg Pairwise Kappa) | {stability['avg_pairwise_kappa']:.3f} | "
        k = stability['avg_pairwise_kappa']
        if k > 0.8: report += "Perfect/Almost Perfect"
        elif k > 0.6: report += "Substantial"
        elif k > 0.4: report += "Moderate"
        else: report += "Fair/Slight"
        report += " |\n"
        
        report += f"| **Score Stability** (Avg Variance) | {stability['avg_score_variance']:.3f} | Lower is better (0 = Perfect) |\n"
        report += f"| **Evidence Stability** (Avg Pairwise IoU) | {stability['avg_pairwise_iou']:.3f} | Higher is better (1 = Perfect) |\n"
        
        report += "\n### Detailed Variance by Category\n"
        report += "High variance in scores indicates categories where the model is uncertain or sensitive to prompt/sampling noise.\n"
    else:
        report += "*Insufficient runs for stability analysis (N < 2).*\n"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Stability Report generated: {output_path}")

def generate_accuracy_report(repo_name, n_runs, accuracy, output_path):
    """Generate the Human Comparison report."""
    report = f"# Human vs AI Comparison Analysis: {repo_name}\n\n"
    report += f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    report += f"**Runs Averaged:** {n_runs}\n"
    report += f"**Model:** Gemini 2.5 Flash (Temp 0.1)\n\n"
    
    report += "## Executive Summary\n"
    report += "This report compares the LLM's evaluations against the Human Gold Standard.\n\n"
    
    if accuracy:
        report += "### Agreement Metrics\n"
        report += "| Metric | Mean | Std Dev | Target |\n"
        report += "|---|---|---|---|\n"
        report += f"| **Checklist Agreement** (Cohen's Kappa) | {accuracy['mean_kappa']:.3f} | ±{accuracy['std_kappa']:.3f} | > 0.6 |\n"
        report += f"| **Score Similarity** (MAE) | {accuracy['mean_mae']:.3f} | ±{accuracy['std_mae']:.3f} | < 0.5 |\n"
        report += f"| **Score Match Rate** (Diff ≤ 1) | {accuracy['mean_match']:.1%} | - | > 80% |\n"
        report += f"| **Evidence Correspondence** (IoU) | {accuracy['mean_iou']:.3f} | ±{accuracy['std_iou']:.3f} | > 0.5 |\n"
        
        report += "\n### Interpretation\n"
        if accuracy['mean_kappa'] > 0.6:
            report += "- **Checklists:** The model agrees substantially with human decisions.\n"
        else:
            report += "- **Checklists:** There is significant disagreement on binary criteria.\n"
            
        if accuracy['mean_match'] > 0.8:
            report += "- **Scores:** The model's quality ratings are highly similar to human ratings.\n"
        else:
            report += "- **Scores:** The model tends to rate differently than the human evaluator.\n"
            
    else:
        report += "*No Human Evaluation provided for comparison.*\n"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Accuracy Report generated: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Run consistency experiment for a repo.")
    parser.add_argument("--repo", required=True, help="Repository URL")
    parser.add_argument("--n", type=int, default=3, help="Number of runs")
    parser.add_argument("--human", help="Path to Human Evaluation JSON (optional)")
    parser.add_argument("--output", default="data/reports/experiments", help="Output directory")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model to use (default: {DEFAULT_MODEL})")
    args = parser.parse_args()
    
    # Setup directories
    repo_name = args.repo.split('/')[-1]
    exp_dir = os.path.join(args.output, repo_name)
    os.makedirs(exp_dir, exist_ok=True)
    
    # 1. Download README
    print(f"Downloading README for {repo_name}...")
    dl = ReadmeDownloader()
    try:
        readme_path = dl.download(args.repo)
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_text = f.read()
            readme_lines = f.readlines()
    except Exception as e:
        print(f"Failed to download README: {e}")
        return

    # 2. Run Evaluations
    runs_data = []
    for i in range(args.n):
        data = run_evaluation(readme_text, args.model, i+1, exp_dir)
        if data:
            runs_data.append(data)
        
        # Wait to respect rate limits (Free Tier is strict)
        if i < args.n - 1:
            print("Waiting 60s before next run to avoid rate limits...")
            time.sleep(60) 
            
    if not runs_data:
        print("No successful runs.")
        return

    # 3. Analyze
    print("\nAnalyzing results...")
    stability = analyze_stability(runs_data)
    
    accuracy = None
    if args.human:
        try:
            with open(args.human, 'r', encoding='utf-8') as f:
                human_data = json.load(f)
            accuracy = analyze_accuracy(runs_data, human_data, repo_name)
        except Exception as e:
            print(f"Error loading human data: {e}")

    # 4. Report
    stability_report_path = os.path.join(exp_dir, f"stability_report_{repo_name}.md")
    generate_stability_report(repo_name, args.n, stability, stability_report_path)
    
    if accuracy:
        accuracy_report_path = os.path.join(exp_dir, f"human_comparison_report_{repo_name}.md")
        generate_accuracy_report(repo_name, args.n, accuracy, accuracy_report_path)
    
    # Cleanup
    dl.cleanup_temp()

if __name__ == "__main__":
    main()
