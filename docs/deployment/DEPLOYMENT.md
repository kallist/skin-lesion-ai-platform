# 部署文档 (DEPLOYMENT)

本文件说明三种运行方式：**本地开发**、**Docker Compose**、**生产注意事项**。

---

## 1. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 开发环境实测 3.10.6 |
| Node.js | 18+ | 实测 24.10.0 |
| PyTorch | 2.5.1 | CPU 或 CUDA 12.1 版本均可 |
| Docker | 24+（可选） | 需要 Docker Desktop / Engine |
| 磁盘 | ≥ 8 GB | CUDA 版 PyTorch 约 4.9 GB，模型约 100 MB |

GPU 说明：训练在有 NVIDIA GPU（RTX 3060 6 GB）的机器上完成；推理在 CPU 上同样可运行（延迟见 `docs/ml/MODEL_REPORT.md`）。

## 2. 本地开发

### 2.1 一键准备（PowerShell）

```powershell
cd <项目根目录>

# 1) 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) 安装依赖
pip install -r backend\requirements.txt
# CPU 版 PyTorch（体积小、无 GPU 也能跑）
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
# 有 NVIDIA GPU 时改用：
# pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121

# 3) 准备数据（审计 + 划分）
python -m ml.prepare_data

# 4) 训练（首次约 10–20 分钟，取决于 GPU）
python -m ml.train --model resnet50 --epochs 18 --batch-size 32

# 5) 评估
python -m ml.evaluate --model models\best_model.pt --split test

# 6) 配置环境变量
Copy-Item .env.example .env
python -c "import secrets;print('SESSION_SECRET='+secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet;print('IMAGE_ENCRYPTION_KEY='+Fernet.generate_key().decode())"
# 把上面两条输出填进 .env

# 7) 启动后端
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 8) 启动前端（另开一个终端）
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

### 2.2 访问地址

| 服务 | 地址 |
| --- | --- |
| 前端 | http://127.0.0.1:5173 |
| 后端 API | http://127.0.0.1:8000/api/v1 |
| Swagger 文档 | http://127.0.0.1:8000/docs |
| 健康检查 | http://127.0.0.1:8000/api/v1/health |

开发模式下 Vite 把 `/api` 代理到 `http://127.0.0.1:8000`，因此浏览器看到同源请求，Cookie 为第一方 Cookie。

### 2.3 测试

```powershell
# 后端
cd backend; ..\.venv\Scripts\python.exe -m pytest -q

# 前端单元测试与构建
cd frontend; npm test; npm run build

# E2E（需要先启动后端与前端 preview）
cd frontend; npm run e2e
```

## 3. Docker Compose

### 3.1 前置条件

- `models/best_model.pt` 必须存在（训练产物，约 100 MB，未提交到 Git）；
- `.env` 中的两个密钥必须填写。

```powershell
# 生成密钥并写入 .env
python scripts\generate_secrets.py >> .env
```

### 3.2 启动

```bash
docker compose up --build
```

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| frontend | 8080 | nginx 托管 SPA，并把 `/api` 反向代理到 backend |
| backend | 8000（内部） | uvicorn 运行 FastAPI，健康检查 `GET /api/v1/health` |

访问：http://localhost:8080

### 3.3 数据卷

| 卷 | 挂载点 | 内容 |
| --- | --- | --- |
| `backend-data` | `/app/backend/data` | SQLite 数据库 + 加密图片目录 |
| `./models` | `/app/models` (只读) | 训练好的模型文件 |

备份 = 备份 `backend-data` 卷 + `.env` 中的 `IMAGE_ENCRYPTION_KEY`（缺一不可）。

### 3.4 常用命令

```bash
docker compose logs -f backend          # 查看后端日志
docker compose exec backend ls /app/models
docker compose down                     # 停止（保留卷）
docker compose down -v                  # 停止并删除数据卷（会丢数据！）
```

## 4. 生产注意事项

| 项目 | 要求 |
| --- | --- |
| HTTPS | 必须。前置 nginx/Caddy 终止 TLS；设置 `COOKIE_SECURE=true` |
| 密钥 | `SESSION_SECRET`、`IMAGE_ENCRYPTION_KEY` 必须由密钥管理系统注入，**禁止写入镜像或仓库** |
| 环境 | `APP_ENV=production`（未设置密钥时应用会拒绝启动并给出明确错误） |
| CORS | `CORS_ORIGINS` 只填真实前端域名，禁止 `*` |
| 反向代理 | 上传体积限制需 ≥ `MAX_UPLOAD_MB`；示例 nginx 配置见 `frontend/nginx.conf` |
| 数据库 | SQLite 适合单机小规模；并发写入高时迁移到 PostgreSQL（`DATABASE_URL` 换驱动即可，ORM 层无需改动） |
| 模型更新 | 替换 `models/best_model.pt` 后重启后端；`/api/v1/model/info` 会显示新版本 |
| 日志 | 已内置密钥/令牌脱敏；生产建议接入集中式日志并保留 ≥ 30 天 |
| 备份 | 每日备份 `data/` 目录；密钥单独离线保管 |
| 资源 | 单实例建议 ≥ 2 vCPU / 4 GB 内存；`INFERENCE_CONCURRENCY` 按 CPU 核数调整 |

## 5. 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 启动报 `IMAGE_ENCRYPTION_KEY must be set` | 生产环境未配置密钥 | 生成并写入 `.env` 或环境变量 |
| `/health` 返回 `"model": false` | 模型文件缺失或损坏 | 检查 `MODEL_PATH`；重新训练或放置 `best_model.pt` |
| 检测返回 503 | 模型未加载 | 查看后端日志中 `model load failed` 的具体原因 |
| 前端请求 401 | 会话过期 | 重新登录；检查系统时间与 `SESSION_TTL_HOURS` |
| 前端请求 403 | 缺少 CSRF 令牌 | 确认前端读取到 `csrf_token` Cookie |
| 上传返回 413 | 超过 `MAX_UPLOAD_MB` | 调整限制或压缩图片 |
| 图片无法解密 | 密钥与加密时不一致 | 必须使用同一 `IMAGE_ENCRYPTION_KEY` 恢复数据 |

更多运维细节见 [OPERATIONS.md](OPERATIONS.md)。
