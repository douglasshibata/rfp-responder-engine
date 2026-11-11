# 📖 Guia Tutorial: Engine de Resposta Automatizada de RFPs & Licitações

Este tutorial detalha o passo a passo operacional para configurar, executar, testar e monitorar o sistema **Automated RFP & Tender Responder Engine**.

---

## 🎯 Visão Geral do Sistema

O sistema resolve um problema crítico para empresas B2B: o tempo gasto respondendo manualmente documentos de RFP (Request for Proposal) com centenas de perguntas.

### Componentes Principais:
1. **FastAPI Gateway**: Interface REST assíncrona para submissão de documentos e consulta de progresso.
2. **Fila Redis + Celery Workers**: Orquestração assíncrona distribuída em tempo real.
3. **Estratégia Multi-Provedor LangChain**:
   - **DeepInfra (Llama 3)**: Leitura rápida e extração de perguntas em lote (baixo custo).
   - **Ollama (Embeddings Locais)**: Busca semântica na base de conhecimento da empresa com privacidade total.
   - **OpenAI (GPT-4o)**: Redação persuasiva e detalhada das respostas finais.

---

## ⚙️ Pré-requisitos e Instalação

### 1. Requisitos de Ambiente
- **Python 3.11 ou superior**
- **Redis Server** (local ou containerizado via Docker)
- **Ollama** (opcional para execução local de embeddings; o sistema possui fallback automático caso esteja offline)

### 2. Instalação das Dependências

Acesse a pasta do projeto e instale as dependências exigidas:

```bash
cd rfp-responder-engine
pip install -r requirements.txt
```

---

## 🚀 Execução do Sistema Passo a Passo

### Passo 1: Iniciar o Broker Redis
Caso não tenha o Redis rodando localmente, suba via Docker:

```bash
docker run -d --name redis-rfp -p 6379:6379 redis:alpine
```

### Passo 2: Iniciar o Worker Celery

Em um terminal separado na pasta `rfp-responder-engine`:

```bash
celery -A tasks.celery_app worker --loglevel=info
```

### Passo 3: Iniciar o Servidor FastAPI

Em outro terminal na mesma pasta:

```bash
python3 main.py
```

O servidor estará ativo em `http://localhost:8000`. A documentação interativa Swagger/OpenAPI estará acessível em `http://localhost:8000/docs`.

---

## 🧪 Testando a API via cURL ou Swagger

### 1. Submeter um Documento de RFP

```bash
curl -X POST "http://localhost:8000/api/v1/rfp/submit" \
     -H "Content-Type: application/json" \
     -d '{
       "title": "Licitação de Infraestrutura de Nuvem",
       "document_text": "Q1. Como sua empresa garante alta disponibilidade 99.99%?\nQ2. Quais certificações de segurança (SOC2, ISO27001) vocês possuem?",
       "knowledge_base": "Nossa plataforma possui conformidade SOC2 Type II e ISO27001. Garantimos uptime de 99.99% com failover automático em multi-regiões."
     }'
```

**Resposta Exemplo (HTTP 202 Accepted):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Licitação de Infraestrutura de Nuvem",
  "status": "PENDING",
  "message": "RFP document submitted successfully. Processing initialized asynchronously."
}
```

### 2. Acompanhar o Progresso da Tarefa

```bash
curl "http://localhost:8000/api/v1/rfp/job/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

**Resposta Exemplo (Status HTTP 200 OK):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Licitação de Infraestrutura de Nuvem",
  "status": "COMPLETED",
  "progress_percentage": 100.0,
  "total_questions": 2,
  "completed_questions": 2,
  "execution_time_seconds": 1.45,
  "created_at": "2026-10-22T10:00:00",
  "updated_at": "2026-10-22T10:00:01",
  "summary_notes": "Successfully answered 2/2 questions across parallel worker tasks."
}
```

### 3. Obter o Documento Final de Resposta

```bash
curl "http://localhost:8000/api/v1/rfp/job/a1b2c3d4-e5f6-7890-abcd-ef1234567890/results"
```

---

## 🛠️ Executando os Testes Automatizados

Para validar o funcionamento completo sem necessidade do Redis e servidores externos (utilizando execução síncrona/eager no Celery e fallbacks determinísticos dos modelos):

```bash
PYTHONPATH=. pytest tests/ -v
```

---

## 🔍 Resolução de Problemas (Troubleshooting)

| Sintoma | Causa Provável | Solução |
| :--- | :--- | :--- |
| `Redis connection error` | Broker Redis indisponível | Inicie o serviço Redis com `docker run -d -p 6379:6379 redis:alpine` ou ajuste `REDIS_URL` em `config.py`. |
| `ModuleNotFoundError` | Executando de fora da pasta base | Configure a variável de ambiente: `PYTHONPATH=. python3 main.py`. |
| `Celery worker not picking tasks` | Fila incompatível ou aplicativo não importado | Garanta que o worker foi disparado usando `celery -A tasks.celery_app worker --loglevel=info`. |
