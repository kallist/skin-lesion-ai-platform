# Windows one-click launcher

## 第一次使用

双击 `SETUP.bat`（只需一次）

## 平时启动

双击 `START.bat` → 浏览器会自动打开

## 关闭

双击 `STOP.bat`

## 查看状态

双击 `STATUS.bat`

## 出错时

打开 `logs\` 文件夹查看日志：

| 文件 | 内容 |
| --- | --- |
| `logs\launcher.log` | 启动器自己的记录（启动 / 停止 / 错误） |
| `logs\backend.log` | 后端（FastAPI + 模型加载 + 推理）输出 |
| `logs\backend.error.log` | 后端标准错误 |
| `logs\frontend.log` | 前端（Vite）输出 |
| `logs\frontend.error.log` | 前端标准错误 |

上一次启动的日志会被重命名为 `*.previous.log`。

## 重要说明

- `START.bat` 不会重新安装依赖，也不会重新训练模型，始终使用当前的 `models\best_model.pt`。
- `STOP.bat` 只关闭本项目启动的进程（通过 `.runtime\launcher.json` 中的 PID + 命令行/端口校验），不会影响 VS Code、其他 Python 或 Node 项目。
- 路径可以包含空格或中文。
- 不需要管理员权限，不修改系统 ExecutionPolicy。
- 端口被其他程序占用时启动器只会报错，不会杀掉那个程序。

> AI 辅助检测结果仅供参考，不替代专业医生诊断。
