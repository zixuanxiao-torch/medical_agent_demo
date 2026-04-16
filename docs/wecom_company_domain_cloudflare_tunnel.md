# 本机运行 + 公司域名通过企业微信校验（CNAME + Cloudflare Tunnel）

服务仍只跑在本机 `http://127.0.0.1:8000`；公网通过 **Cloudflare Tunnel** 接入；**对外域名**使用公司子域（如 `wecom.agent.gilitel.com`），以满足企业微信「域名主体校验」。

应用代码无需修改，回调路径固定为 **`/wecom/callback`**（见 `channels/wecom.py`）。

## 架构

```text
企业微信 HTTPS 请求
  → wecom.agent.gilitel.com（公司 DNS：CNAME）
  → Cloudflare 边缘
  → cloudflared（跑在你笔记本上）
  → http://127.0.0.1:8000（uvicorn）
```

## 一、Cloudflare Zero Trust：公网主机名（你操作）

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)，进入 **Zero Trust**（旧称 Teams）。
2. 左侧 **Networks** → **Tunnels** → **Create a tunnel**（或选择已有 tunnel）。
3. 为 tunnel 命名（例如 `medical-agent-wecom`），按向导 **在本机安装并运行连接器**：
   - 页面会给出一条命令，形如：  
     `cloudflared.exe service install <TOKEN>`  
     或：  
     `cloudflared tunnel run --token <TOKEN>`  
   - 在 **笔记本** 上执行该命令（或见下文 `scripts/run_cloudflared_tunnel.ps1` 使用 `-Token`）。
4. 在同一 tunnel 配置里添加 **Public Hostname**（公网主机名）：
   - **Subdomain**：`wecom`（若完整域名为 `wecom.agent.gilitel.com`，需在下方选域或填完整主机名，以控制台界面为准）。
   - **Domain**：选择 `agent.gilitel.com` 或 `gilitel.com` 下已授权给 Cloudflare 的域；若公司域名 **未** 托管在 Cloudflare，界面通常会提示你在 **外部 DNS** 添加记录。
   - **Service type**：HTTP  
   - **URL**：`http://localhost:8000`（连接器在本机运行时，即本机 FastAPI）。
5. 保存后，记下 Cloudflare 显示的 **DNS 说明**：
   - 一般为：在贵司 DNS 上为 **`wecom.agent.gilitel.com`** 添加 **CNAME**，指向类似 **`<tunnel-id>.cfargotunnel.com`** 的目标（**以控制台显示为准**）。

> **说明**：若公司从未把 `gilitel.com` 接入 Cloudflare，仍可通过「仅添加 CNAME」方式把子域指向 tunnel；具体以 Zero Trust 创建 Public Hostname 时的提示为准。

## 二、公司 DNS：CNAME（交给运维）

请运维在 **阿里云 DNS / 公司内部 DNS**（托管 `gilitel.com` 处）新增：

| 类型 | 主机记录 | 记录值 |
|------|----------|--------|
| CNAME | `wecom.agent`（或控制台要求的主机名） | （粘贴 Cloudflare 给出的 tunnel CNAME 目标） |

- **不要**删除或修改现有 `agent` 主机上的 A 记录（若用于公司官网/nginx），除非运维明确要求。
- 传播生效后，可用 `nslookup wecom.agent.gilitel.com` 查看是否解析到 Cloudflare/tunnel 相关目标。

**可复制给 IT 的一句话：**

> 请为 `wecom.agent.gilitel.com` 添加 CNAME，指向（粘贴 Cloudflare Tunnel 公网主机名配置页给出的目标）。用途：企业微信 HTTPS 回调到开发机上的测试服务（经 Cloudflare Tunnel）。

## 三、本机同时跑 uvicorn + cloudflared

### 终端 1：后端

```powershell
cd C:\Users\10409\Documents\work\shixi_agent\medical_agent_demo
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

### 终端 2：Tunnel 连接器

**方式 A：使用 Zero Trust 页面提供的 `tunnel run --token ...`（推荐，与 Public Hostname 配置一致）**

```powershell
cd C:\Users\10409\Documents\work\shixi_agent\medical_agent_demo
.\scripts\run_cloudflared_tunnel.ps1 -Token "粘贴ZeroTrust给出的TOKEN" -UseHttp2
```

若网络对 QUIC 不友好，务必加 **`-UseHttp2`**（等价于 `--protocol http2`）。

**方式 B：沿用 CLI 创建的命名 tunnel（仅当该 tunnel 已在 Zero Trust 中绑定同一公网主机名）**

```powershell
.\scripts\run_cloudflared_tunnel.ps1 -TunnelName "你的tunnel名" -UseHttp2
```

### 验证

浏览器访问：

- `https://wecom.agent.gilitel.com/health`  
  应看到与 `http://127.0.0.1:8000/health` 一致的 JSON（`ok: true` 等）。

## 四、企业微信后台 + `.env`

1. 自建应用 → **接收消息**：
   - **URL**：`https://wecom.agent.gilitel.com/wecom/callback`
   - **Token**、**EncodingAESKey** 与项目 `.env` 中 **`WECOM_TOKEN`**、**`WECOM_AES_KEY`** 完全一致。
2. `.env` 中同时配置：`WECOM_CORP_ID`、`WECOM_AGENT_ID`、`WECOM_SECRET`（与后台一致）。
3. 保存回调后重启 uvicorn。
4. 将应用拉入测试群，**@应用 + 文本** 验证（默认 `WECOM_ONLY_REPLY_WHEN_MENTIONED=true`）。

## 风险说明

- 笔记本关机或 `cloudflared` 退出后，外网 URL 立即不可用，企业微信回调会失败。
- 子域可改为公司规定的名称（如 `api.gilitel.com`），只要 **Public Hostname + DNS CNAME + 企微回调 URL** 三者一致即可。
