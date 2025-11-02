from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

import faiss
import numpy as np
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from google import genai
from google.genai import types as genai_types
from openai import OpenAI
from pydantic import BaseModel, Field


DATA_DIR = Path("data")
DEFAULT_INPUT_PATH = Path("AI生产力训练营__text_only.csv")
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
INDEX_PATH = DATA_DIR / "index.faiss"
MAX_LINE_SPAN = 2000
EMBEDDING_MODEL = "text-embedding-3-small"
GEMINI_MODEL = "gemini-2.5-pro"


class LineCountResponse(BaseModel):
    total_lines: int = Field(..., description="文件的总行数。")


class LineRangeRequest(BaseModel):
    start_line: int = Field(..., ge=1, description="起始行号（从1开始，包含）。")
    end_line: int = Field(..., ge=1, description="结束行号（包含）。")


class LineRangeResponse(BaseModel):
    start_line: int = Field(..., description="起始行号（包含）。")
    end_line: int = Field(..., description="结束行号（包含）。")
    lines: List[str] = Field(..., description="选定区间内的行内容。")


class SemanticQueryRequest(BaseModel):
    queries: List[str] = Field(..., min_length=1, description="需要进行语义检索的查询字符串列表。")
    k: int = Field(5, ge=1, description="每个查询希望返回的最近邻数量。")


class SemanticHit(BaseModel):
    chunk_id: int = Field(..., description="命中的分块编号。")
    start_line: int = Field(..., description="命中分块的起始行号（包含）。")
    end_line: int = Field(..., description="命中分块的结束行号（包含）。")
    distance: float = Field(..., description="与查询的 L2 距离。")
    text: str = Field(..., description="命中分块的原始文本。")


class SemanticQueryResponse(BaseModel):
    results: List[List[SemanticHit]] = Field(
        ..., description="与输入 queries 一一对应的检索结果列表。"
    )


class DeepThinkRequest(BaseModel):
    prompt: str = Field(..., description="需要深度思考的提示文本。")


class DeepThinkResponse(BaseModel):
    output: str = Field(..., description="Gemini 2.5 Pro 的响应文本。")


class AppState:
    def __init__(self) -> None:
        self.lines: List[str] = []
        self.chunk_records: List[dict] = []
        self.index: faiss.Index | None = None
        self.embedding_client: OpenAI | None = None
        self.deep_think_client: genai.Client | None = None
        self.embedding_model: str = EMBEDDING_MODEL

    @property
    def total_lines(self) -> int:
        return len(self.lines)

    def ensure_index_ready(self) -> None:
        if self.index is None or not self.chunk_records:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="索引尚未加载完成。",
            )


app = FastAPI(
    title="群聊语义索引服务",
    description="提供聊天文本的行号查询、语义检索以及深度思考能力的 FastAPI 服务。",
    version="0.1.0",
)


def read_lines(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8") as infile:
        return [line.rstrip("\r\n") for line in infile]


def load_chunks(path: Path) -> List[dict]:
    records: List[dict] = []
    with path.open("r", encoding="utf-8") as infile:
        for line in infile:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def get_state() -> AppState:
    return app.state.state  # type: ignore[return-value]


@app.on_event("startup")
def startup_event() -> None:
    load_dotenv()

    state = AppState()
    app.state.state = state  # type: ignore[attr-defined]

    if not DEFAULT_INPUT_PATH.exists():
        raise RuntimeError(f"找不到输入文件：{DEFAULT_INPUT_PATH}")
    state.lines = read_lines(DEFAULT_INPUT_PATH)

    if not CHUNKS_PATH.exists() or not INDEX_PATH.exists():
        raise RuntimeError("索引或分块文件不存在，请先运行 scripts/build_index.py 生成索引。")
    state.chunk_records = load_chunks(CHUNKS_PATH)
    if not state.chunk_records:
        raise RuntimeError("分块文件为空，无法加载索引。")

    state.index = faiss.read_index(str(INDEX_PATH))
    if state.index.ntotal != len(state.chunk_records):
        raise RuntimeError("索引中的向量数量与分块元数据不一致。")

    metadata_path = DATA_DIR / "metadata.json"
    if metadata_path.exists():
        with metadata_path.open("r", encoding="utf-8") as infile:
            metadata = json.load(infile)
        model_name = metadata.get("model")
        if isinstance(model_name, str) and model_name:
            state.embedding_model = model_name


def get_openai_client(state: AppState) -> OpenAI:
    if state.embedding_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="未配置 OPENAI_API_KEY。",
            )
        state.embedding_client = OpenAI(api_key=api_key)
    return state.embedding_client


def get_genai_client(state: AppState) -> genai.Client:
    if state.deep_think_client is None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="未配置 GEMINI_API_KEY 或 GOOGLE_API_KEY。",
            )
        state.deep_think_client = genai.Client(api_key=api_key)
    return state.deep_think_client


@app.get(
    "/lines/count",
    response_model=LineCountResponse,
    summary="获取文件总行数",
)
def get_line_count(state: AppState = Depends(get_state)) -> LineCountResponse:
    return LineCountResponse(total_lines=state.total_lines)


@app.post(
    "/lines/content",
    response_model=LineRangeResponse,
    summary="按行号区间获取内容",
)
def get_content_by_lines(
    payload: LineRangeRequest,
    state: AppState = Depends(get_state),
) -> LineRangeResponse:
    state.ensure_index_ready()

    if payload.end_line < payload.start_line:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_line 必须大于或等于 start_line。",
        )

    span = payload.end_line - payload.start_line + 1
    if span > MAX_LINE_SPAN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多只能请求 {MAX_LINE_SPAN} 行。",
        )

    if payload.start_line < 1 or payload.end_line > state.total_lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="行号超出文件范围。",
        )

    start_idx = payload.start_line - 1
    end_idx = payload.end_line
    lines = state.lines[start_idx:end_idx]
    return LineRangeResponse(
        start_line=payload.start_line,
        end_line=payload.end_line,
        lines=lines,
    )


def _semantic_search_single(
    query: str,
    k: int,
    state: AppState,
) -> List[SemanticHit]:
    client = get_openai_client(state)
    response = client.embeddings.create(
        model=state.embedding_model,
        input=query,
    )
    embedding = np.asarray(response.data[0].embedding, dtype="float32")
    embedding = embedding.reshape(1, -1)

    effective_k = min(k, state.index.ntotal)  # type: ignore[union-attr]
    distances, indices = state.index.search(embedding, effective_k)  # type: ignore[union-attr]
    hits: List[SemanticHit] = []
    for distance, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        record = state.chunk_records[idx]
        hits.append(
            SemanticHit(
                chunk_id=record["chunk_id"],
                start_line=record["start_line"],
                end_line=record["end_line"],
                distance=float(distance),
                text=record["text"],
            )
        )
    return hits


@app.post(
    "/search/semantic",
    response_model=SemanticQueryResponse,
    summary="进行语义检索",
)
def semantic_search(
    payload: SemanticQueryRequest,
    state: AppState = Depends(get_state),
) -> SemanticQueryResponse:
    state.ensure_index_ready()
    if payload.k <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="k 必须为正整数。",
        )

    results = [
        _semantic_search_single(query, payload.k, state) for query in payload.queries
    ]
    return SemanticQueryResponse(results=results)


@app.post(
    "/think/deep",
    response_model=DeepThinkResponse,
    summary="调用 Gemini 进行深度思考",
)
def deep_think(
    payload: DeepThinkRequest,
    state: AppState = Depends(get_state),
) -> DeepThinkResponse:
    client = get_genai_client(state)
    contents = [
        genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=payload.prompt)],
        )
    ]
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=-1),
            tools=[
                genai_types.Tool(url_context=genai_types.UrlContext()),
                genai_types.Tool(googleSearch=genai_types.GoogleSearch()),
            ],
        ),
    )
    output = getattr(response, "text", None)
    if not output and getattr(response, "candidates", None):
        parts = []
        for candidate in response.candidates:
            if not getattr(candidate, "content", None):
                continue
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    parts.append(part.text)
        output = "\n".join(parts)
    if not output:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gemini 没有返回可用内容。",
        )
    return DeepThinkResponse(output=output)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.server:app", host="0.0.0.0", port=8004, reload=False)
