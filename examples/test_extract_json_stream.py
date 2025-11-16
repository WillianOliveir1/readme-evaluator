#!/usr/bin/env python
"""
Test script demonstrating how to:
1. Run the extract_json_from_readme function directly
2. Test the /extract-json-stream endpoint with real-time progress
3. Understand the evaluation pipeline

ESTRATÉGIA:
- Esta solução oferece duas formas de usar o módulo evaluate:
  
  a) DIRETO (Direct):
     - Importar extract_json_from_readme()
     - Passar progress_callback para receber updates em tempo real
     - Útil para testes unitários e integração
  
  b) VIA HTTP (SSE Streaming):
     - POST para /extract-json-stream
     - Recebe Server-Sent Events com progresso
     - Útil para interface web real-time
"""
from __future__ import annotations

import os
import sys
import json
import time
from typing import Optional

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.evaluate.extractor import extract_json_from_readme
from backend.evaluate.progress import ProgressUpdate, ProgressTracker
from backend.download.download import ReadmeDownloader


def example_1_direct_evaluation():
    """
    EXEMPLO 1: Chamar extract_json_from_readme diretamente
    
    Use case: Testes, integração, scripts batch
    """
    print("\n" + "=" * 80)
    print("EXEMPLO 1: Avaliação Direta (Direct Evaluation)")
    print("=" * 80)
    
    # Simular readme_text
    readme_text = """
    # MyProject
    
    MyProject is a Python library for data science.
    
    ## Features
    - Fast processing
    - Easy to use
    - Open source
    
    ## Installation
    ```
    pip install myproject
    ```
    """
    
    # Lista para coletar updates
    progress_updates = []
    
    def on_progress(update: ProgressUpdate):
        """Callback que recebe cada atualização de progresso"""
        print(f"  [{update.percentage:3d}%] {update.stage.value:20s} | {update.message}")
        progress_updates.append(update)
    
    print("\nCalling extract_json_from_readme with progress callback...")
    print("(Note: Sem modelo, apenas construção de prompt)")
    
    result = extract_json_from_readme(
        readme_text=readme_text,
        schema_path="schemas/taxonomia.schema.json",
        model=None,  # Sem modelo por enquanto
        progress_callback=on_progress,
    )
    
    print(f"\n✓ Evaluation complete!")
    print(f"  Success: {result.success}")
    print(f"  Prompt length: {len(result.prompt)} chars")
    print(f"  Stages completed: {len(result.progress_history)}")
    print(f"  Total time: {result.timing.get('total', 0):.2f}s")
    
    return result


def example_2_with_gemini():
    """
    EXEMPLO 2: Com modelo Gemini (requer GEMINI_API_KEY)
    
    Use case: Avaliação completa com parsing e validação
    """
    print("\n" + "=" * 80)
    print("EXEMPLO 2: Avaliação com Gemini 2.5 Flash")
    print("=" * 80)
    
    if not os.environ.get("GEMINI_API_KEY"):
        print("⚠ GEMINI_API_KEY não definida. Pulando este exemplo.")
        print("  Para testar: export GEMINI_API_KEY=sk-...")
        return None
    
    # Usar README do Keras
    readme_path = "backend/examples/pandas-dev-pandas-README.md"
    
    if not os.path.exists(readme_path):
        print(f"⚠ Arquivo não encontrado: {readme_path}")
        return None
    
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_text = f.read()
    
    print(f"\nLendo: {readme_path}")
    print(f"Tamanho: {len(readme_text)} chars")
    
    progress_updates = []
    
    def on_progress(update: ProgressUpdate):
        """Callback para cada atualização"""
        status_symbol = {
            "in_progress": "▶",
            "completed": "✓",
            "error": "✗",
        }.get(update.status.value, "?")
        
        print(
            f"  [{update.percentage:3d}%] {status_symbol} "
            f"{update.stage.value:20s} | {update.message}"
        )
        if update.error:
            print(f"       Error: {update.error}")
        progress_updates.append(update)
    
    print("\nCalling extract_json_from_readme with Gemini model...")
    print("Stages:")
    
    start = time.time()
    result = extract_json_from_readme(
        readme_text=readme_text,
        schema_path="schemas/taxonomia.schema.json",
        model="gemini-2.5-flash",
        max_tokens=2048,
        temperature=0.0,
        progress_callback=on_progress,
    )
    total_time = time.time() - start
    
    print(f"\n✓ Evaluation complete in {total_time:.2f}s")
    print(f"  Success: {result.success}")
    print(f"  Prompt length: {len(result.prompt)} chars")
    print(f"  Model output length: {len(result.model_output or '')} chars")
    print(f"  JSON parsed: {result.parsed is not None}")
    print(f"  Schema valid: {result.validation_ok}")
    
    if result.validation_errors:
        print(f"  Validation errors: {result.validation_errors}")
    
    if result.recovery_suggestions:
        print(f"  Recovery suggestions:")
        for suggestion in result.recovery_suggestions:
            print(f"    - {suggestion}")
    
    print(f"\n  Timing breakdown:")
    for stage, duration in result.timing.items():
        print(f"    - {stage}: {duration:.2f}s")
    
    return result


def example_3_download_and_evaluate():
    """
    EXEMPLO 3: Baixar README do GitHub e avaliar
    
    Use case: Pipeline completo: download + evaluate
    """
    print("\n" + "=" * 80)
    print("EXEMPLO 3: Download + Evaluate Pipeline")
    print("=" * 80)
    
    repo_url = "https://github.com/keras-team/keras"
    
    print(f"\nDownloading README from: {repo_url}")
    
    try:
        dl = ReadmeDownloader()
        readme_path = dl.download(repo_url)
        print(f"✓ Downloaded to: {readme_path}")
        
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_text = f.read()
        
        print(f"  Size: {len(readme_text)} chars")
        
        # Mostrar primeira parte do README
        print(f"\n  First 500 chars:")
        print(f"  {readme_text[:500]}")
        
        # Avaliar sem modelo primeiro (apenas prompt)
        print(f"\nEvaluating (without model for now)...")
        
        progress_updates = []
        
        def on_progress(update: ProgressUpdate):
            progress_updates.append(update)
            print(f"  [{update.percentage:3d}%] {update.stage.value}")
        
        result = extract_json_from_readme(
            readme_text=readme_text,
            schema_path="schemas/taxonomia.schema.json",
            model=None,
            progress_callback=on_progress,
        )
        
        print(f"\n✓ Evaluation complete!")
        print(f"  Stages: {len(result.progress_history)}")
        print(f"  Prompt built: {len(result.prompt)} chars")
        
        return result
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def example_4_streaming_simulation():
    """
    EXEMPLO 4: Simular o que a rota /extract-json-stream faz
    
    Use case: Entender o fluxo SSE
    """
    print("\n" + "=" * 80)
    print("EXEMPLO 4: Streaming Simulation (o que /extract-json-stream faz)")
    print("=" * 80)
    
    print("""
    A rota /extract-json-stream funciona assim:
    
    1. Cliente faz POST com ExtractRequest
    2. Backend inicia asyncio.run_in_executor (thread)
    3. Thread executa extract_json_from_readme com progress_callback
    4. Callback coloca eventos em queue.Queue
    5. Async generator consome queue e envia via SSE
    6. Frontend recebe event stream e atualiza UI em tempo real
    
    Fluxo de dados:
    
    POST /extract-json-stream
         ↓
    async progress_generator()
         ├─ run_in_executor(extract_json_from_readme)
         │   └─ Executa em thread separada
         │       └─ Chama progress_callback para cada evento
         │           └─ Coloca em progress_queue
         │
         ├─ Consome progress_queue
         │   ├─ Envia "data: {progress update}\n\n"
         │   ├─ Envia "data: {progress update}\n\n"
         │   └─ ... etc
         │
         └─ Envia resultado final
             └─ "data: {result}\n\n"
    
    Frontend (SSE EventSource):
    ├─ Recebe progress events
    │   ├─ Atualiza progress bar (0-100%)
    │   ├─ Mostra cards de stage
    │   └─ Mostra último message
    │
    └─ Recebe result event
        ├─ Para progress bar
        ├─ Mostra parsed JSON
        ├─ Mostra validation status
        └─ Mostra recovery suggestions
    """)
    
    print("\nPara testar a rota real, use:")
    print("""
    # Terminal 1: Inicie o servidor
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
    
    # Terminal 2: Faça uma requisição
    curl -N -H "Content-Type: application/json" \\
         -d '{"repo_url": "https://github.com/keras-team/keras"}' \\
         http://127.0.0.1:8000/extract-json-stream | grep "data:"
    
    Você verá linhas como:
    data: {"type":"progress","stage":"building_prompt","percentage":25,...}
    data: {"type":"progress","stage":"calling_model","percentage":75,...}
    data: {"type":"progress","stage":"parsing_json","percentage":90,...}
    data: {"type":"progress","stage":"validating","percentage":95,...}
    data: {"type":"result","result":{...}}
    """)


def example_5_run_all_examples():
    """
    EXEMPLO 5: Rodar todos os exemplos
    """
    print("\n" + "=" * 80)
    print("RODANDO TODOS OS EXEMPLOS")
    print("=" * 80)
    
    # Exemplo 1: Direto
    result1 = example_1_direct_evaluation()
    
    # Exemplo 2: Com Gemini
    result2 = example_2_with_gemini()
    
    # Exemplo 3: Download + Evaluate
    result3 = example_3_download_and_evaluate()
    
    # Exemplo 4: Streaming
    example_4_streaming_simulation()
    
    print("\n" + "=" * 80)
    print("RESUMO")
    print("=" * 80)
    print(f"Exemplo 1 (Direto): {'✓' if result1 and result1.success else '✗'}")
    print(f"Exemplo 2 (Gemini): {'✓' if result2 and result2.success else '✗ (API key não definida)'}")
    print(f"Exemplo 3 (Download): {'✓' if result3 and result3.success else '✗'}")
    print(f"\nPara testar /extract-json-stream:")
    print(f"  python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000")


if __name__ == "__main__":
    # Mudar para diretório raiz do projeto
    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    
    # Rodar exemplos
    if len(sys.argv) > 1:
        if sys.argv[1] == "1":
            example_1_direct_evaluation()
        elif sys.argv[1] == "2":
            example_2_with_gemini()
        elif sys.argv[1] == "3":
            example_3_download_and_evaluate()
        elif sys.argv[1] == "4":
            example_4_streaming_simulation()
        else:
            example_5_run_all_examples()
    else:
        example_5_run_all_examples()
