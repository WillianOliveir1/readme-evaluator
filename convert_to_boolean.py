#!/usr/bin/env python
"""
Script para converter present_categories e checklist de:
- 'present'/'absent' -> True/False
- '✔'/'✖' -> True/False  
- 'N/A' -> None
"""

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent


def convert_values(value: Any) -> Any:
    """Converte valores presentes em present_categories e checklist"""
    if isinstance(value, str):
        val_lower = value.lower().strip()
        # Conversões para True
        if val_lower in ['present', '✔', 'true', 'sim', 'yes', '1', 'v', 'y']:
            return True
        # Conversões para False
        elif val_lower in ['absent', '✖', 'false', 'não', 'no', '0', 'n']:
            return False
        # Conversões para None
        elif val_lower in ['n/a', 'na', 'none']:
            return None
    return value


def convert_dict_recursively(obj: Any) -> Any:
    """Recursivamente converte valores em present_categories e checklist"""
    if isinstance(obj, dict):
        result = {}
        for key, val in obj.items():
            # Se está em present_categories ou é um dict de checklist
            if key == 'present_categories' and isinstance(val, dict):
                result[key] = {k: convert_values(v) for k, v in val.items()}
            elif key == 'checklist' and isinstance(val, dict):
                result[key] = {k: convert_values(v) for k, v in val.items()}
            elif isinstance(val, (dict, list)):
                result[key] = convert_dict_recursively(val)
            else:
                result[key] = val
        return result
    elif isinstance(obj, list):
        return [convert_dict_recursively(item) for item in obj]
    return obj


def convert_jsonl_line(line: str) -> str:
    """Converte uma linha de JSONL"""
    if not line.strip():
        return line
    
    try:
        obj = json.loads(line)
        converted = convert_dict_recursively(obj)
        return json.dumps(converted, ensure_ascii=False)
    except json.JSONDecodeError:
        # Se não for JSON válido, retorna a linha original
        return line


def process_file(filepath: Path) -> tuple[bool, str]:
    """Processa um arquivo JSON ou JSONL"""
    if not filepath.exists():
        return False, f"Arquivo não encontrado: {filepath}"
    
    try:
        if filepath.suffix == '.json' and 'package.json' not in filepath.name:
            # Arquivo JSON (não package.json)
            with open(filepath, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    return False, f"JSON inválido em {filepath.name}: {e}"
            
            # Converte
            converted = convert_dict_recursively(data)
            
            # Salva
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(converted, f, indent=2, ensure_ascii=False)
            
            return True, f"✓ {filepath.name}"
        
        elif filepath.suffix == '.jsonl':
            # Arquivo JSONL
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            converted_lines = [convert_jsonl_line(line) for line in lines]
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(converted_lines)
            
            return True, f"✓ {filepath.name}"
        
        return False, f"Tipo de arquivo não reconhecido: {filepath.suffix}"
    
    except Exception as e:
        return False, f"✗ {filepath.name}: {str(e)}"


def main():
    """Processa todos os arquivos JSON e JSONL do repositório"""
    print("🔍 Procurando arquivos JSON e JSONL no repositório...\n")
    
    # Encontra todos os JSONs (exceto node_modules e package.json)
    json_files = list(REPO_ROOT.rglob('*.json'))
    json_files = [f for f in json_files if 'node_modules' not in str(f) and f.name != 'package.json']
    
    # Encontra todos os JSONLs
    jsonl_files = list(REPO_ROOT.rglob('*.jsonl'))
    
    all_files = json_files + jsonl_files
    
    print(f"📋 Encontrados {len(all_files)} arquivos para processar:\n")
    
    success_count = 0
    fail_count = 0
    
    for filepath in sorted(all_files):
        rel_path = filepath.relative_to(REPO_ROOT)
        success, msg = process_file(filepath)
        
        if success:
            print(f"  {msg} ({rel_path})")
            success_count += 1
        else:
            print(f"  {msg}")
            fail_count += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Sucesso: {success_count} arquivos processados")
    print(f"❌ Erros: {fail_count} arquivos")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
