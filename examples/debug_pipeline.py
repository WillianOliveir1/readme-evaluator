#!/usr/bin/env python
"""
Debug Script: Testar módulo evaluate passo a passo

Este script executa o pipeline e mostra EXATAMENTE o que está acontecendo
em cada etapa:
  1. README capturado
  2. Prompt montado
  3. Enviado para o modelo
  4. Resposta recebida
  5. JSON parseado
  6. Validado
"""
from __future__ import annotations

import os
import sys
import json
import time
from typing import Optional
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Carregar .env
def load_env():
    """Carrega variáveis do arquivo .env"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

load_env()

from backend.download.download import ReadmeDownloader
from backend.evaluate.extractor import extract_json_from_readme
from backend.evaluate.progress import ProgressUpdate
from backend.evaluate.json_postprocessor import fix_string_arrays_in_json
from backend import prompt_builder
from backend.gemini_client import GeminiClient


def print_section(title):
    """Imprime seção"""
    print(f"\n{'='*80}")
    print(f"█ {title}")
    print(f"{'='*80}\n")


def print_step(number, title):
    """Imprime passo"""
    print(f"\n▶ PASSO {number}: {title}")
    print(f"{'─'*80}")


def print_success(msg):
    """Imprime sucesso"""
    print(f"✓ {msg}")


def print_error(msg):
    """Imprime erro"""
    print(f"✗ {msg}")


def print_info(msg):
    """Imprime info"""
    print(f"ℹ {msg}")


def test_step_1_download_readme():
    """PASSO 1: Baixar README do GitHub"""
    print_step(1, "Baixar README do GitHub")
    
    repo_url = "https://github.com/keras-team/keras"
    print_info(f"Repository: {repo_url}")
    
    try:
        print_info("Iniciando download...")
        dl = ReadmeDownloader()
        readme_path = dl.download(repo_url)
        print_success(f"README baixado com sucesso!")
        print_info(f"Caminho: {readme_path}")
        
        # Ler arquivo
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_text = f.read()
        
        print_success(f"Arquivo lido: {len(readme_text)} caracteres")
        
        # Mostrar preview
        print_info(f"\nPreview (primeiros 500 chars):")
        print(f"\n{readme_text[:500]}\n")
        print(f"{'...[truncado]...'}")
        
        return readme_text
        
    except Exception as e:
        print_error(f"Erro ao baixar: {e}")
        return None


def test_step_2_build_prompt(readme_text: str):
    """PASSO 2: Montar o prompt"""
    print_step(2, "Montar prompt com schema + README")
    
    schema_path = "schemas/taxonomia.schema.json"
    
    try:
        # Carregar schema
        print_info("Carregando schema...")
        schema_text = prompt_builder.PromptBuilder.load_schema_text(schema_path)
        print_success(f"Schema carregado: {len(schema_text)} caracteres")
        
        print_info(f"Preview do schema (primeiros 300 chars):")
        print(f"\n{schema_text[:300]}\n")
        
        # Montar prompt
        print_info("\nMontando prompt...")
        pb = prompt_builder.PromptBuilder(
            schema=schema_text,
            readme=readme_text
        )
        
        footer = (
            "IMPORTANT: The model must output a single JSON object, valid according to the schema above. "
            "No surrounding backticks, no markdown, no commentary."
        )
        
        prompt = pb.build(instruction=None, footer=footer)
        print_success(f"Prompt montado: {len(prompt)} caracteres")
        
        print_info(f"Preview do prompt (primeiros 500 chars):")
        print(f"\n{prompt[:500]}\n")
        print(f"{'...[truncado]...'}")
        print_info(f"Últimos 300 chars:")
        print(f"\n{prompt[-300:]}\n")
        
        return prompt
        
    except Exception as e:
        print_error(f"Erro ao montar prompt: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_step_3_call_model(prompt: str):
    """PASSO 3: Enviar prompt para o modelo"""
    print_step(3, "Chamar Gemini 2.5 Flash com o prompt")
    
    # Verificar API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print_error("GEMINI_API_KEY não definida!")
        print_info("Procurando em:")
        print_info("  1. Variável de ambiente: export GEMINI_API_KEY='sk-...'")
        print_info("  2. Arquivo .env na raiz do projeto")
        print_info("  3. Arquivo .env em backend/")
        return None
    
    print_success("GEMINI_API_KEY encontrada ✓")
    
    try:
        print_info("Inicializando GeminiClient...")
        client = GeminiClient()
        
        print_info(f"Enviando prompt para {client.default_model}...")
        print_info(f"Configuração:")
        print_info(f"  - max_tokens: 20480")
        print_info(f"  - temperature: 0.0")
        
        start_time = time.time()
        response = client.generate(
            prompt,
            model="gemini-2.5-flash",
            max_tokens=20480,
            temperature=0.0
        )
        elapsed = time.time() - start_time
        
        print_success(f"Resposta recebida em {elapsed:.2f}s!")
        print_success(f"Tamanho da resposta: {len(response)} caracteres")
        
        # Mostrar resposta completa
        print_info(f"\nRESPOSTA COMPLETA DO MODELO:")
        print(f"\n{response}\n")
        
        return response
        
    except Exception as e:
        print_error(f"Erro ao chamar modelo: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_step_4_parse_json(response: str):
    """PASSO 4: Fazer parse do JSON"""
    print_step(4, "Fazer parse do JSON da resposta")
    
    if not response:
        print_error("Resposta vazia do modelo")
        return None
    
    if not response.strip():
        print_error("Resposta contém apenas espaços em branco")
        return None
    
    # Remover backticks markdown se houver
    cleaned_response = response.strip()
    if cleaned_response.startswith("```json"):
        cleaned_response = cleaned_response[7:]  # Remove ```json
    elif cleaned_response.startswith("```"):
        cleaned_response = cleaned_response[3:]  # Remove ```
    
    if cleaned_response.endswith("```"):
        cleaned_response = cleaned_response[:-3]  # Remove trailing ```
    
    cleaned_response = cleaned_response.strip()
    
    try:
        print_info("Fazendo json.loads() na resposta...")
        parsed = json.loads(cleaned_response)
        
        print_success("JSON parseado com sucesso!")
        
        # Mostrar JSON formatado
        print_info("\nJSON PARSEADO (formatado):")
        print(f"\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n")
        
        return parsed
        
    except json.JSONDecodeError as e:
        print_error(f"Erro ao fazer parse: {e}")
        print_info(f"Posição do erro: linha {e.lineno}, coluna {e.colno}")
        print_info(f"Mensagem: {e.msg}")
        
        # Mostrar snippet de onde foi o erro
        lines = response.split('\n')
        if e.lineno <= len(lines):
            error_line = lines[e.lineno - 1]
            print_info(f"\nLinha do erro:")
            print(f"  {error_line}")
            print(f"  {' ' * (e.colno - 1)}^")
        
        print_info(f"\nResposta completa (para debug):")
        print(f"\n{response}\n")
        
        return None


def test_step_5_validate_schema(parsed: dict):
    """PASSO 5: Validar contra schema"""
    print_step(5, "Validar JSON contra schema")
    
    if not parsed:
        print_error("JSON não foi parseado")
        return False
    
    try:
        import jsonschema
        
        schema_path = "schemas/taxonomia.schema.json"
        print_info("Carregando schema: schemas/taxonomia.schema.json")
        
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        
        # Aplicar post-processing antes de validar
        print_info("Aplicando correções automáticas (fix arrays)...")
        fixed_parsed = fix_string_arrays_in_json(parsed)
        print_success("Correções aplicadas!")
        
        print_info("Validando JSON contra schema...")
        jsonschema.validate(instance=fixed_parsed, schema=schema)
        
        print_success("✓ JSON validado com sucesso contra o schema!")
        return True
        
    except jsonschema.ValidationError as e:
        print_error("✗ Erro de validação de schema:")
        print_info(f"  Mensagem: {e.message}")
        print_info(f"  Path: {list(e.path)}")
        
        # Mostrar o que foi validado
        print_info("\n  Instância onde falhou:")
        print(f"  {e.instance}")
        
        return False
        
    except Exception as e:
        print_error(f"Erro ao validar: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_pipeline():
    """Rodar o pipeline completo"""
    print_section("DEBUG PIPELINE COMPLETO")
    print_info("Este script vai testar cada etapa do pipeline")
    print_info("e mostrar EXATAMENTE o que está acontecendo")
    
    # Passo 1: Download
    readme_text = test_step_1_download_readme()
    if not readme_text:
        return
    
    # Passo 2: Montar prompt
    prompt = test_step_2_build_prompt(readme_text)
    if not prompt:
        return
    
    # Passo 3: Chamar modelo
    response = test_step_3_call_model(prompt)
    if not response:
        return
    
    # Passo 4: Parse JSON
    parsed = test_step_4_parse_json(response)
    if not parsed:
        return
    
    # Passo 5: Validar schema
    validation_ok = test_step_5_validate_schema(parsed)
    
    # Resumo final
    print_section("RESUMO FINAL")
    print_info("Pipeline executado com sucesso!")
    print_info(f"  ✓ README capturado: {len(readme_text)} chars")
    print_info(f"  ✓ Prompt montado: {len(prompt)} chars")
    print_info(f"  ✓ Resposta do modelo: {len(response)} chars")
    print_info(f"  ✓ JSON parseado")
    print_info(f"  {'✓' if validation_ok else '✗'} Schema {'validado' if validation_ok else 'INVÁLIDO'}")


def test_with_progress_callback():
    """Teste alternativo: usar a função extract_json_from_readme com callbacks"""
    print_section("TESTE ALTERNATIVO: Com progress callbacks")
    
    repo_url = "https://github.com/keras-team/keras"
    
    print_info(f"Repository: {repo_url}")
    print_info("Baixando README...")
    
    try:
        dl = ReadmeDownloader()
        readme_path = dl.download(repo_url)
        
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_text = f.read()
        
        print_success(f"README capturado: {len(readme_text)} chars")
        
        # Definir callback para ver progresso
        def on_progress(update: ProgressUpdate):
            status = {
                "in_progress": "▶",
                "completed": "✓",
                "error": "✗",
            }.get(update.status.value, "?")
            
            print(f"  [{update.percentage:3d}%] {status} {update.stage.value:20s} | {update.message}")
            
            if update.error:
                print(f"       Error: {update.error}")
        
        print("\nExecutando extract_json_from_readme com callbacks...")
        
        start = time.time()
        result = extract_json_from_readme(
            readme_text=readme_text,
            schema_path="schemas/taxonomia.schema.json",
            model="gemini-2.5-flash",
            progress_callback=on_progress,
        )
        elapsed = time.time() - start
        
        print_success(f"\nExecução completa em {elapsed:.2f}s")
        print_info(f"Resultado:")
        print_info(f"  Success: {result.success}")
        print_info(f"  Prompt length: {len(result.prompt)}")
        print_info(f"  Model output length: {len(result.model_output or '')}")
        print_info(f"  JSON parsed: {result.parsed is not None}")
        print_info(f"  Validation OK: {result.validation_ok}")
        
        if result.parsed:
            print_info(f"\nJSON parseado:")
            print(f"  {json.dumps(result.parsed, indent=2, ensure_ascii=False)}")
        
        if result.validation_errors:
            print_error(f"\nErros de validação:")
            print(f"  {result.validation_errors}")
        
        if result.recovery_suggestions:
            print_info(f"\nSugestões de recuperação:")
            for suggestion in result.recovery_suggestions:
                print(f"  • {suggestion}")
        
        print_info(f"\nTiming:")
        for stage, duration in result.timing.items():
            print(f"  {stage}: {duration:.2f}s")
        
    except Exception as e:
        print_error(f"Erro: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Debug evaluate module")
    parser.add_argument(
        "--mode",
        choices=["full", "callback"],
        default="full",
        help="Modo de teste"
    )
    
    args = parser.parse_args()
    
    # Mudar para diretório raiz
    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    
    if args.mode == "full":
        test_full_pipeline()
    else:
        test_with_progress_callback()
