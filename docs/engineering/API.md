# API 接口文档 (API)

- Base URL：`http://<host>:8000/api/v1`
- 交互式文档：`/docs`（Swagger UI）、`/redoc`
- 数据格式：`application/json; charset=utf-8`（文件上传为 `multipart/form-data`）
- 认证：**HttpOnly Cookie 会话**（`skin_session`）+ 写操作 `X-CSRF-Token` 请求头
- 时间：ISO-8601 UTC 字符串，例如 `2026-01-02T03:04:05+00:00`

---

## 1. 统一错误契约

所有错误响应体格式固定：

```json
{
  "error": {
    "code": "INVALID_IMAGE",
    "message": "上传文件不是有效图片",
    "details": { "field": "image" }
  }
}
```

`details` 可选。**绝不返回** Python traceback、文件路径、SQL 语句或任何密钥。

| HTTP | code | 触发场景 |
| ---: | --- | --- |
| 400 | `BAD_REQUEST` / `INVALID_IMAGE` / `UNSUPPORTED_IMAGE_TYPE` | 请求非法、图片无法解码、格式不支持 |
| 401 | `UNAUTHENTICATED` | 未登录或会话失效 |
| 403 | `FORBIDDEN` | 缺少/错误 CSRF 令牌、功能被关闭 |
| 404 | `NOT_FOUND` | 资源不存在或不属于当前用户 |
| 405 | `METHOD_NOT_ALLOWED` | 方法不允许 |
| 409 | `CONFLICT` | 邮箱/用户名重复、密码强度不足 |
| 413 | `FILE_TOO_LARGE` | 文件或像素数超限 |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | 媒体类型不支持 |
| 422 | `VALIDATION_ERROR` | 请求参数校验失败（`details.fields[]`） |
| 429 | `RATE_LIMITED` | 登录尝试过于频繁 |
| 500 | `INFERENCE_FAILED` / `STORAGE_ERROR` / `INTERNAL_ERROR` | 推理失败、存储失败、未捕获异常 |
| 503 | `MODEL_UNAVAILABLE` | 模型未加载或文件损坏 |

## 2. 系统

### 2.1 GET /health

无需认证。用于 Docker healthcheck 与前端状态提示。

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "development",
  "database": true,
  "model": true,
  "model_version": "1.0.0+run_a_resnet50",
  "uptime_seconds": 123.45
}
```

`status` 为 `ok`（数据库与模型都可用）或 `degraded`。

### 2.2 GET /model/info

返回当前服务模型的元数据。**前端必须从这里获取类别映射，不得自行猜测标签顺序。**

```json
{
  "model_version": "1.0.0+run_a_resnet50",
  "architecture": "resnet50",
  "input_size": 224,
  "class_names": ["benign", "malignant"],
  "class_mapping": { "benign": 0, "malignant": 1 },
  "trained_at": "2026-01-02T03:04:05+00:00",
  "device": "cuda",
  "calibration": "NOT IMPLEMENTED",
  "disclaimer": "AI辅助检测结果，仅供参考，不构成医学诊断。",
  "available": true,
  "best_val_metric": { "accuracy": 0.9, "roc_auc": 0.95 }
}
```

## 3. 认证

### 3.1 POST /auth/register

请求：

```json
{
  "email": "user@example.com",
  "username": "user01",
  "password": "Str0ngPass!",
  "full_name": "张三"
}
```

约束：`email` 合法邮箱且唯一；`username` 3–64 字符、`[A-Za-z0-9._-]`、唯一；
`password` 8–128 字符且至少包含大小写字母/数字/符号中的两类。

响应 `201`：

```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "user01",
    "full_name": "张三",
    "created_at": "2026-01-02T03:04:05+00:00",
    "updated_at": "2026-01-02T03:04:05+00:00"
  },
  "csrf_token": "VJ3s...",
  "message": "注册成功"
}
```

同时下发两个 Cookie：`skin_session`（HttpOnly, SameSite=Lax）与 `csrf_token`（可被 JS 读取）。

### 3.2 POST /auth/login

```json
{ "identifier": "user@example.com", "password": "Str0ngPass!" }
```

`identifier` 可以是邮箱或用户名。成功返回同注册；失败统一 `401 UNAUTHENTICATED`，
不区分"用户不存在"与"密码错误"；连续失败达到阈值返回 `429 RATE_LIMITED`。

### 3.3 POST /auth/logout

无需有效会话即可调用（幂等），清除 Cookie 并吊销当前会话。返回 `{"message": "已退出登录"}`。

### 3.4 GET /auth/session

需要登录。用于 SPA 刷新后恢复登录态：

```json
{ "user": { "...": "..." }, "csrf_token": "", "message": "ok" }
```

未登录返回 `401 UNAUTHENTICATED`。

### 3.5 POST /auth/logout-all

需要登录。吊销该用户全部会话，返回 `{"message": "已退出全部 3 个会话"}`。

## 4. 用户

### 4.1 GET /users/me

需要登录，返回当前用户对象（字段同注册响应中的 `user`）。

### 4.2 PATCH /users/me

需要登录 **且需要 `X-CSRF-Token`**。

```json
{ "full_name": "李四", "username": "user02" }
```

两个字段都可选；用户名冲突返回 `409 CONFLICT`。

### 4.3 DELETE /users/me

需要登录 **且需要 `X-CSRF-Token`**。删除账号、全部会话、全部检测记录与加密图片。

```json
{ "message": "账号及全部检测记录已删除" }
```

## 5. 检测

### 5.1 POST /detections

需要登录。`multipart/form-data`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `image` | File | 是 | JPG / PNG / WEBP / BMP，≤ 10 MB，像素数 ≤ 4000 万 |
| `save_history` | bool | 否（默认 true） | 是否保存到历史（保存即加密落盘） |

请求头（可选）：

| 头 | 说明 |
| --- | --- |
| `Idempotency-Key` | 客户端生成的幂等键；同一用户 + 同一 key 不会重复创建记录 |

响应 `201`：

```json
{
  "id": 42,
  "prediction": "malignant",
  "confidence": 0.9312,
  "probabilities": { "benign": 0.0688, "malignant": 0.9312 },
  "model_version": "1.0.0+run_a_resnet50",
  "original_filename": "mole.jpg",
  "image_available": true,
  "disclaimer": "AI辅助检测结果，仅供参考，不构成医学诊断。",
  "advice": "模型检测结果倾向于恶性风险。该结果不能替代医生诊断，建议尽快由皮肤科专业人员进一步评估；若皮损出现快速增大、颜色改变、破溃或出血，请尽快就医。",
  "created_at": "2026-01-02T03:04:05+00:00"
}
```

`prediction` 只可能是 `benign` 或 `malignant`；`confidence` 恒等于被选中类别的概率。

常见错误：`400 INVALID_IMAGE`（非图片/损坏）、`400 UNSUPPORTED_IMAGE_TYPE`、
`413 FILE_TOO_LARGE`、`401 UNAUTHENTICATED`、`403 FORBIDDEN`（缺少 `X-CSRF-Token`）、
`409 IDEMPOTENCY_CONFLICT`、`503 MODEL_UNAVAILABLE`、`500 INFERENCE_FAILED`。

> **CSRF**：本接口是写操作，**必须携带 `X-CSRF-Token`**（值取自登录时下发的 `csrf_token` Cookie）。
> 浏览器端由前端 API 客户端自动附加；该要求由回归测试锁定。

### 5.2 GET /detections

需要登录。查询参数：

| 参数 | 默认 | 约束 | 说明 |
| --- | --- | --- | --- |
| `page` | 1 | 1–10000 | 页码 |
| `page_size` | 20 | 1–100 | 每页条数 |
| `prediction` | 空 | `benign` \| `malignant` | 结果筛选 |

```json
{
  "items": [
    {
      "id": 42,
      "prediction": "malignant",
      "confidence": 0.9312,
      "probabilities": { "benign": 0.0688, "malignant": 0.9312 },
      "model_version": "1.0.0+run_a_resnet50",
      "original_filename": "mole.jpg",
      "image_available": true,
      "created_at": "2026-01-02T03:04:05+00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

### 5.3 GET /detections/{id}

需要登录。返回单条记录（结构同 5.1 响应）。**不属于当前用户时返回 `404`。**

### 5.4 GET /detections/{id}/image

需要登录。授权校验通过后解密返回 PNG：

```
Content-Type: image/png
Cache-Control: private, max-age=60, no-store
X-Content-Type-Options: nosniff
```

未登录 `401`；非本人记录 `404`；密文丢失或密钥不匹配 `500 STORAGE_ERROR`。

### 5.5 DELETE /detections/{id}

需要登录 **且需要 `X-CSRF-Token`**。删除记录并删除磁盘上的密文。

```json
{ "message": "检测记录已删除" }
```

### 5.6 GET /detections/export

需要登录。返回 CSV 下载：

```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="detection_history_20260102-030405.csv"
```

列：`id, created_at, prediction, confidence, benign_probability, malignant_probability,
model_version, original_filename, inference_latency_ms`。

**CSV 不包含任何原始图片数据。** 支持可选筛选：`prediction`、`date_from`、`date_to`。

## 6. 调用示例

```bash
# 注册并保存 Cookie
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"u@example.com","username":"u1","password":"Str0ngPass!"}'

# 上传检测（带幂等键）
curl -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/detections \
  -H "Idempotency-Key: $(uuidgen)" \
  -F "image=@lesion.jpg" -F "save_history=true"

# 历史列表
curl -b cookies.txt "http://127.0.0.1:8000/api/v1/detections?page=1&page_size=10"

# 导出 CSV
curl -b cookies.txt -o history.csv http://127.0.0.1:8000/api/v1/detections/export
```

> 写操作通过浏览器调用时，前端会自动带上 `X-CSRF-Token`（读取 `csrf_token` Cookie）。
> 用 curl 调用 PATCH/DELETE 时需手动添加该头。

## 7. CORS

允许来源由 `CORS_ORIGINS` 环境变量控制（逗号分隔），`allow_credentials=true`，
允许方法 `GET/POST/PATCH/DELETE/OPTIONS`，允许请求头 `Content-Type`、`X-CSRF-Token`、`Idempotency-Key`。

开发环境前端通过 Vite 代理 `/api`，因此浏览器看到的是同源请求，Cookie 为第一方 Cookie。
