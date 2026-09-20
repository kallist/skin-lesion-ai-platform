# REVIEW PROMPT — 独立审查提示词

> 本文件是实现完成后的独立审查阶段实际使用的指令整理稿。

## 立场

**假设你不是原实现者。** 不要因为代码是自己写的就降低标准。
以外部审查者、安全审查员、ML 复核者的视角重新检查。

## 审查范围

| 维度 | 检查点 |
| --- | --- |
| Requirements | PRD 中的每条 FR / NFR 是否有对应实现与测试 |
| Architecture | 分层是否被遵守；是否存在 main.py 里堆业务逻辑；模型是否单例 |
| ML correctness | 划分是否科学；是否数据泄漏；增强是否过度；模型选择是否只用验证集 |
| Data leakage | train/val/test 交集；重复图/近重复图；测试集是否被用于调参 |
| Security | 密码哈希、会话、CSRF、CORS、IDOR、上传校验、路径穿越、解压炸弹、Secrets |
| Privacy | 图片是否加密落盘；读取是否授权；日志是否泄露敏感信息；EXIF 是否去除 |
| Authentication | 会话过期、注销、并发注册、限流、Cookie 属性 |
| Concurrency | 事件循环是否被阻塞；是否有并发上限；模型是否重复加载 |
| Error handling | 统一错误契约；是否泄露内部信息；失败是否回滚 |
| Frontend | 是否自行计算预测；免责声明是否常驻；是否依赖颜色；移动端可用性 |
| API | 契约与文档是否一致；状态码是否正确；幂等是否可靠 |
| Tests | 覆盖是否真实；是否有 mock 掩盖问题；是否有真实模型冒烟 |
| Docker | 配置是否可解析；密钥是否从环境注入；数据是否持久化；健康检查 |
| Documentation | 是否与实际代码一致；是否夸大结果 |
| Project deliverables | 交付物清单是否齐全（见 docs/archive/project-origin/DELIVERY_CHECKLIST.md） |

## 严重度分级

- **Critical**：数据泄漏、伪造指标、认证绕过、密钥泄露、模型未真实训练
- **High**：IDOR、CSRF 缺失、路径穿越、未加密存储、错误信息泄露内部细节
- **Medium**：幂等竞态、并发阻塞、孤儿文件、文案违规、无障碍缺陷

## 处理规则

- Critical / High：**必须修复**；
- Medium：属于本次 scope 且修复风险低的也修复；
- 修完重新执行相关测试，然后再次检查 `git diff` 与 `git status`。

## 输出格式

```
Critical: <数量> — <问题与处理>
High:     <数量> — <问题与处理>
Medium:   <数量> — <问题与处理>
Fixed:    <已修复项>
Remaining:<未修复项及原因>
```

**不得使用模糊语言**；不得把未修复的 High 说成"可接受"。
