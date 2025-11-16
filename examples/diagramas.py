#!/usr/bin/env python
"""
Visual Diagrams of the Evaluation Pipeline

Este script imprime diagramas ASCII para visualizar o fluxo.
"""

def print_pipeline():
    """Imprime o pipeline de 4 estágios"""
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                   PIPELINE DE AVALIAÇÃO (4 ESTÁGIOS)                      ║
╚═══════════════════════════════════════════════════════════════════════════╝

README TEXT (Markdown)
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ ESTÁGIO 1: BUILDING_PROMPT (25%)                               │
│ • Carrega schema JSON                                           │
│ • Monta prompt com: schema + readme + exemplo                  │
│ • Duração: ~100-500ms                                          │
│ Falhas: schema não encontrado                                  │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ ESTÁGIO 2: CALLING_MODEL (75%)                                 │
│ • Chama Gemini 2.5 Flash                                       │
│ • Passa prompt + max_tokens=2048 + temperature=0.0             │
│ • Duração: ~2-10s (95% do tempo total)                         │
│ Falhas: API key, rate limit, rede, resposta vazia             │
│ Fallback: Detecta resposta vazia → skipa parsing/validating   │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ ESTÁGIO 3: PARSING_JSON (90%)                                  │
│ • Faz json.loads(model_response)                               │
│ • Duração: ~10-50ms                                            │
│ Falhas: JSON inválido, markdown code blocks, múltiplos JSON    │
│ Fallback: Loga snippet de 200 chars, skipa validating         │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ ESTÁGIO 4: VALIDATING (95%)                                    │
│ • Valida contra schema usando jsonschema                       │
│ • Verifica tipos, campos obrigatórios, constraints             │
│ • Duração: ~50-200ms                                           │
│ Falhas: Validação de schema falhou                             │
│ Fallback: Capture error path, adiciona suggestion              │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ RESULTADO: EvaluationResult                                    │
│ • success: bool                                                │
│ • prompt: str                                                  │
│ • model_output: str                                            │
│ • parsed: dict (JSON)                                          │
│ • validation_ok: bool                                          │
│ • progress_history: list[ProgressUpdate]                       │
│ • timing: dict (prompt_build, model_call, parsing, etc)       │
│ • recovery_suggestions: list[str]                              │
└─────────────────────────────────────────────────────────────────┘
    """)


def print_two_modes():
    """Imprime diagrama dos dois modos de uso"""
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                        DOIS MODOS DE USO                                  ║
╚═══════════════════════════════════════════════════════════════════════════╝

MODO 1: DIRETO (Direct Call)
════════════════════════════════════════════════════════════════════════════

    Python Code
        ↓
    result = extract_json_from_readme(
        readme_text="...",
        progress_callback=on_progress,  ← Função que recebe updates
    )
        ↓
    for update in result.progress_history:
        print(f"{update.percentage}% - {update.message}")
    
    Vantagens:
    • Simples e síncrono
    • Callback em tempo real
    • Controle total
    • Ideal para: testes, scripts, debug
    
    Desvantagens:
    • Bloqueia durante execução
    • Não ideal para web


MODO 2: SSE STREAMING (Server-Sent Events)
════════════════════════════════════════════════════════════════════════════

    Browser Client
        ↓
    POST /extract-json-stream
        ↓
    ┌─ FastAPI endpoint
    │
    ├─ run_in_executor(thread)
    │   └─ extract_json_from_readme()
    │       ├─ progress_callback → queue.Queue
    │       ├─ emit: progress update 1
    │       ├─ emit: progress update 2
    │       ├─ emit: progress update 3
    │       └─ return EvaluationResult
    │
    ├─ async progress_generator()
    │   ├─ consome queue.get()
    │   ├─ yield "data: {...progress...}\\n\\n"
    │   ├─ consome queue.get()
    │   ├─ yield "data: {...progress...}\\n\\n"
    │   └─ yield "data: {...result...}\\n\\n"
    │
    └─ StreamingResponse
        ↓
    EventListener (browser)
    ├─ onmessage → progress
    │   ├─ update progress bar (0-100%)
    │   ├─ update stage timeline
    │   └─ update status message
    └─ onmessage → result
        ├─ show final JSON
        ├─ show validation status
        └─ show recovery suggestions

    Vantagens:
    • Não bloqueia
    • Streaming em tempo real
    • Melhor UX
    • Escalável
    • Ideal para: web, produção
    
    Desvantagens:
    • Mais complexo
    • Requer EventSource ou fetch com ReadableStream
    • IE não suporta EventSource


COMPARAÇÃO LADO A LADO
════════════════════════════════════════════════════════════════════════════

┌─────────────────┬──────────────────────────┬──────────────────────────┐
│ Característica  │ Modo 1 (Direto)          │ Modo 2 (SSE)             │
├─────────────────┼──────────────────────────┼──────────────────────────┤
│ Bloqueante      │ ✓ Sim (OK para testes)   │ ✗ Não (melhor para web) │
│ Tempo Real      │ ✓ Sim (callbacks)        │ ✓ Sim (streaming)        │
│ Simplicidade    │ ✓ Muito simples          │ ~ Moderado (mais código) │
│ Uso             │ Testes, scripts, debug   │ Web, produção, frontend  │
│ Escalabilidade  │ ~ Limitada (uma thread)  │ ✓ Excelente (async)      │
│ Latência        │ ~ Média (callbacks)      │ ✓ Baixa (streaming)      │
└─────────────────┴──────────────────────────┴──────────────────────────┘

    """)


def print_error_handling():
    """Imprime diagrama de tratamento de erros"""
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                      TRATAMENTO DE ERROS                                  ║
╚═══════════════════════════════════════════════════════════════════════════╝

ERRO 1: Resposta Vazia do Modelo
────────────────────────────────────────────────────────────────────────────

    CALLING_MODEL
        ↓
    raw = client.generate(...)  → ""  (vazio)
        ↓
    Detecta: if not raw or not raw.strip()
        ↓
    tracker.error_stage(ProgressStage.CALLING_MODEL)
        ↓
    Skipa: PARSING_JSON
    Skipa: VALIDATING
        ↓
    recovery_suggestion: "Model returned empty response. Check API key, 
                          rate limits, or try again."
        ↓
    result.success = False


ERRO 2: JSON Inválido
────────────────────────────────────────────────────────────────────────────

    PARSING_JSON
        ↓
    json.loads(raw)  → JSONDecodeError
        ↓
    Detecta: except json.JSONDecodeError
        ↓
    Log com snippet: raw[:200]
        ↓
    tracker.error_stage(ProgressStage.PARSING_JSON)
        ↓
    Skipa: VALIDATING
        ↓
    recovery_suggestion: "Model output was not valid JSON. 
                          Try with a different model or adjust temperature."
        ↓
    result.success = False
    result.parsed = None


ERRO 3: Validação de Schema Falhou
────────────────────────────────────────────────────────────────────────────

    VALIDATING
        ↓
    jsonschema.validate(parsed, schema)  → ValidationError
        ↓
    Detecta: except jsonschema.ValidationError
        ↓
    Extrai path: error.path = ["features", 0, "name"]
        ↓
    tracker.error_stage(ProgressStage.VALIDATING)
        ↓
    recovery_suggestion: "Field validation failed at: features.0.name"
        ↓
    result.success = False
    result.validation_ok = False


FLUXO DE RECUPERAÇÃO
────────────────────────────────────────────────────────────────────────────

    Usuário recebe result com:
    • success = False
    • recovery_suggestions = [
        "Model returned empty response. Check API key, rate limits, 
         or try again.",
      ]
        ↓
    Frontend mostra:
    ✗ Evaluation failed
    💡 Suggestion: Check API key, rate limits, or try again
    
    [Retry Button] ← Tentar novamente
    
    OU usuário ajusta:
    • GEMINI_API_KEY
    • Temperature
    • Prompt
    • Schema
        ↓
    Tenta novamente

    """)


def print_timing_breakdown():
    """Imprime breakdown de timing"""
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                       BREAKDOWN DE TIMING                                 ║
╚═══════════════════════════════════════════════════════════════════════════╝

Exemplo: Avaliar README do Keras
────────────────────────────────────────────────────────────────────────────

Timing esperado por estágio:

    BUILDING_PROMPT    :  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  (0.18s / 3%)
    CALLING_MODEL      :  ███████████████████████████████░░░░░░░░  (5.23s / 92%)
    PARSING_JSON       :  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  (0.08s / 1%)
    VALIDATING         :  ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  (0.18s / 3%)
                          ─────────────────────────────────────────────────
    TOTAL              :  5.67s

Breakdown:
    ┌─────────────────┬───────┬────────┐
    │ Estágio         │ Tempo │ % do Total │
    ├─────────────────┼───────┼────────┤
    │ building_prompt │ 0.18s │ 3%     │
    │ calling_model   │ 5.23s │ 92%    │ ← A maioria!
    │ parsing         │ 0.08s │ 1%     │
    │ validation      │ 0.18s │ 3%     │
    ├─────────────────┼───────┼────────┤
    │ TOTAL           │ 5.67s │ 100%   │
    └─────────────────┴───────┴────────┘

Insights:
✓ 92% do tempo é CALLING_MODEL (rede para Gemini API)
✓ 8% é tudo mais (CPU local)
✓ Para melhorar velocidade: otimizar prompt ou usar modelo mais rápido


Percentuais de Progresso (para UI):
────────────────────────────────────────────────────────────────────────────

0%   ├─ Iniciando
     ├─ BUILDING_PROMPT ...
25%  ├─ Prompt construído
     ├─ CALLING_MODEL ...
75%  ├─ Modelo respondeu
     ├─ PARSING_JSON ...
90%  ├─ JSON parseado
     ├─ VALIDATING ...
95%  ├─ Validação completa
     ├─ COMPLETED
100% └─ Pronto!


Exemplo de Timing Real (JSON):
────────────────────────────────────────────────────────────────────────────

{
  "timing": {
    "prompt_build": 0.18,      // Segundos para montar prompt
    "model_call": 5.23,        // Segundos para chamar API + receber
    "parsing": 0.08,           // Segundos para fazer json.loads()
    "validation": 0.18,        // Segundos para validar schema
    "total": 5.67              // Tempo total
  },
  "progress_history": [
    {
      "stage": "building_prompt",
      "status": "completed",
      "percentage": 25,
      "elapsed_seconds": 0.18,
      "estimated_remaining_seconds": 5.49
    },
    {
      "stage": "calling_model",
      "status": "completed",
      "percentage": 75,
      "elapsed_seconds": 5.42,
      "estimated_remaining_seconds": 0.25
    },
    ...
  ]
}

    """)


def print_all():
    """Imprime todos os diagramas"""
    print_pipeline()
    print_two_modes()
    print_error_handling()
    print_timing_breakdown()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "pipeline":
            print_pipeline()
        elif sys.argv[1] == "modes":
            print_two_modes()
        elif sys.argv[1] == "errors":
            print_error_handling()
        elif sys.argv[1] == "timing":
            print_timing_breakdown()
        else:
            print("Uso: python diagramas.py [pipeline|modes|errors|timing]")
    else:
        print_all()
