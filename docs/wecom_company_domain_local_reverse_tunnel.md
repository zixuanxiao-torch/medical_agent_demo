# 企业微信接入（本机运行 + 公司域名 + 反向通道）

适用场景：

- 你的应用继续只跑在本机：`http://127.0.0.1:8000`
- 企业微信回调要用公司域名：`https://agent.gilitel.com/wecom/callback`
- 公司运维可改 `agent.gilitel.com` 的 nginx

核心思路：

1. 你在本机跑 FastAPI。
2. 你建立一个“公司服务器 -> 本机”的反向通道（SSH reverse 或 frp）。
3. 公司 nginx 把 `/wecom/callback` 反代到这个映射端口。

## 一、建议方案选择

优先级（从易维护到灵活）：

1. 你们已有 SSH 服务器权限：用 SSH reverse tunnel（最简单）。
2. 你们已有 frp：用 frp（更可控，适合长期）。

## 二、运维需要做什么（必做）

在 `agent.gilitel.com` 的 nginx 上配置 HTTPS（证书有效）并新增反代：

```nginx
server {
    listen 443 ssl;
    server_name agent.gilitel.com;
    # ssl_certificate ...;
    # ssl_certificate_key ...;

    location /wecom/callback {
        proxy_pass http://127.0.0.1:18000/wecom/callback;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:18000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

说明：

- 这里的 `127.0.0.1:18000` 是“公司服务器本地映射端口”，由你建立反向通道后提供。
- 若运维要求走内网地址，也可以改成内网 IP:端口。

## 三、你本机需要做什么

### 1）启动后端

```powershell
cd C:\Users\10409\Documents\work\shixi_agent\medical_agent_demo
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

### 2）建立反向通道

#### 方案 A：SSH reverse tunnel（推荐起步）

使用脚本：

```powershell
.\scripts\run_reverse_ssh_tunnel.ps1 -SshUser "你的用户名" -SshHost "agent.gilitel.com" -RemotePort 18000 -LocalPort 8000
```

或直接命令：

```powershell
ssh -NT -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -R 127.0.0.1:18000:127.0.0.1:8000 你的用户名@agent.gilitel.com
```

#### 方案 B：frp

由运维在服务器侧配置 `frps`，你在本机跑 `frpc`，把本机 8000 映射到服务器本地端口 18000。

## 四、验证连通性

1. 本机先确认：`http://127.0.0.1:8000/health` 可访问。
2. 反向通道建立后，请运维在服务器上执行：

```bash
curl http://127.0.0.1:18000/health
```

应返回 `ok: true`。

3. 你在外网浏览器访问：

- `https://agent.gilitel.com/health`

应返回 `ok: true`。

## 五、企业微信后台配置

自建应用 -> 接收消息：

- URL：`https://agent.gilitel.com/wecom/callback`
- Token：与 `.env` 的 `WECOM_TOKEN` 一致
- EncodingAESKey：与 `.env` 的 `WECOM_AES_KEY` 一致

并确保 `.env` 填好：

- `WECOM_CORP_ID`
- `WECOM_AGENT_ID`
- `WECOM_SECRET`
- `WECOM_TOKEN`
- `WECOM_AES_KEY`

修改后重启 `uvicorn`。

## 六、验收标准

1. 企业微信后台保存回调通过。
2. 群里 `@应用 + 文本`，机器人能回复。
3. 若开启 `debug`，可看到你现有工具调用链（例如 `kb_retrieve`）。
