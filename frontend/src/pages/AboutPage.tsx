import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import Disclaimer from '../components/Disclaimer';
import type { Health, ModelInfo } from '../types';
import { formatDateTime } from '../utils/format';

/** Facts about the project itself.  Everything here is verifiable in the
 *  repository (artifacts/, models/model_meta.json, docs/). */
const ENGINEERING_SCOPE = [
  ['数据处理与模型', '数据审计、重复图分组、group-aware 分层划分、ResNet50 两阶段迁移学习、早停与模型元数据'],
  ['推理服务', 'FastAPI 服务化、模型单例加载、训练/评估/服务共用同一套预处理、并发上限与超时保护'],
  ['Web 产品化', 'React 18 + TypeScript 界面、注册登录、上传检测、结果可视化、历史与对比、CSV 导出'],
  ['安全与隐私', 'Argon2id 口令哈希、HttpOnly 会话 Cookie、CSRF 双重提交、越权访问防护、图像 Fernet 加密、EXIF 剥离'],
  ['质量与验证', 'pytest、Vitest、Playwright 端到端测试、真实模型冒烟测试、内部测试与独立外部测试'],
];

export default function AboutPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [model, setModel] = useState<ModelInfo | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.modelInfo().then(setModel).catch(() => setModel(null));
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">关于本平台</h1>
        <p className="mt-1 text-sm text-slate-600">
          皮肤病变智能识别与辅助分析平台 · AI 应用工程实践项目
        </p>
      </header>

      <Disclaimer />

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">项目定位</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          皮肤病变的外观差异细微，普通人很难判断哪些皮损需要尽快就医。本项目把「上传一张照片、
          得到一个良恶性倾向提示并留下可追踪的记录」做成了一条完整的端到端链路：
          数据准备与审计 → 模型训练与评估 → 模型服务化 → Web 产品化 → 安全与隐私设计 →
          自动化测试 → 独立外部验证。
        </p>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          它的用途是 <strong>AI 工程实践与皮肤健康辅助分析</strong>，
          不是医疗器械，也不提供诊断结论。模型在内部测试集与独立外部测试集上的
          实测指标、混淆矩阵与曲线见
          <Link to="/evaluation" className="font-medium text-brand-700 hover:underline">
            模型评测
          </Link>
          页。
        </p>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">项目背景与我的角色</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          本项目为校企联合 AI 应用实习实践项目，由广州泰迪智能科技有限公司相关人员参与项目指导与实践。
          项目并非该公司的商业产品或生产系统，也没有在任何医疗机构上线使用。
        </p>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          我在项目中承担 AI 应用开发与产品设计工作：梳理需求与验收标准，
          组织数据结构与划分方案，完成模型训练与评估，把模型封装为后端服务并实现前端界面，
          补齐安全与隐私设计，最后用自动化测试和独立外部评测验证交付质量。
        </p>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">工程范围</h2>
        <dl className="mt-3 space-y-3 text-sm">
          {ENGINEERING_SCOPE.map(([term, detail]) => (
            <div key={term} className="rounded-xl bg-slate-50 p-4">
              <dt className="font-semibold text-slate-700">{term}</dt>
              <dd className="mt-1 leading-relaxed text-slate-600">{detail}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">算法说明</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-relaxed text-slate-700">
          <li>
            用户上传的图片在服务端被真实解码（不信任文件扩展名与 MIME 声明），
            校验格式、体积与像素数后去除 EXIF 等元数据。
          </li>
          <li>
            图像被缩放到 224×224 并做 ImageNet 标准化
            （mean=[0.485,0.456,0.406]，std=[0.229,0.224,0.225]），
            与训练/评估阶段使用完全一致的预处理代码。
          </li>
          <li>
            使用 ImageNet 预训练的 ResNet50 进行迁移学习，输出两个类别
            （benign=0, malignant=1）的 softmax 概率，取概率较大者为预测结果，
            其概率值作为模型置信度。
          </li>
          <li>
            检测结果与图片哈希、模型版本一起写入个人历史；图片经 Fernet
            对称加密后落盘，只有本人登录并通过授权校验后才能解密查看。
          </li>
        </ol>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">模型与系统状态</h2>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
          <div className="rounded-xl bg-slate-50 p-4">
            <dt className="text-slate-500">模型版本</dt>
            <dd className="mt-0.5 break-all font-medium text-slate-800">
              {model?.model_version ?? '获取中…'}
            </dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-4">
            <dt className="text-slate-500">网络结构</dt>
            <dd className="mt-0.5 font-medium text-slate-800">
              {model ? `${model.architecture} (${model.input_size}×${model.input_size})` : '获取中…'}
            </dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-4">
            <dt className="text-slate-500">训练时间</dt>
            <dd className="mt-0.5 font-medium text-slate-800">
              {model?.trained_at ? formatDateTime(model.trained_at) : '—'}
            </dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-4">
            <dt className="text-slate-500">服务健康</dt>
            <dd className="mt-0.5 font-medium text-slate-800">
              {health
                ? `${health.status === 'ok' ? '正常' : '降级'} · 数据库${health.database ? '✓' : '✕'} · 模型${health.model ? '✓' : '✕'}`
                : '获取中…'}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-slate-500">
          概率校准状态：{model?.calibration ?? '未知'}
          （未进行 temperature scaling，因此置信度不能解释为临床患病概率）
        </p>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">隐私与数据使用</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-700">
          <li>上传的图片仅用于本次检测与个人历史记录，不会用于其他用途。</li>
          <li>密码使用 Argon2id 哈希存储，会话令牌只保存哈希值，系统不保存明文密码。</li>
          <li>图片以 Fernet 加密形式存储在服务端，密钥仅通过环境变量注入。</li>
          <li>每个用户只能访问自己的检测记录；越权访问会被拒绝并返回 404。</li>
          <li>删除记录或删除账号时，对应的加密图片会一并从磁盘清除。</li>
        </ul>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">技术栈</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-700">
          PyTorch · torchvision ResNet50 · FastAPI · SQLAlchemy · SQLite ·
          React 18 · TypeScript · TailwindCSS · Vitest · Playwright · Docker Compose
        </p>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">关于 AI 辅助开发</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          本项目的开发过程把 AI Coding Agent 纳入了工程流程：由人定义目标、非目标与验收标准，
          把架构约束、安全要求、并发与失败处理、测试要求整理成结构化提示词交给 Agent 执行，
          Agent 的输出再经过代码审查、自动化测试与真实运行验证才被接受。
          详细流程与边界见仓库文档 <code>docs/engineering/AI_ASSISTED_DEVELOPMENT.md</code>。
        </p>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">已知局限</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-700">
          <li>
            训练数据规模有限（1840 张），且没有 patient_id / lesion_id，
            划分只能是图像级分组划分，内部指标偏乐观。
          </li>
          <li>独立外部测试准确率 78.54%、恶性召回 65.49%，泛化能力仍不足。</li>
          <li>未做概率校准，置信度不能当作患病概率解读。</li>
          <li>SQLite 单实例部署，未做多实例与高并发验证。</li>
          <li>未通过任何医疗器械认证，也没有临床验证数据。</li>
        </ul>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to="/detect" className="btn-primary">
            开始检测
          </Link>
          <Link to="/evaluation" className="btn-secondary">
            查看模型评测
          </Link>
          <Link to="/" className="btn-secondary">
            返回首页
          </Link>
        </div>
      </section>
    </div>
  );
}
