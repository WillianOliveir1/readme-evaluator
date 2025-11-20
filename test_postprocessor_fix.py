#!/usr/bin/env python
"""Teste do post-processor corrigido"""

import json
import sys
from pathlib import Path

# Adiciona backend ao path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from evaluate.json_postprocessor import (
    normalize_present_categories,
    remove_disallowed_category_fields,
    fix_string_arrays_in_json,
    validate_and_fix_json
)

def test_with_example():
    """Testa com arquivo de exemplo real"""
    example_file = Path(__file__).parent / 'backend' / 'examples' / 'manual-evaluation' / 'pandas.json'
    
    if not example_file.exists():
        print(f"❌ Arquivo de exemplo não encontrado: {example_file}")
        return
    
    print(f"📂 Carregando exemplo: {example_file.name}")
    with open(example_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("\n✅ JSON carregado com sucesso")
    print(f"   - Metadata: {data['metadata']['repository_name']}")
    print(f"   - Present categories: {list(data['structural_summary']['present_categories'].values())}")
    
    # Testa normalização
    print("\n🔧 Aplicando normalize_present_categories...")
    data = normalize_present_categories(data)
    
    print("✅ Present categories após normalização:")
    for cat, val in data['structural_summary']['present_categories'].items():
        print(f"   - {cat}: {val}")
    
    # Testa remove_disallowed_category_fields
    print("\n🔧 Aplicando remove_disallowed_category_fields...")
    data = remove_disallowed_category_fields(data)
    print("✅ Campos removidos e estrutura corrigida")
    
    # Verifica estrutura de dimensions_summary
    print("\n📊 Verificando dimensions_summary:")
    ds = data['dimensions_summary']
    for key in ['quality', 'appeal', 'clarity']:
        val = ds[key]
        if isinstance(val, dict):
            print(f"   ✓ {key}: {type(val).__name__} com note={val.get('note', 'N/A')}")
        else:
            print(f"   ✗ {key}: {type(val).__name__} (deveria ser dict)")
    
    # Testa fix_string_arrays_in_json
    print("\n🔧 Aplicando fix_string_arrays_in_json...")
    data = fix_string_arrays_in_json(data)
    print("✅ Arrays corrigidas")
    
    # Valida contra schema
    print("\n✅ Validando contra schema...")
    schema_file = Path(__file__).parent / 'schemas' / 'taxonomia.schema.json'
    is_valid, msg = validate_and_fix_json(data, str(schema_file))
    
    if is_valid:
        print(f"✅ {msg}")
    else:
        print(f"❌ {msg}")
    
    return data

if __name__ == "__main__":
    test_with_example()
