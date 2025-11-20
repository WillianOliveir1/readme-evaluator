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
# Baseado no schema oficial: schemas/taxonomia.schema.json
CATEGORY_SCHEMAS = {
    "other": {
        "checklist_fields": ["generic_sections", "placeholders"],
        "allowed_fields": ["checklist", "action", "evidences", "suggested_improvements"],
    },
    "what": {
        "checklist_fields": ["clear_description", "features_scope", "target_audience"],
        "quality_fields": ["clarity", "understandability", "conciseness", "consistency"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "why": {
        "checklist_fields": ["explicit_purpose", "benefits_vs_alternatives", "use_cases"],
        "quality_fields": ["clarity", "effectiveness", "appeal"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "how_installation": {
        "checklist_fields": ["reproducible_commands", "compatibility_requirements", "dependencies"],
        "quality_fields": ["structure", "readability", "clarity"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "how_usage": {
        "checklist_fields": ["minimal_working_example", "io_examples", "api_commands_context"],
        "quality_fields": ["understandability", "code_readability", "effectiveness"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "how_config_requirements": {
        "checklist_fields": ["documented_configuration", "parameters_options", "troubleshooting"],
        "quality_fields": ["clarity", "structure", "conciseness"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "when": {
        "checklist_fields": ["current_status", "roadmap", "changelog"],
        "quality_fields": ["clarity", "consistency"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "who": {
        "checklist_fields": ["authors_maintainers", "contact_channels", "code_of_conduct"],
        "quality_fields": ["clarity", "consistency"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "license": {
        "checklist_fields": ["license_type", "license_link"],
        "quality_fields": ["clarity", "consistency"],  # NOTA: license usa valores inteiros simples, não objetos
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "contribution": {
        "checklist_fields": ["contributing_link", "contribution_steps", "standards"],
        "quality_fields": ["structure", "clarity", "readability"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
    "references": {
        "checklist_fields": ["docs_link", "relevant_references", "faq_support"],
        "quality_fields": ["effectiveness", "clarity"],
        "allowed_fields": ["checklist", "quality", "evidences", "justifications", "suggested_improvements"],
    },
}


def normalize_present_categories(data: Any) -> Any:
    """
    Normaliza os valores de present_categories para '✔', '✖', ou 'N/A'
    Aceita: 'present'/'absent', 'true'/'false', '✔'/'✖', 'sim'/'não'
    
    Args:
        data: JSON parseado
        
    Returns:
        JSON com present_categories normalizados
    """
    if isinstance(data, dict):
        if 'structural_summary' in data and isinstance(data['structural_summary'], dict):
            ss = data['structural_summary']
            if 'present_categories' in ss and isinstance(ss['present_categories'], dict):
                pc = ss['present_categories']
                for key in pc.keys():
                    val = pc[key]
                    if isinstance(val, str):
                        val_lower = val.lower()
                        # Mapeia valores para símbolos normalizados
                        if val_lower in ['present', 'true', 'sim', 'yes', '1', 'v', 'y', '✔']:
                            pc[key] = '✔'
                        elif val_lower in ['absent', 'false', 'não', 'no', '0', 'n', '✖']:
                            pc[key] = '✖'
                        elif val_lower in ['n/a', 'na']:
                            pc[key] = 'N/A'
    return data


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
                    except (ValueError, TypeError):
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
    Também corrige a estrutura de 'quality' que pode estar incorreta.
    
    IMPORTANTE: A estrutura esperada varia por categoria:
    - who.quality.clarity: { note: 1-5, evidences: [], justifications: [] }  (OBJETO)
    - who.quality.consistency: { note: 1-5, evidences: [], justifications: [] }  (OBJETO)
    - when.quality.clarity: { note: 1-5, evidences: [], justifications: [] }  (OBJETO)
    - when.quality.consistency: { note: 1-5, evidences: [], justifications: [] }  (OBJETO)
    - license.quality.clarity: inteiro 1-5  (INTEIRO SIMPLES)
    - license.quality.consistency: inteiro 1-5  (INTEIRO SIMPLES)
    
    Args:
        data: JSON parseado (dict)
        
    Returns:
        JSON com campos não permitidos removidos e estrutura corrigida
    """
    if not isinstance(data, dict):
        return data
    
    # Corrige nomes de campos em structural_summary
    if 'structural_summary' in data and isinstance(data['structural_summary'], dict):
        ss = data['structural_summary']
        # Renomeia organization_observations para organization_notes
        if 'organization_observations' in ss:
            ss['organization_notes'] = ss.pop('organization_observations')
        # Renomeia general_observations para general_notes em metadata
    
    if 'metadata' in data and isinstance(data['metadata'], dict):
        md = data['metadata']
        # Renomeia general_observations para general_notes
        if 'general_observations' in md:
            md['general_notes'] = md.pop('general_observations')
    
    # Se tem a chave 'categories', processa cada categoria
    if 'categories' in data and isinstance(data['categories'], dict):
        for category_name, category_data in data['categories'].items():
            if isinstance(category_data, dict):
                # Determina quais campos são permitidos nesta categoria
                schema = CATEGORY_SCHEMAS.get(category_name)
                if not schema:
                    continue  # Pula categorias desconhecidas
                allowed = set(schema['allowed_fields'])
                
                # Remove campos não permitidos
                fields_to_remove = []
                for field in category_data.keys():
                    if field not in allowed:
                        fields_to_remove.append(field)
                
                for field in fields_to_remove:
                    del category_data[field]
                
                # Normaliza valores do checklist (convert 'present'/'absent' to '✔'/'✖')
                if 'checklist' in category_data and isinstance(category_data['checklist'], dict):
                    checklist = category_data['checklist']
                    for check_key in checklist.keys():
                        val = checklist[check_key]
                        if isinstance(val, str):
                            val_lower = val.lower()
                            if val_lower in ['present', 'true', 'sim', 'yes', '1', '✔']:
                                checklist[check_key] = '✔'
                            elif val_lower in ['absent', 'false', 'não', 'no', '0', '✖']:
                                checklist[check_key] = '✖'
                            elif val_lower in ['n/a', 'na']:
                                checklist[check_key] = 'N/A'
                
                # Corrige a estrutura de 'quality' se necessário
                if 'quality' in category_data and isinstance(category_data['quality'], dict):
                    quality = category_data['quality']
                    expected_quality_fields = schema.get('quality_fields', [])
                    
                    # Para 'license': quality.clarity e quality.consistency DEVEM ser INTEIROS
                    if category_name == 'license':
                        for key in expected_quality_fields:
                            if key in quality:
                                val = quality[key]
                                # Se é um objeto com 'note', extrai o valor numérico
                                if isinstance(val, dict):
                                    if 'note' in val:
                                        quality[key] = int(val['note'])
                                    else:
                                        # Se não tem 'note', pega o primeiro valor numérico
                                        for v in val.values():
                                            if isinstance(v, (int, float)):
                                                quality[key] = int(v)
                                                break
                                        else:
                                            quality[key] = 3  # Default
                                # Se é string, converte
                                elif isinstance(val, str):
                                    try:
                                        quality[key] = int(val)
                                    except (ValueError, TypeError):
                                        quality[key] = 3  # Default
                                # Se já é inteiro, mantém
                                elif not isinstance(val, (int, float)):
                                    quality[key] = 3
                    
                    # Para outras categorias: quality fields DEVEM ser OBJETOS com {note, evidences, justifications}
                    else:
                        for key in expected_quality_fields:
                            if key in quality:
                                val = quality[key]
                                # Se NÃO é dict, converte
                                if not isinstance(val, dict):
                                    try:
                                        note_val = int(val) if isinstance(val, (int, str, float)) else 3
                                    except (ValueError, TypeError):
                                        note_val = 3
                                    quality[key] = {
                                        "note": note_val,
                                        "evidences": [],
                                        "justifications": []
                                    }
                                else:
                                    # É um dict, garante estrutura correta
                                    if "note" not in val:
                                        note_val = 3
                                        for v in val.values():
                                            if isinstance(v, int) and 1 <= v <= 5:
                                                note_val = v
                                                break
                                        val["note"] = note_val
                                    elif not isinstance(val.get("note"), int):
                                        try:
                                            val["note"] = int(val["note"])
                                        except (ValueError, TypeError):
                                            val["note"] = 3
                                    
                                    if "evidences" not in val:
                                        val["evidences"] = []
                                    elif isinstance(val["evidences"], str):
                                        val["evidences"] = [val["evidences"]]
                                    
                                    if "justifications" not in val:
                                        val["justifications"] = []
                                    elif isinstance(val["justifications"], str):
                                        val["justifications"] = [val["justifications"]]
    
    # Processa dimensions_summary: garante que todos os campos sejam objetos {note, evidences, justifications}
    if 'dimensions_summary' in data and isinstance(data['dimensions_summary'], dict):
        ds = data['dimensions_summary']
        expected_dims = ['quality', 'appeal', 'readability', 'understandability', 'structure', 
                        'cohesion', 'conciseness', 'effectiveness', 'consistency', 'clarity']
        
        for dim_name in expected_dims:
            if dim_name in ds:
                val = ds[dim_name]
                # Se NÃO é dict, converte para objeto
                if not isinstance(val, dict):
                    try:
                        note_val = int(val) if isinstance(val, (int, str, float)) else 3
                    except (ValueError, TypeError):
                        note_val = 3
                    ds[dim_name] = {
                        "note": note_val,
                        "evidences": [],
                        "justifications": []
                    }
                else:
                    # É um dict, garante estrutura correta
                    if "note" not in val:
                        note_val = 3
                        for v in val.values():
                            if isinstance(v, int) and 1 <= v <= 5:
                                note_val = v
                                break
                        val["note"] = note_val
                    elif not isinstance(val.get("note"), int):
                        try:
                            val["note"] = int(val["note"])
                        except (ValueError, TypeError):
                            val["note"] = 3
                    
                    if "evidences" not in val:
                        val["evidences"] = []
                    elif isinstance(val["evidences"], str):
                        val["evidences"] = [val["evidences"]]
                    
                    if "justifications" not in val:
                        val["justifications"] = []
                    elif isinstance(val["justifications"], str):
                        val["justifications"] = [val["justifications"]]
    
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
    fixed_json = normalize_present_categories(json_obj)
    fixed_json = remove_disallowed_category_fields(fixed_json)
    fixed_json = fix_string_arrays_in_json(fixed_json)
    
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
            "general_notes": "Test"
        },
        "structural_summary": {
            "detected_sections": ["Section 1"],
            "present_categories": {
                "what": "present",  # Será convertido para ✔
                "why": "present",
                "how_installation": "present",
                "how_usage": "absent",  # Será convertido para ✖
                "how_config_requirements": "present",
                "when": "absent",
                "who": "absent",
                "license": "absent",
                "contribution": "absent",
                "references": "present",
                "other": "N/A"
            },
            "organization_notes": "Test"
        },
        "categories": {
            "what": {
                "checklist": {"clear_description": "present", "features_scope": "present", "target_audience": "present"},
                "quality": {
                    "clarity": {"note": 5, "evidences": [], "justifications": []},
                    "understandability": {"note": 5, "evidences": [], "justifications": []},
                    "conciseness": {"note": 4, "evidences": [], "justifications": []},
                    "consistency": {"note": 5, "evidences": [], "justifications": []}
                },
                "evidences": ["Evidence 1"],
                "justifications": "This is a string instead of array",  # Será convertido para array
                "suggested_improvements": []
            }
        },
        "dimensions_summary": {
            "quality": {"note": 4, "evidences": [], "justifications": []},
            "appeal": {"note": 4, "evidences": [], "justifications": []},
            "readability": {"note": 4, "evidences": [], "justifications": []},
            "understandability": {"note": 4, "evidences": [], "justifications": []},
            "structure": {"note": 4, "evidences": [], "justifications": []},
            "cohesion": {"note": 4, "evidences": [], "justifications": []},
            "conciseness": {"note": 4, "evidences": [], "justifications": []},
            "effectiveness": {"note": 4, "evidences": [], "justifications": []},
            "consistency": {"note": 4, "evidences": [], "justifications": []},
            "clarity": {"note": 4, "evidences": [], "justifications": []},
            "global_notes": "Test notes"
        },
        "executive_summary": {
            "strengths": [],
            "weaknesses": [],
            "critical_gaps": [],
            "priority_recommendations": []
        }
    }
    
    # Testa o fix
    print("Testando post-processor de JSON...")
    print("\n1. Antes do fix:")
    print(f"   justifications type: {type(test_data['categories']['what']['justifications'])}")
    
    fixed = fix_string_arrays_in_json(test_data)
    
    print("\n2. Depois do fix:")
    print(f"   justifications type: {type(fixed['categories']['what']['justifications'])}")
    print(f"   Valor: {fixed['categories']['what']['justifications']}")
