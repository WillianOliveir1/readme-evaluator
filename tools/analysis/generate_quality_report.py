import json
import glob
import os
import pandas as pd
import numpy as np

def load_evaluations(directory, source_label):
    evaluations = []
    files = glob.glob(os.path.join(directory, "*.json"))
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                if 'metadata' not in data:
                    data['metadata'] = {}
                data['metadata']['source'] = source_label
                evaluations.append(data)
        except Exception as e:
            print(f"Error reading {f}: {e}")
    return evaluations

def calculate_averages(evaluations):
    repo_data = []
    all_dimensions = set()

    for eval_data in evaluations:
        repo_name_raw = eval_data.get('metadata', {}).get('repository_name', 'Unknown')
        source = eval_data.get('metadata', {}).get('source', 'Unknown')
        repo_name = f"{repo_name_raw} ({source})"
        
        categories = eval_data.get('categories', {})
        dimensions_summary = eval_data.get('dimensions_summary', {})
        
        target_dims = [k for k in dimensions_summary.keys() if k not in ['global_notes', 'global_observations']]
        all_dimensions.update(target_dims)
        
        # Use ONLY dimensions_summary for calculations
        repo_avgs = {
            'Repository': repo_name_raw,
            'Source': source
        }
        valid_scores_count = 0
        sum_avgs = 0
        
        for dim in target_dims:
            score = dimensions_summary.get(dim)
            final_score = None
            
            if isinstance(score, (int, float)):
                final_score = score
            elif isinstance(score, dict):
                if 'note' in score:
                    final_score = score['note']
                elif 'score' in score:
                    final_score = score['score']
            
            if final_score is not None:
                repo_avgs[dim] = round(float(final_score), 2)
                sum_avgs += final_score
                valid_scores_count += 1
            else:
                repo_avgs[dim] = np.nan
        
        if valid_scores_count > 0:
            repo_avgs['Overall'] = round(sum_avgs / valid_scores_count, 2)
        else:
            repo_avgs['Overall'] = 0.0
            
        repo_data.append(repo_avgs)

    return repo_data, sorted(list(all_dimensions))

def generate_markdown_report(repo_data, dimensions, output_file):
    df = pd.DataFrame(repo_data)
    
    for dim in dimensions:
        if dim not in df.columns:
            df[dim] = np.nan

    # Group by Source and calculate mean for dimensions + Overall
    # numeric_only=True is safer
    grouped = df.groupby('Source')[dimensions + ['Overall']].mean(numeric_only=True)
    
    # Transpose: Rows become Dimensions, Columns become Sources
    transposed = grouped.T
    
    # Ensure column order: Manual, Gemini (if they exist)
    cols = []
    if 'Manual' in transposed.columns:
        cols.append('Manual')
    if 'Gemini' in transposed.columns:
        cols.append('Gemini')
    
    # Add any other sources found
    for c in transposed.columns:
        if c not in cols:
            cols.append(c)
            
    transposed = transposed[cols]
    
    # Reset index to get 'Dimensão' column
    transposed.index.name = 'Dimensão'
    transposed = transposed.reset_index()
    
    # Round numeric columns
    for col in cols:
        transposed[col] = transposed[col].round(2)
        
    # Rename columns for the final report
    final_cols = ['Dimensão'] + [f'Média {c}' for c in cols]
    transposed.columns = final_cols

    markdown_table = transposed.to_markdown(index=False)
    
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
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Report generated at: {output_file}")
    print(markdown_table)

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    manual_eval_dir = os.path.join(base_dir, "data", "samples", "manual-evaluation")
    gemini_eval_dir = os.path.join(base_dir, "data", "samples", "gemini-evaluation")
    
    output_report = os.path.join(base_dir, "data", "reports", "combined_quality_report.md")
    
    all_evals = []
    
    print(f"Reading Manual evaluations from: {manual_eval_dir}")
    all_evals.extend(load_evaluations(manual_eval_dir, "Manual"))
    
    print(f"Reading Gemini evaluations from: {gemini_eval_dir}")
    all_evals.extend(load_evaluations(gemini_eval_dir, "Gemini"))
    
    if all_evals:
        data, dims = calculate_averages(all_evals)
        generate_markdown_report(data, dims, output_report)
    else:
        print("No evaluation files found.")
