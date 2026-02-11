import json
import os
import glob
from statistics import mean

def calculate_average(categories, metric):
    """Calculate average for a metric across categories (excluding dimensions_summary)."""
    values = []
    for cat_name, cat_data in categories.items():
        if cat_name == 'dimensions_summary':
            continue
        
        val = None
        if 'quality' in cat_data and isinstance(cat_data['quality'], dict):
            q = cat_data['quality']
            if metric in q:
                val = q[metric]
                if isinstance(val, dict) and 'note' in val:
                    val = val['note']
        
        if val is not None and isinstance(val, (int, float)):
            values.append(val)
            
    if not values:
        return 0.0
    return mean(values)

def calculate_from_summary(data, metric):
    """Calculate a metric score from dimensions_summary (holistic score).
    
    This is the recommended approach: use the global dimensions_summary
    which provides holistic scores, NOT the per-category averages.
    """
    summary = data.get('dimensions_summary', {})
    val = summary.get(metric)
    
    if isinstance(val, dict):
        val = val.get('note', val.get('score'))
    
    if val is not None and isinstance(val, (int, float)):
        return float(val)
    
    # Fallback: compute from categories if summary is missing
    categories = data.get('categories', {})
    return calculate_average(categories, metric)

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    repo = data.get('metadata', {}).get('repository_name', 'Unknown')
    evaluator = data.get('metadata', {}).get('evaluator', 'Unknown')
    
    metrics = ['clarity', 'readability', 'structure', 'understandability', 'conciseness', 'effectiveness']
    results = {}
    
    for m in metrics:
        score = calculate_from_summary(data, m)
        results[m] = round(score, 2)
        
    return repo, evaluator, results

def main():
    # Resolve paths relative to the project root (two levels up from this file)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    base_dirs = [
        os.path.join(project_root, 'data', 'samples', 'manual-evaluation'),
        os.path.join(project_root, 'data', 'samples', 'gemini-evaluation'),
    ]
    
    print(f"{'Repo':<20} | {'Source':<10} | {'Cla':<5} | {'Rea':<5} | {'Str':<5} | {'Und':<5} | {'Con':<5} | {'Eff':<5}")
    print("-" * 80)
    
    for d in base_dirs:
        files = glob.glob(os.path.join(d, '*.json'))
        for f in files:
            repo, evaluator, res = process_file(f)
            source = "Manual" if "manual" in d else "Gemini"
            print(f"{repo:<20} | {source:<10} | {res['clarity']:<5} | {res['readability']:<5} | {res['structure']:<5} | {res['understandability']:<5} | {res['conciseness']:<5} | {res['effectiveness']:<5}")

if __name__ == "__main__":
    main()
