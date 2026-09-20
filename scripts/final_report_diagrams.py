"""Render the diagrams used by the final internship report as PNG files.

Mermaid cannot be embedded in a DOCX directly, so the architecture diagram, the
ER diagram and the ML pipeline diagram are drawn with matplotlib and written to
docs/archive/project-origin/assets/diagrams/.  Pure documentation tooling - it touches no model
or application code.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parents[1] / "docs" / "final" / "assets" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)

EDGE = "#37474f"
FILL_BROWSER = "#e3f2fd"
FILL_FRONT = "#e8f5e9"
FILL_BACK = "#fff3e0"
FILL_ML = "#f3e5f5"
FILL_DATA = "#eceff1"


def box(ax, x, y, w, h, text, *, fill, fontsize=10, bold=False, radius=0.02):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.004,rounding_size={radius}",
        linewidth=1.0, edgecolor=EDGE, facecolor=fill, zorder=2,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, zorder=3,
            fontweight="bold" if bold else "normal", linespacing=1.5)
    return (x + w / 2, y, x + w / 2, y + h)


def arrow(ax, start, end, *, style="-|>", color=EDGE, lw=1.2, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle=style, color=color, linewidth=lw,
        linestyle=ls, mutation_scale=12, zorder=1,
        connectionstyle=f"arc3,rad={rad}",
    ))


# ----------------------------------------------------------------- architecture
fig, ax = plt.subplots(figsize=(7.4, 8.6))
ax.set_xlim(0, 10)
ax.set_ylim(0, 12)
ax.axis("off")

box(ax, 2.6, 11.0, 4.8, 0.8, "用户浏览器（Chrome / Edge / Firefox / Safari）",
    fill=FILL_BROWSER, bold=True, fontsize=11)

box(ax, 0.4, 9.0, 4.2, 1.5,
    "前端  React 18 + TypeScript + TailwindCSS\n"
    "页面路由 / 上传交互 / 结果可视化 / 状态与错误处理",
    fill=FILL_FRONT, fontsize=9.5)
box(ax, 5.4, 9.0, 4.2, 1.5,
    "API 客户端\n携带会话 Cookie、CSRF 头\n统一错误契约解析",
    fill=FILL_FRONT, fontsize=9.5)

box(ax, 1.2, 7.0, 7.6, 1.2,
    "FastAPI 接口层（/api/v1：auth / users / detections / system）\n"
    "请求校验（Pydantic 2）· 依赖注入 · 会话与 CSRF 校验 · 统一错误处理",
    fill=FILL_BACK, fontsize=9.5)

box(ax, 0.4, 5.0, 4.4, 1.3,
    "业务服务层\n认证服务 · 检测服务\n用户服务 · 图片加密存储",
    fill=FILL_BACK, fontsize=9.5)
box(ax, 5.2, 5.0, 4.4, 1.3,
    "模型服务（进程内单例）\n加载一次 · 信号量限流\n线程池执行阻塞推理",
    fill=FILL_ML, fontsize=9.5)

box(ax, 5.2, 3.1, 4.4, 1.1,
    "PyTorch ResNet50\nmodels/best_model.pt（224×224 输入，二分类）",
    fill=FILL_ML, fontsize=9.5)
box(ax, 0.4, 3.1, 4.4, 1.1,
    "SQLAlchemy 2 ORM\nusers / sessions / detections",
    fill=FILL_DATA, fontsize=9.5)

box(ax, 0.4, 1.2, 4.4, 1.1, "SQLite 数据库\nbackend/data/app.sqlite3",
    fill=FILL_DATA, fontsize=9.5)
box(ax, 5.2, 1.2, 4.4, 1.1, "加密图片目录（Fernet）\nbackend/data/encrypted_uploads",
    fill=FILL_DATA, fontsize=9.5)

arrow(ax, (5.0, 11.0), (5.0, 10.5))
arrow(ax, (2.5, 10.5), (2.5, 10.5 - 0.4))
arrow(ax, (5.0, 9.75), (5.0, 8.2), rad=0)
arrow(ax, (7.5, 9.0), (7.5, 8.2))
arrow(ax, (2.6, 7.0), (2.6, 6.3))
arrow(ax, (7.4, 7.0), (7.4, 6.3))
arrow(ax, (7.4, 5.0), (7.4, 4.2))
arrow(ax, (2.6, 5.0), (2.6, 4.2))
arrow(ax, (2.6, 3.1), (2.6, 2.3))
arrow(ax, (7.4, 3.1), (7.4, 2.3))
ax.text(5.05, 10.72, "HTTPS / JSON · multipart", fontsize=8, ha="left", color="#546e7a")
ax.text(8.9, 8.55, "GET /health\nGET /model/info", fontsize=8, ha="center", color="#546e7a")
ax.text(0.35, 2.55, "SQL 读写（事务）", fontsize=8, ha="left", color="#546e7a")
ax.text(9.75, 2.55, "密文写入 / 授权解密", fontsize=8, ha="right", color="#546e7a")

ax.set_title("图 3-1  系统总体架构", fontsize=12, pad=6)
fig.tight_layout()
fig.savefig(OUT / "architecture.png", dpi=170)
plt.close(fig)
print("[diagram] architecture.png")

# ----------------------------------------------------------------- ER diagram
fig, ax = plt.subplots(figsize=(7.4, 4.4))
ax.set_xlim(0, 10)
ax.set_ylim(0, 6)
ax.axis("off")


def entity(ax, x, y, w, title, rows, fill):
    h = 0.42 + 0.3 * len(rows)
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.03",
                                linewidth=1.1, edgecolor=EDGE, facecolor="white", zorder=2))
    ax.add_patch(FancyBboxPatch((x, y + h - 0.42), w, 0.42,
                                boxstyle="round,pad=0.01,rounding_size=0.03",
                                linewidth=1.1, edgecolor=EDGE, facecolor=fill, zorder=3))
    ax.text(x + w / 2, y + h - 0.21, title, ha="center", va="center",
            fontsize=10, fontweight="bold", zorder=4)
    for index, row in enumerate(rows):
        ax.text(x + 0.12, y + h - 0.62 - 0.3 * index, row, ha="left", va="center",
                fontsize=8.6, zorder=4)
    return h


h_user = entity(ax, 0.3, 3.0, 3.4, "users", [
    "id  INTEGER  PK",
    "email  UNIQUE  INDEX",
    "username  UNIQUE  INDEX",
    "password_hash  (Argon2id)",
    "full_name / is_active",
    "created_at / updated_at",
], FILL_FRONT)

h_session = entity(ax, 6.3, 3.3, 3.4, "sessions", [
    "id  INTEGER  PK",
    "user_id  FK → users.id",
    "token_hash  UNIQUE  INDEX",
    "csrf_token_hash",
    "expires_at / revoked_at",
], FILL_BACK)

h_detect = entity(ax, 3.3, 0.4, 3.4, "detections", [
    "id  INTEGER  PK",
    "user_id  FK → users.id",
    "prediction / confidence",
    "benign_probability",
    "malignant_probability",
    "model_version",
    "encrypted_image_path",
    "original_filename / created_at",
], FILL_ML)

arrow(ax, (3.7, 4.4), (6.3, 4.4), style="-|>", lw=1.1)
arrow(ax, (3.7, 3.6), (6.3, 3.6), style="<|-|>", lw=1.1, color="#90a4ae")
ax.text(5.0, 4.55, "1 : N", fontsize=9, ha="center")
arrow(ax, (2.0, 3.0), (4.4, 3.0 - 0.2), style="-|>", lw=1.1, rad=0.15)
ax.text(2.9, 2.35, "1 : N（级联删除）", fontsize=9, ha="center")

ax.set_title("图 8-1  数据库实体关系（SQLite）", fontsize=12, pad=6)
fig.tight_layout()
fig.savefig(OUT / "erd.png", dpi=170)
plt.close(fig)
print("[diagram] erd.png")

# ----------------------------------------------------------------- ML pipeline
fig, ax = plt.subplots(figsize=(7.4, 3.4))
ax.set_xlim(0, 10)
ax.set_ylim(0, 4)
ax.axis("off")

stages = [
    ("原始数据\n1840 张", FILL_DATA),
    ("审计与去重\n损坏 0 / 重复 1 组", FILL_DATA),
    ("分组分层划分\n1294 / 276 / 270", FILL_FRONT),
    ("训练（两阶段迁移学习）\n12 epochs，best 7", FILL_ML),
    ("验证集选模型\nval ROC-AUC 0.9773", FILL_ML),
    ("内部测试集评估\nAccuracy 92.96%", FILL_BACK),
    ("学校独立测试\nAccuracy 78.54%", FILL_BROWSER),
]
w, gap = 1.24, 0.15
x = 0.15
centres = []
for index, (label, fill) in enumerate(stages):
    box(ax, x, 1.5, w, 1.15, label, fill=fill, fontsize=8.2)
    centres.append((x, x + w))
    if index:
        arrow(ax, (x - gap, 2.07), (x, 2.07), lw=1.1)
    x += w + gap

ax.annotate("", xy=(centres[-1][1], 0.95), xytext=(centres[-2][0], 0.95),
            arrowprops=dict(arrowstyle="-|>", color="#c62828", lw=1.3))
ax.text(5.0, 0.55, "冻结模型直接评测：不重新训练、不微调、不调整阈值",
        fontsize=9, ha="center", color="#c62828")
ax.set_title("图 5-1  数据与模型流程", fontsize=12, pad=6)
fig.tight_layout()
fig.savefig(OUT / "ml_pipeline.png", dpi=170)
plt.close(fig)
print("[diagram] ml_pipeline.png")
