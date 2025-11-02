# 项目说明

## 项目动机

我们想回答一个具体的问题：**当面对一份特别特别长的文档时，AI 能否在尽量少的人类干预下快速读懂并写出有体系的总结？** 现实案例是「AI 生产力训练营」微信群，已沉淀两年、累计约一百万 token 的聊天文本。[早期实验](https://yage.ai/ai-book.html)表明，即便数据完全未整理，LLM 也能凭借大 context window 输出结构化的长篇内容，但整个流程依旧高度依赖人工挑选片段、组织证据。

为了验证迭代成果，我们基于同一套流程做了一个简易实验，产出可在 [`results/wechat_group_summary.md`](results/wechat_group_summary.md) 查看。我觉得这个文档的质量是远远不如我们上一次实验手工生成的质量高的，但是考虑到这个方向潜力还是很大的，所以把代码和提示词分享出来，方便大家在这个基础上继续探索。

随着复杂模型（例如 GPT-5-Codex 系列）的能力增强，我们希望进一步探索：**能否把阅读—检索—推理—写作链路交给智能体自动完成，或至少让它主导大部分工作？** 这个仓库就是为了验证这一想法而搭建，目标是让智能体自己探索素材、沉淀洞见，并把结果汇编成书稿。

## 设计思路与核心工具

为了让智能体真正摸得到素材，我们提供了四类能力：

1. **原始文本访问 (`GET /lines/count`, `POST /lines/content`)**  
   让模型随时读取原文行号与上下文，相当于把大部头摊开在面前。
2. **语义检索 (`POST /search/semantic`)**  
   借助 FAISS 与传统一维检索相比更好地理解问题语义，避免模型只能用 `rg/grep` 这类基于字符串的粗检。
3. **深度思考 (`POST /think/deep`)**  
   将整理出的线索交给 Gemini 2.5 Pro 做长链推理，扩展想法或提出新的调查方向。
4. **编排指引 (`instructions.md`)**  
   用于提示智能体的标准工作流，让它学会反复提问、检索、验真和写作，而不是一次性生成看似合理的答案。

这四个工具共同保证：既能让智能体直接查看原始材料，也能利用更强大的语义检索与推理能力建立自己的资料索引，从而在最少人工干预的情况下完成长文档的迭代撰写。

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
