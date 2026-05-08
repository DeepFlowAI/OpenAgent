<div align="center">

# openagent

**开源 LLM 智能体平台** — 知识库、多渠道智能体、对话流程、工具调用、向量化与语义检索。

<p align="center">
  <a href="https://hub.docker.com/r/DeepFlowAI/OpenAgent-api">Docker Hub</a> ·
  <a href="./docker/README.md">自托管部署</a> ·
  <a href="https://github.com/DeepFlowAI/OpenAgent/issues">反馈问题</a>
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

## ✨ 特性

- **LLM 厂商中立** — 基于 LiteLLM；支持 OpenAI、阿里百炼、Moonshot、智谱、MiniMax、OpenRouter 以及任意 OpenAI 兼容端点。
- **支持语义检索的知识库** — Git 化文档摄入、pgvector 检索、BGE Embedding + Reranker 开箱即用。
- **可视化智能体构建** — 在管理 UI 中定义工具、提示词、对话流程。
- **多渠道对话** — 网站嵌入、帮助中心、API 调用任选。
- **帮助中心托管** — Markdown 驱动的对外文档站，支持多栏目导航。
- **天然多租户** — 开箱即用的单租户；企业版扩展支持平台级租户管理。
- **OpenTelemetry 可观测** — 厂商中立 OTLP 链路 / 日志（兼容 SigNoz、Honeycomb、Tempo、Grafana Cloud）。

## 🚀 快速开始

```bash
git clone https://github.com/DeepFlowAI/OpenAgent.git
cd openagent/docker
cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

docker compose up -d        # 默认自带 PostgreSQL (pgvector) + Redis
```

打开 <http://localhost:3000>，使用以下账号登录：

| 字段     | 默认值       |
| -------- | ------------ |
| 企业 ID  | `default`    |
| 账号     | `admin`      |
| 密码     | `Admin123456`   |

> ⚠️ **任何非本地环境，首次登录后请立即修改密码。**

至少要在 `.env` 设置一个 LLM provider key（例如 `OPENROUTER_API_KEY=sk-...`），知识库功能需要 `SILICONFLOW_API_KEY=...`。

### 使用自己的数据库 / Redis

编辑 `.env` 里的 `COMPOSE_PROFILES=` 排除对应内嵌服务，再设置 `DATABASE_URL` / `REDIS_URL`，命令仍然是 `docker compose up -d`。完整部署指南见 **[docker/README.md](docker/README.md)**。

> **外部 PostgreSQL 必须安装 `pgvector` 扩展**（用于语义检索）。

## 🛠️ 本地开发

```bash
# 后端
cd server && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.dev   # 改 DATABASE_URL / REDIS_URL / LLM_API_KEY 等
uvicorn app.main:app --reload --port 5001

# 前端
cd web && npm install
cp .env.example .env.dev
npm run dev
```

| 服务                | 地址                         |
| ------------------- | ---------------------------- |
| 前端                | http://localhost:3000        |
| 后端 API            | http://localhost:5001        |
| API 文档 (Swagger)  | http://localhost:5001/docs   |

## 🧩 架构

```
┌─────────────────────────┐    ┌─────────────────────────┐
│  Next.js + React        │◄──►│   FastAPI + LiteLLM     │
│  (web)                  │    │   (api)                 │
└─────────────────────────┘    └────────────┬────────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          ▼                 ▼                 ▼
                  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                  │  pgvector    │  │   Redis 7    │  │   对象存储   │
                  │ (向量+业务)  │  │ (缓存+队列)  │  │  (文件上传)  │
                  └──────────────┘  └──────────────┘  └──────────────┘
```

后端严格遵循 **Router → Service → Repository → Model** 分层，输入输出由 Pydantic Schema 约束。闭源扩展模块（如多租户管理）通过 `app/extensions/` 下的约定式加载器自动注册，无需改动开源代码。

## 🏢 版本对比

| 版本           | 租户                                   | 租户管理 API                       |
| -------------- | -------------------------------------- | ---------------------------------- |
| **社区版**     | 自动建一个 `default` 单租户            | —                                  |
| **企业版**     | 多租户                                 | `/api/v1/tenants`（闭源扩展）      |

社区版（即本仓库）对单组织部署是功能完整的。企业版扩展为 SaaS 运营方提供平台级租户增删改查 API。

## 🤝 贡献

欢迎提交 Issue、Discussion 与 Pull Request。提交 PR 前请确保测试通过：

```bash
cd server && pytest
```

## 📜 协议

openagent 采用 [GNU Affero 通用公共许可证 v3.0](LICENSE) 开源。
