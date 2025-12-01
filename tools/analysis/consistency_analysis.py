import json
import os
import glob
import numpy as np
from pathlib import Path
import re

# Configuration
GEMINI_DIR = r"c:\Users\WiOliveira\OneDrive - MODEC\Documents\Projects\readme-evaluator\data\samples\gemini-evaluation"
MANUAL_DIR = r"c:\Users\WiOliveira\OneDrive - MODEC\Documents\Projects\readme-evaluator\data\samples\manual-evaluation"
VARIANCE_DIR = r"c:\Users\WiOliveira\OneDrive - MODEC\Documents\Projects\readme-evaluator\data\processed"
README_DIRS = [
    r"c:\Users\WiOliveira\OneDrive - MODEC\Documents\Projects\readme-evaluator\data\readmes_archive",
    r"c:\Users\WiOliveira\OneDrive - MODEC\Documents\Projects\readme-evaluator\data\samples"
]

def load_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def load_readme(repo_name):
    """Try to find the README file for a given repo."""
    # Normalize repo name (e.g. 'pandas' -> 'pandas-dev-pandas')
    # This is a heuristic. We search for files containing the repo name.
    for d in README_DIRS:
        files = glob.glob(os.path.join(d, "*.md"))
        for f in files:
            if repo_name.lower() in os.path.basename(f).lower():
                with open(f, 'r', encoding='utf-8') as rf:
                    return rf.readlines()
    return None

def flatten_checklist(data):
    """Extract all checklist items as a flat list of values."""
    items = []
    categories = data.get('categories', {})
    for cat_name, cat_data in categories.items():
        checklist = cat_data.get('checklist', {})
        for key, value in checklist.items():
            # Normalize value to string for categorical comparison
            val_str = str(value).lower() if value is not None else "null"
            items.append({
                'id': f"{cat_name}:{key}",
                'value': val_str
            })
    return items

def flatten_scores(data):
    """Extract all quality scores."""
    scores = []
    categories = data.get('categories', {})
    for cat_name, cat_data in categories.items():
        quality = cat_data.get('quality', {})
        for key, value in quality.items():
            if isinstance(value, (int, float)):
                scores.append({
                    'id': f"{cat_name}:{key}",
                    'value': float(value)
                })
    return scores

def flatten_evidences(data):
    """Extract evidences."""
    evs = []
    categories = data.get('categories', {})
    for cat_name, cat_data in categories.items():
        ev_list = cat_data.get('evidences', [])
        evs.append({
            'id': cat_name,
            'value': ev_list
        })
    return evs

def calculate_kappa(list1, list2):
    """Calculate Cohen's Kappa for two lists of categorical values."""
    if not list1 or not list2 or len(list1) != len(list2):
        return 0.0
    
    # Align by ID
    dict1 = {item['id']: item['value'] for item in list1}
    dict2 = {item['id']: item['value'] for item in list2}
    
    common_ids = set(dict1.keys()) & set(dict2.keys())
    if not common_ids:
        return 0.0
    
    y1 = [dict1[i] for i in common_ids]
    y2 = [dict2[i] for i in common_ids]
    
    # Unique classes
    classes = sorted(list(set(y1 + y2)))
    n_classes = len(classes)
    class_map = {c: i for i, c in enumerate(classes)}
    
    # Confusion Matrix
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for a, b in zip(y1, y2):
        cm[class_map[a]][class_map[b]] += 1
        
    n = len(y1)
    if n == 0: return 0.0
    
    # Observed Agreement (Po)
    po = np.trace(cm) / n
    
    # Expected Agreement (Pe)
    sum_row = np.sum(cm, axis=1)
    sum_col = np.sum(cm, axis=0)
    pe = np.sum(sum_row * sum_col) / (n * n)
    
    if pe == 1: return 1.0 # Perfect agreement
    
    kappa = (po - pe) / (1 - pe)
    return kappa

def calculate_mae(list1, list2):
    """Calculate Mean Absolute Error."""
    dict1 = {item['id']: item['value'] for item in list1}
    dict2 = {item['id']: item['value'] for item in list2}
    
    common_ids = set(dict1.keys()) & set(dict2.keys())
    if not common_ids:
        return 0.0, 0.0
    
    diffs = []
    matches = 0 # Diff <= 1
    
    for i in common_ids:
        d = abs(dict1[i] - dict2[i])
        diffs.append(d)
        if d <= 1.0:
            matches += 1
            
    mae = np.mean(diffs)
    match_rate = matches / len(diffs)
    
    return mae, match_rate

def find_line_numbers(evidence_text, readme_lines):
    """Find line numbers where evidence_text appears in readme_lines."""
    # Simple substring search. 
    # Clean text: remove markdown bold/italic markers for better matching?
    # For now, strict matching.
    
    lines = set()
    clean_ev = evidence_text.strip()
    if not clean_ev: return lines
    
    for i, line in enumerate(readme_lines):
        if clean_ev in line:
            lines.add(i + 1)
            
    return lines

def normalize_and_tokenize(text_list):
    """Join list of texts, normalize, and tokenize into a set of words."""
    if not text_list:
        return set()
    
    # Join all texts
    full_text = " ".join(text_list)
    
    # Lowercase
    full_text = full_text.lower()
    
    # Remove non-alphanumeric (keep spaces)
    full_text = re.sub(r'[^a-z0-9\s]', '', full_text)
    
    # Split into tokens
    tokens = set(full_text.split())
    return tokens

def calculate_token_overlap(evidences1, evidences2):
    """Calculate Jaccard Index (IoU) between two lists of evidence strings."""
    # Helper to extract strings from the flattened structure [{'id':..., 'value': [...]}]
    def extract_strings(flat_evs):
        all_strings = []
        for item in flat_evs:
            if isinstance(item['value'], list):
                all_strings.extend(item['value'])
            elif isinstance(item['value'], str):
                all_strings.append(item['value'])
        return all_strings

    set1 = normalize_and_tokenize(extract_strings(evidences1))
    set2 = normalize_and_tokenize(extract_strings(evidences2))
    
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
        
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union

def calculate_evidence_overlap(gemini_evs, manual_evs, repo_name=None):
    """Calculate Evidence Overlap using Token Jaccard Index."""
    # repo_name is kept for compatibility but ignored
    return calculate_token_overlap(gemini_evs, manual_evs)

def analyze_variance(repo_name):
    """Analyze variance across multiple runs for a repo."""
    # Find files
    pattern = os.path.join(VARIANCE_DIR, f"{repo_name}*.json")
    files = glob.glob(pattern)
    
    if len(files) < 2:
        return None
        
    all_scores = {} # id -> list of scores
    
    for fpath in files:
        data = load_json(fpath)
        if not data: continue
        scores = flatten_scores(data)
        for item in scores:
            if item['id'] not in all_scores:
                all_scores[item['id']] = []
            all_scores[item['id']].append(item['value'])
            
    # Calculate variance per item, then mean variance
    variances = []
    for scores in all_scores.values():
        if len(scores) > 1:
            variances.append(np.var(scores))
            
    return np.mean(variances) if variances else 0.0

def main():
    print("# Consistency Analysis Report\n")
    
    gemini_files = glob.glob(os.path.join(GEMINI_DIR, "*.json"))
    
    total_kappa = []
    total_mae = []
    total_match = []
    total_iou = []
    
    print("## Per-Repository Analysis\n")
    print("| Repository | Kappa (Checklist) | MAE (Scores) | Match Rate (<=1) | Evidence IoU |")
    print("|---|---|---|---|---|")
    
    for g_path in gemini_files:
        filename = os.path.basename(g_path)
        repo_name = filename.replace('.json', '')
        
        m_path = os.path.join(MANUAL_DIR, filename)
        if not os.path.exists(m_path):
            continue
            
        g_data = load_json(g_path)
        m_data = load_json(m_path)
        
        # Checklist Kappa
        g_check = flatten_checklist(g_data)
        m_check = flatten_checklist(m_data)
        kappa = calculate_kappa(g_check, m_check)
        total_kappa.append(kappa)
        
        # Scores MAE
        g_scores = flatten_scores(g_data)
        m_scores = flatten_scores(m_data)
        mae, match = calculate_mae(g_scores, m_scores)
        total_mae.append(mae)
        total_match.append(match)
        
        # Evidence IoU
        g_evs = flatten_evidences(g_data)
        m_evs = flatten_evidences(m_data)
        iou = calculate_evidence_overlap(g_evs, m_evs, repo_name)
        iou_str = f"{iou:.2f}" if iou is not None else "N/A"
        if iou is not None: total_iou.append(iou)
        
        print(f"| {repo_name} | {kappa:.2f} | {mae:.2f} | {match:.2%} | {iou_str} |")
        
    print("\n## Aggregate Metrics\n")
    print(f"- **Mean Cohen's Kappa**: {np.mean(total_kappa):.2f}")
    print(f"- **Mean MAE**: {np.mean(total_mae):.2f}")
    print(f"- **Mean Score Match Rate**: {np.mean(total_match):.2%}")
    if total_iou:
        print(f"- **Mean Evidence IoU**: {np.mean(total_iou):.2f}")
    else:
        print("- **Mean Evidence IoU**: N/A (No READMEs found)")
        
    print("\n## Variance Analysis (Stability)\n")
    # Check for Keras specifically as we saw files for it
    keras_var = analyze_variance("keras-3")
    if keras_var is not None:
        print(f"- **Keras Score Variance**: {keras_var:.4f}")
    else:
        print("- No repeated runs found for variance analysis.")

if __name__ == "__main__":
    main()
