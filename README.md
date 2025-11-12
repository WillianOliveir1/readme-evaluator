 # readme-evaluator — Guia de instalação e execução

Este repositório contém um backend em Python (FastAPI) e um frontend Next.js para avaliar READMEs e extrair uma taxonomia JSON baseada em um esquema canônico.

Este README mostra passo a passo como instalar dependências e executar o projeto em um ambiente Windows (cmd.exe). Ajuste comandos para outras shells/OS quando necessário.

## Pré-requisitos

- Python 3.10+ instalado e disponível no PATH
- Node.js 18+ / npm (para a parte frontend)
- Git (opcional)

## Visão geral dos diretórios importantes

- `backend/` — código Python (FastAPI, cliente HF, extrator, renderizador)
- `frontend/` — aplicação Next.js (UI)
- `schemas/` — esquema JSON canônico usado pelo prompt
- `backend/examples/` — exemplos de README e JSON de saída

## 1) Preparar o ambiente Python (backend)

Abra um terminal (cmd.exe) no diretório do projeto.

1. Crie e ative um virtualenv (recomendado):

```cmd
python -m venv .venv
.venv\Scripts\activate
```

2. Instale dependências do backend:

```cmd
pip install --upgrade pip
pip install -r backend/requirements.txt
```

3. (Opcional) Se preferir, instale ferramentas de lint/test localmente:

```cmd
pip install flake8 pytest
```

## 2) Configurar variáveis de ambiente

O projeto usa a variável `HUGGINGFACE_API_TOKEN` para chamar a API de inferência. Existem duas opções:

- Exportar no terminal (temporário):

```cmd
set HUGGINGFACE_API_TOKEN=hf_...seu_token_aqui...
```

- Ou criar um arquivo `.env` na raiz do projeto com a linha:

```text
HUGGINGFACE_API_TOKEN=hf_...seu_token_aqui...
```

O backend usa `os.environ` para ler a variável; se você criar `.env` garanta que o processo que inicia o app carregue esse arquivo (por exemplo, usando `python-dotenv` em scripts de execução, ou definindo a variável no ambiente).

> Nota: em ambientes corporativos a rede pode bloquear acesso a huggingface.co — se tiver problemas de conexão, teste a partir de uma rede diferente (por exemplo hotspot) ou configure proxy apropriado.

## 3) Executar o backend (FastAPI)

No terminal (com o virtualenv ativado):

```cmd
# executa o servidor em http://127.0.0.1:8000
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Endpoints úteis:

- `POST /readme` — baixar README a partir de um repositório GitHub. Body JSON: `{ "repo_url": "https://github.com/owner/repo" }`
- `POST /extract-json` — extrai JSON estruturado (forneça `readme_text` ou `repo_url`). Se `model` estiver vazio, retorna apenas o prompt construído.
- `POST /render` — renderiza texto a partir do JSON validado.
- `POST /generate` — endpoint genérico que passa o `prompt` para o Hugging Face Inference API (requer token).

Exemplo rápido usando `curl` (atenção ao escaping no Windows cmd):

```cmd
curl -X POST http://127.0.0.1:8000/extract-json -H "Content-Type: application/json" -d "{\"readme_text\": \"L0001: # Example\nL0002: ...\"}"
```

Se preferir Python para chamadas às APIs, um exemplo mínimo usando `requests`:

```py
import requests
resp = requests.post('http://127.0.0.1:8000/extract-json', json={'readme_text': 'L0001: # Example\nL0002: ...'})
print(resp.json())
```

## 4) Executar o runner de prompt (CLI)

Existe um utilitário CLI que monta o prompt de extração e pode chamar o modelo:

```cmd
# apenas constrói o prompt e mostra um preview
python backend/run_pipeline.py --readme backend/examples/sample_readme_for_model.md --schema schemas/taxonomia.schema.json

# chama o modelo (requer HUGGINGFACE_API_TOKEN no ambiente)
python backend/run_pipeline.py --readme backend/examples/sample_readme_for_model.md --schema schemas/taxonomia.schema.json --call-model --model qwen2.5-7b-instruct
```

## 5) Executar o frontend (Next.js)

No diretório `frontend`:

```cmd
cd frontend
npm install
npm run dev
```

O frontend de desenvolvimento ficará disponível em `http://localhost:3000` (por padrão). A API FastAPI padrão permite CORS do `http://localhost:3000`.

## 6) Observações sobre o fluxo de prompts

- A composição de prompts agora é feita via a classe `PromptBuilder` em `backend/prompt_builder.py`.
- Para obter rótulos legíveis nas seções do prompt (por exemplo `schema`, `readme`, `extra_text`) passe esses textos como keyword-arguments quando instanciar `PromptBuilder`, por exemplo:

```py
from backend.prompt_builder import PromptBuilder
pb = PromptBuilder(schema=schema_text, readme=readme_text, extra_text=extra_text)
prompt = pb.build()
```

## 7) Limpeza de Git / .gitignore

Adicionei um `.gitignore` na raiz para evitar commitar ambientes virtuais, caches e arquivos sensíveis. Se já comitou arquivos que agora estão no `.gitignore`, remova-os do índice com:

```cmd
# mostrar arquivos que ainda estão no índice
git status

# remover do índice (mantém o arquivo local):
git rm --cached path/to/file
```

## 8) Verificações rápidas / debugging

- Verificar import básico do backend:

```cmd
python -c "import backend.main; print('backend OK')"
```

- Se houver problemas de import, verifique se o virtualenv está ativado e se as dependências foram instaladas.
- Se o modelo não responder, verifique `HUGGINGFACE_API_TOKEN` e a conectividade de rede.

## 9) Próximos passos sugeridos

- Adicionar testes automatizados (pytest) para o extractor e PromptBuilder.
- Adicionar CI para lint e testes.
- Documentar exemplos de prompts e o esquema em mais detalhes (arquivos em `backend/prompts` e `schemas/`).

Se quiser, eu atualizo este README com instruções específicas para deploy (Docker, Azure, etc.) ou adiciono um `Makefile`/scripts para facilitar repetição dos passos.
