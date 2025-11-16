#!/usr/bin/env python
"""
JSON Post-Processor: Corrige arrays que estão como strings

Este script é uma solução rápida para garantir que campos como
'justifications', 'evidences' e 'suggested_improvements' sempre
sejam arrays, mesmo se o modelo retornar strings.
"""

import json
from typing import Any


# Define quais campos são esperados em cada categoria
CATEGORY_SCHEMAS = {
    "other": {
        "allowed_fields": ["checklist", "action", "evidences", "suggested_improvements"],
        "required_fields": ["checklist", "action", "evidences", "suggested_improvements"],
    },
    # Todas as outras categorias têm: checklist, quality, evidences, justifications, suggested_improvements
    "default": {
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
        "required_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    }
}


def fix_string_arrays_in_json(data: Any) -> Any:
    """
    Percorre o JSON e converte strings em arrays para campos específicos.
    Também converte strings em booleanos para campos que exigem boolean.
    Remove campos não permitidos por categoria.
    
    Campos que devem ser arrays:
    - justifications
    - evidences
    - suggested_improvements
    
    Campos que devem ser booleanos:
    - reclassify
    - suggest_removal
    
    Args:
        data: JSON parseado (dict, list, etc)
        
    Returns:
        JSON corrigido
    """
    
    if isinstance(data, dict):
        # Processa cada chave do dicionário
        for key, value in data.items():
            # Se a chave é um dos campos que deve ser array
            if key in ['justifications', 'evidences', 'suggested_improvements']:
                if isinstance(value, str):
                    # Converte string para array com um item
                    data[key] = [value]
                elif isinstance(value, list):
                    # Já é array, mas verifica se todos items são strings
                    data[key] = [
                        item if isinstance(item, str) else str(item)
                        for item in value
                    ]
            # Se a chave é um dos campos que deve ser booleano
            elif key in ['reclassify', 'suggest_removal']:
                if isinstance(value, str):
                    # Converte string para booleano
                    data[key] = value.lower() in ['true', 'sim', 'yes', '1', 'v', 'y']
                elif isinstance(value, (int, float)):
                    # Converte número para booleano
                    data[key] = bool(value)
                elif not isinstance(value, bool):
                    # Se não é booleano, tenta converter
                    try:
                        data[key] = bool(value)
                    except:
                        data[key] = False
            else:
                # Recursivamente processa sub-dicionários
                if isinstance(value, (dict, list)):
                    data[key] = fix_string_arrays_in_json(value)
    
    elif isinstance(data, list):
        # Processa cada item da lista
        data = [fix_string_arrays_in_json(item) for item in data]
    
    return data


def remove_disallowed_category_fields(data: Any) -> Any:
    """
    Remove campos que não são permitidos em cada categoria.
    
    A categoria 'other' tem estrutura diferente das outras:
    - other: checklist, action, evidences, suggested_improvements
    - outras: checklist, quality, evidences, justifications, suggested_improvements
    
    Args:
        data: JSON parseado (dict)
        
    Returns:
        JSON com campos não permitidos removidos
    """
    if not isinstance(data, dict):
        return data
    
    # Se tem a chave 'categories', processa cada categoria
    if 'categories' in data and isinstance(data['categories'], dict):
        for category_name, category_data in data['categories'].items():
            if isinstance(category_data, dict):
                # Determina quais campos são permitidos nesta categoria
                schema = CATEGORY_SCHEMAS.get(category_name, CATEGORY_SCHEMAS['default'])
                allowed = set(schema['allowed_fields'])
                
                # Remove campos não permitidos
                fields_to_remove = []
                for field in category_data.keys():
                    if field not in allowed:
                        fields_to_remove.append(field)
                
                for field in fields_to_remove:
                    del category_data[field]
    
    return data


def validate_and_fix_json(json_obj: dict, schema_path: str) -> tuple[bool, str]:
    """
    Valida JSON contra schema e aplica fix se necessário.
    
    Args:
        json_obj: JSON parseado
        schema_path: Caminho para o arquivo de schema
        
    Returns:
        (is_valid, message)
    """
    import jsonschema
    
    # Carrega schema
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    # Primeira tentativa de validação
    try:
        jsonschema.validate(instance=json_obj, schema=schema)
        return True, "JSON validado com sucesso na primeira tentativa!"
    except jsonschema.ValidationError as e:
        print(f"❌ Erro inicial: {e.message}")
        print(f"   Path: {list(e.path)}")
    
    # Aplica fix
    print("\n🔧 Aplicando correções automáticas...")
    fixed_json = fix_string_arrays_in_json(json_obj)
    
    # Segunda tentativa após fix
    try:
        jsonschema.validate(instance=fixed_json, schema=schema)
        return True, "✓ JSON corrigido e validado com sucesso!"
    except jsonschema.ValidationError as e:
        return False, f"❌ Erro mesmo após fix: {e.message} em {list(e.path)}"


# Exemplo de uso
if __name__ == "__main__":
    # Dados de teste
    test_data = {
        "metadata": {
            "repository_name": "Test",
            "repository_link": "http://example.com",
            "readme_raw_link": "http://example.com/readme",
            "evaluation_date": "2024-01-01",
            "evaluator": "Test",
            "general_observations": "Test"
        },
        "structural_summary": {
            "detected_sections": ["Section 1"],
            "present_categories": {
                "what": "✔",
                "why": "✔",
                "how_installation": "✔",
                "how_usage": "✖",
                "how_config_requirements": "✔",
                "when": "✖",
                "who": "✖",
                "license": "✖",
                "contribution": "✖",
                "references": "✔",
                "other": "N/A"
            },
            "organization_observations": "Test"
        },
        "categories": {
            "what": {
                "checklist": {"clear_description": 1, "features_scope": 1, "target_audience": 1},
                "quality": {"clarity": 5, "understandability": 5, "conciseness": 4, "consistency": 5},
                "evidences": ["Evidence 1"],  # ✓ Array
                "justifications": "This is a string instead of array",  # ❌ String
                "suggested_improvements": []
            }
        },
        "dimensions_summary": {"quality": 4, "appeal": 4},
        "executive_summary": {"strengths": [], "weaknesses": [], "critical_gaps": [], "priority_recommendations": []}
    }
    
    # Testa o fix
    print("Testando post-processor de JSON...")
    print("\n1. Antes do fix:")
    print(f"   justifications type: {type(test_data['categories']['what']['justifications'])}")
    
    fixed = fix_string_arrays_in_json(test_data)
    
    print("\n2. Depois do fix:")
    print(f"   justifications type: {type(fixed['categories']['what']['justifications'])}")
    print(f"   Valor: {fixed['categories']['what']['justifications']}")
