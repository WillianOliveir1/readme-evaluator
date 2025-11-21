import json
import os
from pathlib import Path

def load_json_file(filepath):
    """Carrega arquivo JSON com tratamento de erro"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao carregar {filepath}: {e}")
        return None

def extract_quality_metrics(category_data):
    """Extrai as métricas de qualidade de uma categoria"""
    if isinstance(category_data, dict):
        return category_data.get('quality', {})
    return {}

def extract_justifications(category_data):
    """Extrai as justificativas de uma categoria"""
    if isinstance(category_data, dict):
        justifications = category_data.get('justifications', [])
        if justifications:
            return ' '.join(justifications)
    return ""

def generate_single_project_report(repo_name, gemini_data, manual_data):
    """Gera relatório para um único projeto"""
    
    report = f"# Comparação: {repo_name.upper()}\n\n"
    report += "**Gemini vs Manual Evaluator**\n\n"
    
    # Extrair categorias
    gemini_categories = gemini_data.get('categories', {})
    manual_categories = manual_data.get('categories', {})
    
    all_categories = set(gemini_categories.keys()) | set(manual_categories.keys())
    
    # Comparar cada categoria/taxonomia
    for category in sorted(all_categories):
        gemini_cat = gemini_categories.get(category, {})
        manual_cat = manual_categories.get(category, {})
        
        report += f"## {category.replace('_', ' ').upper()}\n\n"
        
        # Extrair notas de qualidade
        gemini_quality = extract_quality_metrics(gemini_cat)
        manual_quality = extract_quality_metrics(manual_cat)
        
        # Extrair justificativas
        gemini_just = extract_justifications(gemini_cat)
        manual_just = extract_justifications(manual_cat)
        
        # Tabela de notas
        report += "### Notas (Quality Metrics)\n\n"
        report += "| Métrica | Gemini | Manual | Status |\n"
        report += "|---------|--------|--------|--------|\n"
        
        all_metrics = set(gemini_quality.keys()) | set(manual_quality.keys())
        for metric in sorted(all_metrics):
            gemini_val = gemini_quality.get(metric, '-')
            manual_val = manual_quality.get(metric, '-')
            
            # Marcar diferenças
            if gemini_val == manual_val:
                status = "✅"
            else:
                status = "⚠️"
            
            report += f"| {metric} | {gemini_val} | {manual_val} | {status} |\n"
        
        report += "\n### Justificativas\n\n"
        report += "**Gemini:**\n"
        report += f"> {gemini_just if gemini_just else 'Sem justificativa'}\n\n"
        report += "**Manual:**\n"
        report += f"> {manual_just if manual_just else 'Sem justificativa'}\n\n"
        
        if gemini_just != manual_just:
            report += "**Status:** ⚠️ Justificativas diferem\n\n"
        else:
            report += "**Status:** ✅ Justificativas iguais\n\n"
        
        report += "---\n\n"
    
    return report

def generate_report_by_taxonomy(gemini_path, manual_path, output_dir):
    """Gera relatórios comparativos organizados por taxonomia - um arquivo por projeto"""
    
    gemini_dir = Path(gemini_path)
    manual_dir = Path(manual_path)
    output_path = Path(output_dir)
    
    # Encontrar arquivos JSON em ambas as pastas
    gemini_files = set(f.name for f in gemini_dir.glob('*.json'))
    manual_files = set(f.name for f in manual_dir.glob('*.json'))
    
    common_files = gemini_files & manual_files
    
    # Criar diretório de saída se não existir
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Gerar relatório de índice
    index_report = "# Índice de Comparações\n\n"
    index_report += f"**Comparação: Gemini vs Manual Evaluator**\n\n"
    index_report += f"## Resumo\n"
    index_report += f"- Arquivos em comum: {len(common_files)}\n"
    index_report += f"- Apenas em Gemini: {len(gemini_files - manual_files)}\n"
    index_report += f"- Apenas em Manual: {len(manual_files - gemini_files)}\n\n"
    index_report += "## Projetos Comparados\n\n"
    
    # Comparar cada arquivo
    for filename in sorted(common_files):
        gemini_file = gemini_dir / filename
        manual_file = manual_dir / filename
        
        gemini_data = load_json_file(gemini_file)
        manual_data = load_json_file(manual_file)
        
        if gemini_data is None or manual_data is None:
            print(f"⚠️ Erro ao carregar {filename}")
            continue
        
        repo_name = filename.replace('.json', '')
        
        # Gerar relatório individual
        project_report = generate_single_project_report(repo_name, gemini_data, manual_data)
        
        # Salvar em arquivo individual
        project_file = output_path / f"comparison-{repo_name}.md"
        with open(project_file, 'w', encoding='utf-8') as f:
            f.write(project_report)
        
        print(f"✅ Relatório gerado: {project_file}")
        
        # Adicionar ao índice
        index_report += f"- [{repo_name.upper()}](comparison-{repo_name}.md)\n"
    
    # Salvar índice
    index_file = output_path / "README.md"
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(index_report)
    
    print(f"✅ Índice gerado em: {index_file}")

# Executar comparação
if __name__ == "__main__":
    gemini_path = "data/samples/gemini-evaluation"
    manual_path = "data/samples/manual-evaluation"
    output_dir = "data/reports/comparison_reports"
    
    generate_report_by_taxonomy(gemini_path, manual_path, output_dir)