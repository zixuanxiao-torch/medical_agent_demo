"""
供管理接口与文档使用的「工具清单 + 边界说明」。
后续接入新工具时：先改 tools.py 实现，再在此补充一条 registry，保持对外描述一致。
"""

from __future__ import annotations

from typing import Any

# 与 tools.ALLOWED_TOOLS 应对齐；name 必须一致
TOOL_REGISTRY: list[dict[str, Any]] = [
    {
        "name": "query_medical_table",
        "kind": "read",
        "data_scope": "SQLite medical_items（院内常识/流程文案）",
        "description": "按关键词模糊检索知识库条目，用于回答流程、注意事项等非个体医疗诊断问题。",
        "parameters": {
            "keyword": {"type": "string", "required": True, "hint": "用户问题中的核心词"},
        },
        "boundaries": [
            "不得替代医生诊断或用药建议；急症须引导 120/急诊。",
            "若库中无结果，应如实说明并建议人工客服，勿编造条目。",
        ],
    },
    {
        "name": "query_order",
        "kind": "read",
        "data_scope": "SQLite orders（体检/消费类订单）",
        "description": "按订单号或手机后四位查订单状态；单号形态多为 ORD…。",
        "parameters": {
            "order_id": {"type": "string", "required": False},
            "phone_last4": {"type": "string", "required": False},
        },
        "boundaries": [
            "仅查询「订单」，不可用于「工单」进度；工单请用 query_ticket。",
            "order_id 与 phone_last4 至少填一个。",
        ],
    },
    {
        "name": "query_ticket",
        "kind": "read",
        "data_scope": "SQLite tickets（客服工单）",
        "description": "按工单数字 ID 查询，或不传 ID 返回最近工单列表（演示）。",
        "parameters": {
            "ticket_id": {"type": "integer", "required": False, "hint": "如 1、2"},
        },
        "boundaries": [
            "与 query_order 区分：用户说「工单」必须用本工具。",
        ],
    },
    {
        "name": "create_ticket",
        "kind": "write",
        "data_scope": "SQLite tickets INSERT",
        "description": "创建客服工单，需标题与详情。",
        "parameters": {
            "title": {"type": "string", "required": True},
            "detail": {"type": "string", "required": True},
        },
        "boundaries": [
            "敏感操作：参数需经后端校验；生产环境应叠加频控与鉴权。",
            "创建成功后可通过管理台 /admin 轮询或业务系统接收通知。",
        ],
    },
    {
        "name": "kb_retrieve",
        "kind": "read",
        "data_scope": "本地 Chroma 向量库（由 kb_clean.jsonl 离线建库）",
        "description": "按用户问题在知识库中检索最相关的证据片段（top_k）。回答必须基于检索结果，检索不到就如实说明。",
        "parameters": {
            "query": {"type": "string", "required": True},
            "top_k": {"type": "integer", "required": False, "hint": "默认 5，最大 20"},
        },
        "boundaries": [
            "仅做检索，不做推理；最终答复由模型在看到证据后生成。",
            "命中结果可能包含历史对话片段，必须遵守脱敏与保密要求。",
        ],
    },
]


def get_tool_registry() -> dict[str, Any]:
    return {
        "version": "1.0",
        "agent_protocol": "模型输出 JSON：action=tool|reply；与 OpenAI function_call 不同，微调数据需与此一致。",
        "tools": TOOL_REGISTRY,
    }
