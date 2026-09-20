# BACKEND PROMPT — 后端与安全提示词

> 本文件是后端/数据库/隐私实现阶段实际使用的指令整理稿。

## 技术栈与分层

Python + FastAPI + Pydantic + SQLAlchemy + SQLite + PyTorch + PIL。
必须分层：`API → Service → Repository → Database`，ML 路径
`DetectionService → ModelService → PyTorch Model`。**禁止把所有代码写进 main.py。**

## 数据库

至少包含 `users`、`sessions`、`detections` 三张表，字段示例：

- users：id, email(UNIQUE), username, password_hash, created_at, updated_at
- sessions：id, user_id(FK), token_hash, expires_at, created_at
- detections：id, user_id(FK), prediction, confidence, benign_probability,
  malignant_probability, model_version, encrypted_image_path, original_filename, created_at

必要时增加 idempotency_key。必须建立外键、索引、唯一约束。生成 `docs/engineering/DATABASE.md`（含 Mermaid ER 图）。

## 认证

实现注册、登录、退出、当前用户、个人信息。密码绝不能明文保存，使用 Argon2 或 bcrypt。
推荐 session cookie：HttpOnly、SameSite=Lax，生产 `Secure=true`。
禁止把密码打印到 console / log / trace / 数据库明文。

## 图像隐私

- 限制文件大小（10 MB）、只允许合法图片、**不信任 MIME header**、必须实际 decode 图片；
- 防伪装文件、防路径穿越、服务端生成文件名、去除无必要 EXIF；
- 日志不输出 raw image / base64；
- 历史功能需要保存图片 → 实现应用层加密落盘（cryptography / Fernet），
  环境变量 `IMAGE_ENCRYPTION_KEY`，不得写入 repository，`.env.example` 只放空值；
- 授权用户读取历史图片：server → authorization → decrypt → response；
- **禁止直接公开 uploads 目录**。

## 写入失败处理

推荐流程：decode + validate → inference → encrypt to temp file → atomic rename → DB transaction insert → commit；
若 DB commit 失败必须清理刚写入的 image。提供 orphan cleanup，不能留下大量孤儿文件。

## 并发

不要在 async handler 中直接阻塞 event loop；使用 threadpool 或合理同步 endpoint，
并建立 bounded concurrency（如 `ModelInferenceSemaphore`）防止 GPU OOM / CPU 饱和。
同一 model singleton 只加载一次，禁止每次 HTTP 请求重新加载模型。

## 幂等

上传接口支持可选 `Idempotency-Key`；同一用户 + 同一 key 不重复创建记录。
必须使用数据库 UNIQUE 约束或可靠事务方案，**不要只依赖 race-prone 的 if exists: insert**。

## API 清单

```
GET  /api/v1/health
POST /api/v1/auth/register | /login | /logout
GET  /api/v1/users/me          PATCH /api/v1/users/me
POST /api/v1/detections        (multipart: image, 可选 save_history=true)
GET  /api/v1/detections        GET /api/v1/detections/{id}
GET  /api/v1/detections/{id}/image      DELETE /api/v1/detections/{id}
GET  /api/v1/detections/export
GET  /api/v1/model/info
```

detection 响应必须包含 id、prediction、confidence、probabilities{benign,malignant}、
model_version、disclaimer、created_at。**不得让 frontend 自己计算 prediction。**

## 错误契约

```
{"error": {"code": "INVALID_IMAGE", "message": "上传文件不是有效图片"}}
```

覆盖 400 / 401 / 403 / 404 / 409 / 413 / 422 / 500 / 503。
**不要把 Python traceback、filesystem path、secret、SQL 直接返回客户端。**

## 失败场景必须处理

No model、Broken model file、Invalid image、Huge image、Unsupported format、Corrupted JPEG、
Database unavailable、Encryption key invalid、Disk write failure、Model inference failure、
Concurrent requests、User session expired、Deleted history、Missing encrypted image。
UI 显示友好错误，server log 记录技术错误，但日志必须 redaction。

## 安全审查清单

密码存储、会话、CORS、CSRF、IDOR、文件上传、路径穿越、文件类型伪造、
图像解压炸弹（PIL decompression bomb，设置最大像素限制）、Secrets、SQL 注入、XSS、
敏感日志、未授权历史访问。
