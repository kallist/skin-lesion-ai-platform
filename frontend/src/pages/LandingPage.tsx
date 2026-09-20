import { Link } from 'react-router-dom';
import Disclaimer from '../components/Disclaimer';
import { useAuth } from '../hooks/useAuth';

/** Tech-stack markers shown under the hero — they double as the project's
 *  engineering one-liner for anyone landing on the app for the first time. */
const stackBadges = ['ResNet50', 'FastAPI', 'React', 'Independent Evaluation'];

const features = [
  {
    icon: '🔬',
    title: 'AI 智能检测',
    body: 'ImageNet 预训练的 ResNet50 两阶段迁移学习模型，输入统一 224×224，输出良性 / 恶性倾向与两类概率。',
  },
  {
    icon: '🖼️',
    title: '上传与预处理',
    body: '拖拽或点选 JPG / PNG / WEBP / BMP，上传前本地预览；服务端真实解码校验，剥离 EXIF 元数据后再推理。',
  },
  {
    icon: '🗂️',
    title: '个人检测档案',
    body: '每次检测的结果、模型置信度、模型版本与时间自动归档到个人账户，只有本人登录并授权后才能查看。',
  },
  {
    icon: '📊',
    title: '历史结果分析',
    body: '按良性 / 恶性倾向筛选，分页浏览历史记录，查看单次检测详情与当时的概率分布。',
  },
  {
    icon: '⚖️',
    title: '结果对比',
    body: '选择任意两次检测并排对比倾向、置信度与概率差异，便于回顾同一部位多次记录的变化。',
  },
  {
    icon: '📤',
    title: '数据导出与隐私管理',
    body: '检测记录一键导出 CSV；随机盐 Argon2id 口令哈希、会话令牌哈希存储、图像 Fernet 加密落盘。',
  },
];

export default function LandingPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-10">
      <section className="card overflow-hidden">
        <div className="grid gap-8 p-6 sm:p-10 lg:grid-cols-2 lg:items-center">
          <div>
            <span className="badge bg-brand-50 text-brand-700">
              AI 辅助分析 · 不构成医学诊断
            </span>
            <h1 className="mt-4 text-3xl font-bold leading-tight text-slate-900 sm:text-4xl">
              皮肤病变智能识别与
              <span className="text-brand-600">辅助分析平台</span>
            </h1>
            <p className="mt-4 text-base leading-relaxed text-slate-600">
              基于深度学习的皮肤病变图像分析：上传一张皮肤病变照片，服务端使用训练完成的
              ResNet50 模型给出良性 / 恶性倾向、两类概率与模型置信度，
              并把每次检测归档到你的个人检测记录中。
            </p>

            <ul className="mt-5 flex flex-wrap gap-2">
              {stackBadges.map((badge) => (
                <li
                  key={badge}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600"
                >
                  {badge}
                </li>
              ))}
            </ul>

            <div className="mt-6 flex flex-wrap gap-3">
              <Link to={user ? '/detect' : '/register'} className="btn-primary">
                {user ? '开始检测' : '免费注册并开始检测'}
              </Link>
              <Link to="/about" className="btn-secondary">
                查看项目说明
              </Link>
              {!user && (
                <Link to="/login" className="btn-secondary">
                  已有账号，去登录
                </Link>
              )}
            </div>

            <p className="mt-4 text-xs leading-relaxed text-slate-500">
              本系统用于 AI 工程实践与皮肤健康辅助分析，结果仅供参考，不能替代专业医生诊断。
              项目为校企联合 AI 应用实习实践项目，由广州泰迪智能科技有限公司相关人员参与项目指导与实践；
              不是该公司的商业产品或生产系统，也没有在任何医疗机构上线使用。
            </p>
          </div>

          <div className="rounded-2xl border border-brand-100 bg-gradient-to-br from-brand-50 to-white p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-brand-700">
              检测流程
            </h2>
            <ol className="mt-4 space-y-4">
              {[
                ['上传图片', '拖拽或点击选择一张皮肤病变照片'],
                ['服务端校验', '真实解码图片、限制体积与像素数、去除 EXIF'],
                ['模型推理', '224×224 归一化后输入 ResNet50 得到两类概率'],
                ['结果解读', '显示倾向、置信度、概率与就医建议，并自动归档'],
              ].map(([title, body], index) => (
                <li key={title} className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-600 text-xs font-bold text-white"
                  >
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{title}</p>
                    <p className="text-sm text-slate-600">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <Disclaimer />

      <section aria-labelledby="features-heading">
        <h2 id="features-heading" className="text-xl font-bold text-slate-900">
          产品功能
        </h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <article key={feature.title} className="card p-5">
              <span aria-hidden="true" className="text-2xl">
                {feature.icon}
              </span>
              <h3 className="mt-3 text-base font-semibold text-slate-900">{feature.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{feature.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="card p-6" aria-labelledby="model-heading">
        <h2 id="model-heading" className="text-lg font-bold text-slate-900">
          模型与系统状态
        </h2>
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['深度学习', 'PyTorch · ResNet50 · 两阶段迁移学习'],
            ['后端服务', 'FastAPI · SQLAlchemy · SQLite'],
            ['前端界面', 'React 18 · TypeScript · TailwindCSS'],
            ['隐私保护', 'Argon2id 口令哈希 · 图像 Fernet 加密落盘'],
          ].map(([term, detail]) => (
            <div key={term} className="rounded-xl bg-slate-50 p-4">
              <dt className="font-semibold text-slate-700">{term}</dt>
              <dd className="mt-1 text-slate-600">{detail}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-xs text-slate-500">
          模型版本、输入尺寸、概率校准状态等实时信息见
          <Link to="/about" className="font-medium text-brand-700 hover:underline">
            关于本平台
          </Link>
          ；内部测试集与独立外部测试集的实测指标、混淆矩阵与曲线见
          <Link to="/evaluation" className="font-medium text-brand-700 hover:underline">
            模型评测
          </Link>
          。
        </p>
      </section>
    </div>
  );
}
