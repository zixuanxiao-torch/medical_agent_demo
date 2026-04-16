# 医疗客服智能体 · 本地 DEMO

面向「一周工作量」的演示项目：网页聊天 + 本地 Ollama 模型 + SQLite 假数据 + 工具调用（查表 / 查订单 / 建工单）。

## 一、安装什么、装在哪里

### 1. Anaconda / 虚拟环境（你已有）

- **安装位置**：Anaconda 默认目录（例如 `C:\Users\你的用户名\anaconda3`）。
- **本项目 Python 依赖**：只在你的 **`my_lab_env`** 里安装（不要混到 base）。

### 2. Ollama（本机模型服务，独立于 conda）

- **是什么**：在后台跑大模型，通过 `http://127.0.0.1:11434` 提供接口。
- **安装位置**：官网 Windows 安装包，按向导装即可（与 Anaconda 无关）。
- **模型下载**：在 **PowerShell 或 CMD** 里执行（示例）：

```text
ollama pull qwen2.5:7b
```

若机器较吃力，可换更小模型，并在 `.env` 里改 `OLLAMA_MODEL`。

#### 用 DeepSeek API 代替 Ollama（不占本机大模型空间）

1. 复制 `.env.example` 为 `.env`，至少设置：

```text
LLM_BACKEND=openai_compatible
OPENAI_API_BASE=https://api.deepseek.com
OPENAI_API_KEY=你的_sk_密钥
OPENAI_MODEL=deepseek-chat
```

2. 在项目目录执行 `python test_llm.py` 测通后，再 `uvicorn`。**无需**本机 `ollama pull`。

### 3. 本项目代码依赖（装在 conda 环境里）

在 **`my_lab_env`** 激活后，进入本目录执行：

```text
cd c:\Users\10409\Documents\work\shixi_agent\medical_agent_demo
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env` 中的 `OLLAMA_MODEL` 与 `ollama pull` 的模型名保持一致。

---

## 二、怎么跑起来

1. **若用 Ollama**：启动 Ollama（托盘有图标或能访问 11434 端口）。**若用 DeepSeek API**：跳过此步。
2. 激活环境并启动后端：

```text
conda activate my_lab_env
cd c:\Users\10409\Documents\work\shixi_agent\medical_agent_demo
python test_llm.py
```

看到有一句回复即表示 **LLM 配置** 正确（Ollama 或 DeepSeek 均可）。

3. 启动 Web：

```text
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开：`http://127.0.0.1:8000/`

---

## 二点五、开发回归测试（pytest）

```text
cd c:\Users\10409\Documents\work\shixi_agent\medical_agent_demo
pip install -r requirements-dev.txt
pytest
```

---

## 二点五（二）、知识库追加（新清洗数据并入 Chroma）

清洗流水线见 `shuju.ipynb`；合并旧库 + 新库 JSONL 并增量写入向量库：

- 操作说明：[docs/kb_merge_append.md](docs/kb_merge_append.md)
- 合并脚本：`py -3 -m scripts.kb_merge_jsonl --base ... --add ... --out ...`
- 增量建库：`py -3 -m scripts.kb_build_chroma`（默认跳过已存在 id；全量用 `--rebuild`）

---

## 二点六、企业微信（自建应用）群聊接入（@应用自动回复）

本项目已提供企业微信回调入口：

- 回调校验（GET）：`/wecom/callback`
- 接收消息（POST）：`/wecom/callback`（会**快速返回** `success`，后台异步处理并主动发消息）

### 需要在 `.env` 配置

```text
WECOM_CORP_ID=ww...
WECOM_AGENT_ID=1000...
WECOM_SECRET=...
WECOM_TOKEN=...
WECOM_AES_KEY=...   # EncodingAESKey（43位）
WECOM_ONLY_REPLY_WHEN_MENTIONED=true
```

### 公司域名 + 本机运行（通过企微「域名主体校验」）

若个人域名无法通过主体校验，可用**公司子域**（如 `wecom.agent.gilitel.com`）对外暴露 HTTPS，本机仍只跑 `127.0.0.1:8000`：**公司 DNS 添加 CNAME → Cloudflare Tunnel（cloudflared 跑在本机）**。完整步骤见：

- [docs/wecom_company_domain_cloudflare_tunnel.md](docs/wecom_company_domain_cloudflare_tunnel.md)
- [docs/wecom_company_domain_local_reverse_tunnel.md](docs/wecom_company_domain_local_reverse_tunnel.md)（公司 nginx 做公网入口，应用仍只在你本机）

一键启动 tunnel（示例：Zero Trust 提供的 token + 网络需 HTTP/2 时）：

```text
.\scripts\run_cloudflared_tunnel.ps1 -Token "粘贴TOKEN" -UseHttp2
```

若你们公司要求 `agent.gilitel.com` 走公司 nginx，而你的应用继续跑在本机，可用 SSH 反向隧道：

```text
.\scripts\run_reverse_ssh_tunnel.ps1 -SshUser "你的用户名" -SshHost "agent.gilitel.com" -RemotePort 18000 -LocalPort 8000
```

### 最小联调步骤（开发机）

1. 启动服务（企业微信回调必须 HTTPS；本机演示可用 ngrok / frp / **Cloudflare Tunnel**，或按上文使用公司子域）：

```text
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

2. 在企业微信后台「自建应用」里配置“接收消息”回调 URL 为：
   - `https://你的域名/wecom/callback`（例如 `https://wecom.agent.gilitel.com/wecom/callback`）
   - 并填写 `WECOM_TOKEN` / `WECOM_AES_KEY`（与 `.env` 一致）
3. 回调保存校验通过后，把该应用加入你的目标群。
4. 在群里 `@应用 + 文字` 发送，应用会回复。

说明：群聊中默认仅在被 @ 时回复（`WECOM_ONLY_REPLY_WHEN_MENTIONED=true`）。如你们企业微信回调字段里无法识别 @，联调时可临时关掉该开关再逐步完善识别逻辑。

---

## 三、一周工作量怎么体现（可按天交付）

| 天数 | 任务 | 产出 |
|------|------|------|
| **第 1 天** | 装 Anaconda、建/确认 `my_lab_env`；装 Ollama；`ollama pull`；跑通 `test_ollama.py` | 环境说明截图 + 一条成功回复 |
| **第 2 天** | 理解仓库结构；跑通 `uvicorn`；打开网页能聊天 | 录屏或截图 |
| **第 3 天** | 读 `db.py` / `tools.py`，往 SQLite 里加几条自己的「表格」与订单 | 数据说明 1 页 |
| **第 4 天** | 读 `agent.py` 主循环；用「显示调试 trace」看工具是否被调用 | 问题记录 + 一次成功工具调用 trace |
| **第 5 天** | 强化规则：急症关键词、回复模板、参数校验 | 简短变更说明 |
| **第 6 天** | 整理接口约定（`/chat` 请求体、错误码）；写演示话术 | API 草图 1 页 |
| **第 7 天** | 演示彩排：固定剧本（查订单 / 建工单 / 知识库命中） | DEMO 讲稿 + PPT 大纲 |

---

## 四、目录说明

- `app.py`：FastAPI、`/chat`、静态页入口  
- `agent.py`：主循环（模型 → JSON → 工具 → 再模型）  
- `tools.py`：工具白名单与分发  
- `db.py`：SQLite 表结构与示例数据  
- `prompts.py`：系统提示与急症短路  
- `static/index.html`：网页聊天窗口  

数据库文件默认：`data/demo_medical.db`（首次运行自动创建）。

---

## 五、示例对话

- 「查订单 ORD2025001」  
- 「我手机后四位是 1234，订单怎么样了」  
- 「体检前要空腹吗」  
- 「我要投诉，帮我建工单」  

---

## 六、免责声明

本仓库仅供学习与演示，不构成医疗建议。急症请走 120 / 急诊。
