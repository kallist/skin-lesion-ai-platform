# 运维手册 (OPERATIONS)

面向"项目交接后由他人维护"的场景，覆盖模型替换、数据备份、图片存储、日志与故障处理。

---

## 1. 模型替换

```powershell
# 1) 备份当前模型
Copy-Item models\best_model.pt models\best_model.pt.bak -Force

# 2) 训练新模型（产物直接覆盖 models/best_model.pt）
python -m ml.train --model resnet101 --epochs 20 --run-name run_c_resnet101

# 3) 用验证集确认新模型优于旧模型
python -m ml.evaluate --model models\best_model.pt --split val --metrics-file artifacts\metrics_val_new.json

# 4) 只有在验证集确认更好后，才在内部测试集上做一次最终评估
python -m ml.evaluate --model models\best_model.pt --split test

# 5) 重启后端（模型是启动时加载的单例）
#    Docker: docker compose restart backend
#    本地:   重新运行 uvicorn
```

检查替换是否生效：

```bash
curl -s http://127.0.0.1:8000/api/v1/model/info | python -m json.tool
# 关注 model_version / architecture / trained_at / best_val_metric
```

**回滚**：`Copy-Item models\best_model.pt.bak models\best_model.pt -Force` 后重启。

> 注意：`models/*.pt` 被 `.gitignore` 忽略（体积大）。交付时模型文件放在
> `deliverables/models/`，或由接收方按 README 的训练步骤重新生成。

## 2. 数据库备份与恢复

```powershell
# 备份（SQLite 使用 .backup 命令保证一致性）
cd backend
..\.venv\Scripts\python.exe -c "import sqlite3;src=sqlite3.connect('data/app.sqlite3');dst=sqlite3.connect('data/backup_20260102.sqlite3');src.backup(dst);dst.close();src.close();print('backup ok')"

# 恢复
Copy-Item data\backup_20260102.sqlite3 data\app.sqlite3 -Force
# 同时必须恢复对应的 data\encrypted_uploads\ 目录，否则历史图片无法解密
```

**备份必须包含**：

1. `backend/data/app.sqlite3`（用户、会话、检测记录）
2. `backend/data/encrypted_uploads/*.enc`（加密图片）
3. `.env` 中的 `IMAGE_ENCRYPTION_KEY`（**离线单独保管**）

只备份数据库、丢失密钥 = 图片永久不可读；只备份图片、丢失数据库 = 无法关联到用户。

## 3. 图片存储管理

| 目录 | 内容 | 清理策略 |
| --- | --- | --- |
| `backend/data/encrypted_uploads/` | `det_<uuid>.enc` 加密图片 | 由记录删除驱动；孤儿文件启动时自动清理 |
| `backend/data/tmp/` | 写入中的临时密文 | 超过 1 小时自动清理 |

手动清理孤儿文件（磁盘上有、数据库里没有）：

```python
# backend 目录下运行
from app.db import SessionLocal
from app.services.detection_service import sweep_orphan_images
with SessionLocal() as db:
    print("removed:", sweep_orphan_images(db, min_age_seconds=3600))
```

估算占用：单张 224×224 PNG 密文约 50–150 KB；1000 条记录约 50–150 MB。

## 4. 会话与账号维护

```python
# 清理已过期会话
from app.db import SessionLocal
from app.services.auth_service import purge_expired_sessions
with SessionLocal() as db:
    print("purged:", purge_expired_sessions(db))
```

- 用户自助删除账号：前端"个人中心 → 删除我的账号"（级联删除记录与图片）；
- 停用某账号（不删数据）：直接改库 `UPDATE users SET is_active = 0 WHERE username = 'x';`
  停用后该用户无法登录，已有会话在下次请求时被拒绝。

## 5. 日志

| 项目 | 说明 |
| --- | --- |
| 输出 | stdout（Docker 下 `docker compose logs -f backend`） |
| 级别 | `LOG_LEVEL=INFO`（生产）；排查问题临时 `DEBUG` |
| 脱敏 | `RedactingFilter` 自动掩码密码、token、cookie、API key、Fernet 密钥、长 base64 |
| 关键日志 | `model backend '...' ready in X s`、`inference failed: <异常类型>`、`model unavailable: <原因>` |
| 禁止 | 不记录原始图片、base64 图片、请求体、完整邮箱（只记录前缀） |

日志样例：

```
2026-01-02 03:04:05 INFO    app.main | starting Skin Cancer Image Detection API v1.0.0 (production)
2026-01-02 03:04:07 INFO    app.ml   | model backend 'real' ready in 2.31s (version=1.0.0+run_a_resnet50)
2026-01-02 03:04:09 INFO    app.detection | idempotent replay for key=9f2a***
```

## 6. 监控建议

| 指标 | 来源 | 告警阈值建议 |
| --- | --- | --- |
| 服务存活 | `GET /api/v1/health` | 连续 3 次失败 |
| 模型可用性 | `health.model == true` | 任一时刻为 false |
| 数据库可用性 | `health.database == true` | 任一时刻为 false |
| 推理延迟 | 响应头 `X-Process-Time-Ms` / `inference_latency_ms` | p95 > 2 s |
| 错误率 | 日志中 5xx 计数 | > 1% |
| 磁盘 | 数据卷使用率 | > 80% |

## 7. 故障处理速查

| 症状 | 排查顺序 |
| --- | --- |
| 所有检测都 503 | ① `ls models/best_model.pt` ② 后端日志 `model load failed` ③ 用 `python -m ml.infer <图片>` 本地验证模型文件 |
| 上传全部 400 | 确认文件是真图片；`python -c "from PIL import Image;Image.open('x.jpg').verify()"` |
| 历史图片打不开（500 STORAGE_ERROR） | 检查 `IMAGE_ENCRYPTION_KEY` 是否被改动；文件是否被误删 |
| 登录后立刻 401 | 检查 Cookie 是否被浏览器拦截（`COOKIE_SECURE=true` 但用 HTTP 访问会失败） |
| 写操作 403 | 前端未带 `X-CSRF-Token`；确认 `csrf_token` Cookie 存在且未被清除 |
| 数据库 locked | 检查是否有长时间事务；SQLite 已开启 WAL 与 30s 超时 |
| 磁盘写满 | 清理 `data/tmp`，运行孤儿清理脚本，扩容数据卷 |

## 8. 升级流程

1. 备份数据（见 §2）；
2. 拉取新代码，`pip install -r backend/requirements.txt`、`npm install`；
3. 跑测试：`pytest -q`、`npm test`、`npm run build`；
4. 若表结构有变化，先迁移（见 `docs/engineering/DATABASE.md` §7）；
5. `docker compose up --build -d`（或重启本地服务）；
6. 验证：`curl /api/v1/health`、`/api/v1/model/info`、手动跑一次检测；
7. 观察日志 10 分钟，无异常后结束。
