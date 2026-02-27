# H5 三模块前端 + FastAPI 网关（独立目录）

本目录是独立实现，不改动 OctopusAI 现有逻辑。

## 模块

- 个性化语音（语音设计）
- 语音生成（语音合成）
- 环境音效（视频环境音）

## 功能

- H5 三模块界面（按你给的模块字段搭建）
- FastAPI 统一入口
- 串行队列（一次只执行一个任务）
- 任务状态轮询与结果下载
- 联调别名接口（`/api/run/{app}`、`/api/status`）

## 本地启动

```bash
pip install -r h5_gateway/requirements.txt
uvicorn h5_gateway.app:app --host 0.0.0.0 --port 8000
```

打开：

- `http://127.0.0.1:8000/`

接口健康检查：

- `http://127.0.0.1:8000/api/health`

联调入口（先可访问、先联调）：

- `POST /api/run/{app}`（`app1/voice_design` 已接入真实队列）
- `GET /api/status`（队列状态别名）

## 服务连接（环境变量）

按你服务器里 3 个服务实际地址修改：

```bash
export VOICE_DESIGN_URL="http://127.0.0.1:9001/infer"
export TTS_URL="http://127.0.0.1:9002/infer"
export ENV_AUDIO_URL="http://127.0.0.1:9003/infer"
```

如果服务字段名不同，可覆盖字段映射（示例）：

```bash
export VOICE_DESIGN_TEXT_FIELD="text"
export TTS_REF_AUDIO_FIELD="reference_audio"
export ENV_VIDEO_FIELD="video"
```

## 对外访问

云平台端口映射建议（任选其一）：

- 方案 A（简单）：`18080 -> 8000`
- 方案 B（推荐）：`80 -> 80`，Nginx 反向代理到 `127.0.0.1:8000`

外部访问：

- `http://你的公网地址:18080/`

## 服务器部署（推荐）

以下步骤在服务器中执行（假设代码路径为 `/opt/h5_gateway`）：

```bash
cd /opt/h5_gateway
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
chmod +x deploy/start.sh
```

### 方式 1：直接启动（用于验证）

```bash
cd /opt/h5_gateway
APP_HOST=0.0.0.0 APP_PORT=8000 ./deploy/start.sh
```

### 方式 2：systemd 常驻（生产）

```bash
cp /opt/h5_gateway/deploy/h5-gateway.service /etc/systemd/system/h5-gateway.service
systemctl daemon-reload
systemctl enable --now h5-gateway
systemctl status h5-gateway
```

### 方式 3：Nginx 对外暴露 80（生产推荐）

```bash
cp /opt/h5_gateway/deploy/nginx-h5-gateway.conf /etc/nginx/conf.d/h5-gateway.conf
nginx -t
systemctl reload nginx
```

说明：该 Nginx 配置已经是「静态 H5 + 反代 /api」模式：

- `/` 直接返回 `/opt/h5_gateway/static/index.html`
- `/api/*` 转发到 `127.0.0.1:8000`

完成后外网访问：

- `http://你的公网IP/`
- `http://你的公网IP/api/health`
- `http://你的公网IP/api/status`

联调调用示例：

```bash
curl -X POST "http://你的公网IP/api/run/app1" \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，这是联调文本","language":"Chinese"}'
```

## 常见问题

- SSH 连不上但平台 WebSSH 能进：通常是认证链路不同，先把本机公钥写入服务器对应用户的 `~/.ssh/authorized_keys`。
- 页面能开但提交失败：确认 `VOICE_DESIGN_URL`、`TTS_URL`、`ENV_AUDIO_URL` 在服务器内网可访问。
- 大文件上传失败：检查 Nginx `client_max_body_size`（本项目配置为 `512m`）。
