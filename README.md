<div align="center">

# openagent

**Open-source LLM agent platform** — knowledge bases, multi-channel agents, conversation flows, tool calling, embedding & semantic search.

<p align="center">
  <a href="https://hub.docker.com/r/DeepFlowAI/OpenAgent-api">Docker Hub</a> ·
  <a href="./docker/README.md">Self-hosting</a> ·
  <a href="https://github.com/DeepFlowAI/OpenAgent/issues">Issues</a>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-AGPL--3.0-blue?style=flat-square"></a>
  <a href="https://hub.docker.com/r/DeepFlowAI/OpenAgent-api"><img alt="Docker pulls (api)" src="https://img.shields.io/docker/pulls/DeepFlowAI/OpenAgent-api?style=flat-square&label=api%20pulls"></a>
  <a href="https://hub.docker.com/r/DeepFlowAI/OpenAgent-web"><img alt="Docker pulls (web)" src="https://img.shields.io/docker/pulls/DeepFlowAI/OpenAgent-web?style=flat-square&label=web%20pulls"></a>
  <a href="https://github.com/DeepFlowAI/OpenAgent/releases"><img alt="Latest release" src="https://img.shields.io/github/v/release/DeepFlowAI/OpenAgent?style=flat-square"></a>
  <a href="https://github.com/DeepFlowAI/OpenAgent/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/DeepFlowAI/OpenAgent?style=flat-square"></a>
</p>

<p align="center">
  <a href="./README.md"><img alt="English" src="https://img.shields.io/badge/English-d9d9d9?style=flat-square"></a>
  <a href="./README.zh-CN.md"><img alt="简体中文" src="https://img.shields.io/badge/%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-d9d9d9?style=flat-square"></a>
</p>

</div>

## ✨ Features

- **LLM-agnostic** — built on LiteLLM; bring keys for OpenAI, Aliyun Bailian, Moonshot, Zhipu, Minimax, OpenRouter, or any OpenAI-compatible endpoint.
- **Knowledge bases with semantic search** — Git-backed document ingestion, pgvector-powered retrieval, BGE embedding + reranker out of the box.
- **Visual agent builder** — define tools, prompts, and conversation flows in the admin UI.
- **Multi-channel chat** — embed agents on websites, help centers, or via API.
- **Help center hosting** — Markdown-driven public documentation site, multi-tab navigation.
- **Multi-tenant ready** — single-tenant out of the box; the Enterprise edition adds platform-level tenant management.
- **OpenTelemetry observability** — vendor-neutral OTLP traces & logs (works with SigNoz, Honeycomb, Tempo, Grafana Cloud).

## 🚀 Quick Start

```bash
git clone https://github.com/DeepFlowAI/OpenAgent.git
cd openagent/docker
cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

docker compose up -d        # bundles PostgreSQL (pgvector) + Redis by default
```

Open <http://localhost:3000> and sign in:

| Field    | Default      |
| -------- | ------------ |
| Tenant   | `default`    |
| Username | `admin`      |
| Password | `Admin123456`   |

> ⚠️ **Change the password immediately after first login in any non-local deployment.**

You'll also want to set at least one LLM provider API key in `.env` (e.g. `OPENROUTER_API_KEY=sk-...`) and `SILICONFLOW_API_KEY=...` for the knowledge-base embedding/reranker.

### Bring your own database / Redis

Edit `COMPOSE_PROFILES=` in `.env` to drop the bundled service(s), then set `DATABASE_URL` / `REDIS_URL`. The command stays `docker compose up -d`. Full deployment guide → **[docker/README.md](docker/README.md)**.

> **External PostgreSQL** must have the `pgvector` extension installed (used for semantic search).

## 🛠️ Local Development

```bash
# Backend
cd server && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.dev   # set DATABASE_URL / REDIS_URL / LLM_API_KEY etc.
uvicorn app.main:app --reload --port 5001

# Frontend
cd web && npm install
cp .env.example .env.dev
npm run dev
```

| Service             | URL                          |
| ------------------- | ---------------------------- |
| Frontend            | http://localhost:3000        |
| Backend API         | http://localhost:5001        |
| API docs (Swagger)  | http://localhost:5001/docs   |

## 🧩 Architecture

```
┌─────────────────────────┐    ┌─────────────────────────┐
│  Next.js + React        │◄──►│   FastAPI + LiteLLM     │
│  (web)                  │    │   (api)                 │
└─────────────────────────┘    └────────────┬────────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          ▼                 ▼                 ▼
                  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                  │  pgvector    │  │   Redis 7    │  │ Object store │
                  │ (vectors+RDS)│  │ (cache+queue)│  │ (uploads)    │
                  └──────────────┘  └──────────────┘  └──────────────┘
```

Backend follows a strict **Router → Service → Repository → Model** layering with Pydantic schemas for I/O. Closed-source extensions (e.g. multi-tenant management) plug in via a convention-based loader at `app/extensions/`.

## 🏢 Editions

| Edition         | Tenants                              | Tenant management API           |
| --------------- | ------------------------------------ | ------------------------------- |
| **Community**   | Single auto-provisioned `default`    | —                               |
| **Enterprise**  | Multi-tenant                         | `/api/v1/tenants` (closed)      |

The Community edition (this repository) is feature-complete for single-organization deployments. The Enterprise extension adds the platform-level tenant CRUD API for SaaS operators.

## 🤝 Contributing

Issues, discussions, and pull requests are welcome. Before opening a PR please make sure tests pass:

```bash
cd server && pytest
```

## 📜 License

openagent is released under the [GNU Affero General Public License v3.0](LICENSE).
