# README Evaluator

Ferramenta para avaliar READMEs de repositórios GitHub usando IA. Extrai uma taxonomia JSON estruturada baseada em um esquema canônico e renderiza um resumo legível da avaliação.

## 🚀 Quick Start

### Pré-requisitos

- **Python 3.10+** (backend)
- **Node.js 18+** e npm (frontend)
- **GEMINI_API_KEY** (chave da API Google Gemini)

### Setup (5 minutos)

#### 1. Backend (Python + FastAPI)

```cmd
# Crie um virtualenv
python -m venv .venv
.venv\Scripts\activate

# Instale dependências
pip install --upgrade pip
pip install -r backend/requirements.txt
```

#### 2. Configure a API Key

Crie um arquivo `.env` na raiz do projeto:

```
GEMINI_API_KEY=sua_chave_aqui
```

Ou export no terminal:

```cmd
set GEMINI_API_KEY=sua_chave_aqui
```

#### 3. Inicie o Backend

```cmd
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Backend estará em `http://localhost:8000`

#### 4. Inicie o Frontend

```cmd
cd frontend
npm install
npm run dev
```

Frontend estará em `http://localhost:3000`

---

## 📋 Como Usar

1. Abra `http://localhost:3000` no navegador
2. Cole a URL de um repositório GitHub (ex: `https://github.com/owner/repo`)
3. Clique em "Evaluate README"
4. Aguarde o processamento:
   - **Extração**: README é processado e avaliado
   - **Renderização**: Resultado é convertido para linguagem natural legível
5. Veja o resumo executivo na seção **"Evaluation Summary"**
6. Explore os detalhes técnicos (JSON estruturado, prompt usado, etc.)

---

## 🏗️ Arquitetura

```
readme-evaluator/
├── backend/
│   ├── main.py                 # FastAPI app com endpoints
│   ├── pipeline.py             # Orquestração do pipeline
│   ├── gemini_client.py        # Cliente da API Gemini
│   ├── prompt_builder.py       # Construção de prompts
│   ├── evaluate/
│   │   ├── extractor.py        # Extração de JSON
│   │   ├── json_postprocessor.py # Correção de tipos
│   │   └── progress.py         # Rastreamento de progresso
│   ├── present/
│   │   └── renderer.py         # Renderização para texto
│   └── requirements.txt
├── frontend/
│   ├── pages/index.js          # UI principal (Next.js)
│   └── package.json
├── schemas/
│   └── taxonomia.schema.json   # Schema JSON canônico
└── README.md
```

---

## 🔌 API Endpoints

### `POST /extract-json-stream`

Avalia um README e retorna a taxonomia JSON + texto renderizado via Server-Sent Events (SSE).

**Request:**
```json
{
  "readme_text": "# Project Name\n...",
  "model": "gemini-2.5-flash",
  "max_tokens": 2048,
  "temperature": 0.1
}
```

**Response (SSE):**
- `type: "progress"` — Atualizações de progresso
- `type: "result"` — JSON estruturado (taxonomia)
- `type: "rendered"` — Texto renderizado em linguagem natural
- `type: "error"` — Erro durante processamento

---

### `POST /readme`

Baixa o README de um repositório GitHub.

**Request:**
```json
{
  "repo_url": "https://github.com/owner/repo"
}
```

**Response:**
```json
{
  "content": "# Project\n...",
  "filename": "README.md"
}
```

---

## 📊 Taxonomia JSON

O schema (`schemas/taxonomia.schema.json`) define 11 categorias:

1. **what** — O que é o projeto?
2. **why** — Por que existe?
3. **how_installation** — Como instalar?
4. **how_usage** — Como usar?
5. **how_config_requirements** — Configuração e requisitos?
6. **when** — Status e versão?
7. **who** — Autores e mantenedores?
8. **license** — Licença?
9. **contribution** — Como contribuir?
10. **references** — Documentação e referências?
11. **other** — Outras seções detectadas?

Cada categoria contém:
- **checklist** — Itens específicos presentes/ausentes
- **quality** — Notas de 1-5 (para maioria das categorias)
- **evidences** — Trechos encontrados no README
- **justifications** — Por que recebeu essa avaliação
- **suggested_improvements** — Sugestões

---

## 🔧 Post-Processing

O backend aplica automaticamente:

1. **Fix de Arrays** — Converte strings para arrays em campos como `evidences`, `justifications`, `suggested_improvements`
2. **Fix de Booleanos** — Converte strings para booleanos em `reclassify`, `suggest_removal`
3. **Remoção de Campos Inválidos** — Remove campos não permitidos por categoria (ex: `justifications` não existe em `other`)
4. **Validação** — Valida contra schema JSON

---

## 🐛 Debugging

**Ver logs do backend:**
```cmd
# Terminal onde backend está rodando mostra logs em tempo real
```

**DevTools do frontend (F12):**
- Console: vê eventos SSE e logs
- Network: vê requests para `/extract-json-stream`

**Testar endpoint direto:**
```cmd
curl -X POST http://localhost:8000/readme ^
  -H "Content-Type: application/json" ^
  -d "{\"repo_url\":\"https://github.com/owner/repo\"}"
```

---

## 🌍 Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|----------|-----------|-----------|
| `GEMINI_API_KEY` | ✅ | Chave da API Google Gemini |
| `BACKEND_PORT` | ❌ | Porta do backend (padrão: 8000) |
| `FRONTEND_PORT` | ❌ | Porta do frontend (padrão: 3000) |

---

## 📦 Dependências

### Backend (`backend/requirements.txt`)
- fastapi >= 0.121.2
- uvicorn >= 0.38.0
- google-genai >= 1.50.1
- jsonschema >= 4.25.1
- pydantic >= 2.12.4
- python-dotenv >= 1.2.1

### Frontend (`frontend/package.json`)
- next >= 16.0.1
- react >= 18.2.0
- react-dom >= 18.2.0

---

## ✅ Testes

Execute testes do backend:

```cmd
pytest tests/
```

---

## 📄 Licença

MIT

---

## 👥 Contribuições

Abra uma issue ou PR para sugestões e melhorias!
