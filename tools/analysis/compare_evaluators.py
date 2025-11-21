import json
import os
from pathlib import Path

def load_json_file(filepath):
    """Load JSON file with error handling."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def extract_quality_metrics(category_data):
    """Extract quality metrics from a category."""
    if isinstance(category_data, dict):
        return category_data.get('quality', {})
    return {}

def extract_justifications(category_data):
    """Extract justifications from a category."""
    if isinstance(category_data, dict):
        justifications = category_data.get('justifications', [])
        if justifications:
            return ' '.join(justifications)
    return ""

def generate_single_project_report(repo_name, gemini_data, manual_data):
    """Generate report for a single project."""
    
    report = f"# Comparison: {repo_name.upper()}\n\n"
    report += "**Gemini vs Manual Evaluator**\n\n"
    
    # Extract categories
    gemini_categories = gemini_data.get('categories', {})
    manual_categories = manual_data.get('categories', {})
    
    all_categories = set(gemini_categories.keys()) | set(manual_categories.keys())
    
    # Compare each category/taxonomy
    for category in sorted(all_categories):
        gemini_cat = gemini_categories.get(category, {})
        manual_cat = manual_categories.get(category, {})
        
        report += f"## {category.replace('_', ' ').upper()}\n\n"
        
        # Extract quality scores
        gemini_quality = extract_quality_metrics(gemini_cat)
        manual_quality = extract_quality_metrics(manual_cat)
        
        # Extract justifications
        gemini_just = extract_justifications(gemini_cat)
        manual_just = extract_justifications(manual_cat)
        
        # Scores table
        report += "### Scores (Quality Metrics)\n\n"
        report += "| Metric | Gemini | Manual | Status |\n"
        report += "|--------|--------|--------|--------|\n"
        
        all_metrics = set(gemini_quality.keys()) | set(manual_quality.keys())
        for metric in sorted(all_metrics):
            gemini_val = gemini_quality.get(metric, '-')
            manual_val = manual_quality.get(metric, '-')
            
            # Mark differences
            if gemini_val == manual_val:
                status = "✅"
            else:
                status = "⚠️"
            
            report += f"| {metric} | {gemini_val} | {manual_val} | {status} |\n"
        
        report += "\n### Justifications\n\n"
        report += "**Gemini:**\n"
        report += f"> {gemini_just if gemini_just else 'No justification'}\n\n"
        report += "**Manual:**\n"
        report += f"> {manual_just if manual_just else 'No justification'}\n\n"
        
        if gemini_just != manual_just:
            report += "**Status:** ⚠️ Justifications differ\n\n"
        else:
            report += "**Status:** ✅ Justifications match\n\n"
        
        report += "---\n\n"
    
    return report

def generate_report_by_taxonomy(gemini_path, manual_path, output_dir):
    """Generate comparative reports organized by taxonomy - one file per project."""
    
    gemini_dir = Path(gemini_path)
    manual_dir = Path(manual_path)
    output_path = Path(output_dir)
    
    # Find JSON files in both folders
    gemini_files = set(f.name for f in gemini_dir.glob('*.json'))
    manual_files = set(f.name for f in manual_dir.glob('*.json'))
    
    common_files = gemini_files & manual_files
    
    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate index report
    index_report = "# Comparison Index\n\n"
    index_report += f"**Comparison: Gemini vs Manual Evaluator**\n\n"
    index_report += f"## Summary\n"
    index_report += f"- Common files: {len(common_files)}\n"
    index_report += f"- Only in Gemini: {len(gemini_files - manual_files)}\n"
    index_report += f"- Only in Manual: {len(manual_files - gemini_files)}\n\n"
    index_report += "## Compared Projects\n\n"
    
    # Compare each file
    for filename in sorted(common_files):
        gemini_file = gemini_dir / filename
        manual_file = manual_dir / filename
        
        gemini_data = load_json_file(gemini_file)
        manual_data = load_json_file(manual_file)
        
        if gemini_data is None or manual_data is None:
            print(f"⚠️ Error loading {filename}")
            continue
        
        repo_name = filename.replace('.json', '')
        
        # Generate individual report
        project_report = generate_single_project_report(repo_name, gemini_data, manual_data)
        
        # Save to individual file
        project_file = output_path / f"comparison-{repo_name}.md"
        with open(project_file, 'w', encoding='utf-8') as f:
            f.write(project_report)
        
        print(f"✅ Report generated: {project_file}")
        
        # Add to index
        index_report += f"- [{repo_name.upper()}](comparison-{repo_name}.md)\n"
    
    # Save index
    index_file = output_path / "README.md"
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(index_report)
    
    print(f"✅ Index generated at: {index_file}")

# Run comparison
if __name__ == "__main__":
    gemini_path = "data/samples/gemini-evaluation"
    manual_path = "data/samples/manual-evaluation"
    output_dir = "data/reports/comparison_reports"
    
    generate_report_by_taxonomy(gemini_path, manual_path, output_dir)