from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ollama | openai_compatible（DeepSeek / 多数国产云走 OpenAI 兼容 /v1/chat/completions）
    llm_backend: Literal["ollama", "openai_compatible"] = "ollama"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"

    openai_api_base: str = "https://api.deepseek.com"
    openai_api_key: str = ""
    openai_model: str = "deepseek-chat"

    agent_max_tool_rounds: int = 5
    database_path: str = "./data/demo_medical.db"

    # 业务系统调用 POST /chat：非空则必须带 X-Chat-Token 或 Authorization: Bearer <同值>
    chat_api_token: str = ""

    # 管理后台 /admin：非空则须在 URL ?token= 或请求头 X-Admin-Token 携带相同值
    admin_token: str = ""
    # 管理页轮询间隔（秒），仅前端使用说明；实际间隔写死在 admin.html
    admin_poll_interval_sec: int = 2

    # 微调 / SFT 样本累积文件（JSONL，一行一条）
    finetune_jsonl_path: str = "./data/finetune/samples.jsonl"

    # ========== 知识库（RAG）==========
    # DashScope OpenAI-compatible embeddings
    embed_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-v4"
    # DashScope embeddings 对 batch 有较小上限（常见 <=10）
    embed_batch_size: int = 10
    # Chroma 持久化目录（先用本地）
    kb_chroma_dir: str = "./data/kb_chroma"
    # 源知识库 JSONL（Q/A 结构，用于离线建库脚本）
    kb_source_jsonl: str = ""
    kb_top_k: int = 5

    # ========== 企业微信（自建应用 · 群聊接入）==========
    # 企业 ID、应用 agentid、应用 Secret
    wecom_corp_id: str = ""
    wecom_agent_id: int = 0
    wecom_secret: str = ""
    # 回调校验/加解密参数（在企业微信后台配置）
    wecom_token: str = ""
    wecom_aes_key: str = ""
    # 仅在群聊中被 @ 时才回复（不同回调字段形态不一，仍建议开启并配合实际联调调整）
    wecom_only_reply_when_mentioned: bool = True


def get_settings() -> Settings:
    return Settings()


def db_path_resolved(settings: Settings) -> Path:
    p = Path(settings.database_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def finetune_jsonl_resolved(settings: Settings) -> Path:
    p = Path(settings.finetune_jsonl_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
