# 项目说明

本项目用于处理群聊文本数据，构建语义索引，并提供 FastAPI 服务与智能体协作指引。

## 环境准备

1. **创建并激活 virtualenv**
   ```bash
   uv venv venv
   source venv/bin/activate
   ```
2. **安装依赖**（必须使用 `uv pip install`）
   ```bash
   uv pip install -r requirements.txt  # 如果尚未生成 requirements.txt，请见下文安装命令
   ```
   当前环境所需的核心依赖包括 `openai`、`faiss-cpu`、`fastapi`、`uvicorn`、`python-dotenv`、`google-genai`、`numpy`、`tqdm` 等。
3. **配置凭证**
   - 在根目录的 `.env` 中填入 `OPENAI_API_KEY`。
   - 将 Google Gemini 的密钥写入 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`。

## 生成索引

1. 确保聊天文本文件位于根目录（默认文件名 `AI生产力训练营__text_only.csv`）。
2. 执行构建脚本：
   ```bash
   source venv/bin/activate
   python scripts/build_index.py \
     --input-path AI生产力训练营__text_only.csv \
     --output-dir data \
     --chunk-size 50 \
     --overlap 10 \
     --workers 16 \
     --model text-embedding-3-small
   ```
3. 运行结束后会在 `data/` 目录生成：
   - `index.faiss`：FAISS L2 索引。
   - `chunks.jsonl`：含每个分块的行号、文本与向量。
   - `metadata.json`：记录模型与分块配置。

## 启动 FastAPI 服务

1. 确保 `.env` 中的密钥有效且索引已生成。
2. 启动服务（默认端口 8004）：
   ```bash
   source venv/bin/activate
   uvicorn app.server:app --host 0.0.0.0 --port 8004
   ```
3. 可通过 `http://localhost:8004/docs` 查看 Swagger UI，快速试用接口：
   - `GET /lines/count`
   - `POST /lines/content`
   - `POST /search/semantic`
   - `POST /think/deep`

## 智能体协作

项目根目录的 `instructions.md` 为编排智能体的操作手册。建议在任何自动化流程中读取该文件，并按照其中的工作流调用 FastAPI 接口与 Gemini 深度思考模型，逐步生成面向群聊洞见的长文档。

## 日常流程回顾

1. 新的聊天记录到达后，放置到根目录并运行 `scripts/build_index.py` 更新索引。
2. 启动 FastAPI 服务，为前端或智能体提供查询与语义检索能力。
3. 智能体依照 `instructions.md` 的流程，交替调用 `POST /think/deep` 与检索接口，逐步沉淀分析成果。
