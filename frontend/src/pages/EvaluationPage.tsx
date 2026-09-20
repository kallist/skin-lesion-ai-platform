import { Link } from 'react-router-dom';
import Disclaimer from '../components/Disclaimer';
import {
  EXTERNAL_CLASS_BALANCE,
  EXTERNAL_OVERLAP,
  EXTERNAL_TEST,
  INTERNAL_TEST,
  MODEL_INFO,
  pointDelta,
  type EvaluationMetrics,
} from '../data/evaluation';
import { formatPercent } from '../utils/format';

type MetricKey = 'accuracy' | 'recall' | 'specificity' | 'precision' | 'f1';

const METRIC_ROWS: { key: MetricKey; label: string }[] = [
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'recall', label: 'Recall / Sensitivity（恶性）' },
  { key: 'specificity', label: 'Specificity' },
  { key: 'precision', label: 'Precision（恶性）' },
  { key: 'f1', label: 'F1' },
];

function ConfusionTable({ metrics, label }: { metrics: EvaluationMetrics; label: string }) {
  const { tp, tn, fp, fn } = metrics.confusion;
  return (
    <table className="mt-3 w-full border-collapse text-center text-sm">
      <caption className="sr-only">{label}混淆矩阵</caption>
      <thead>
        <tr>
          <th scope="col" className="p-2 text-xs font-medium text-slate-500">
            {label}（n={metrics.n}）
          </th>
          <th scope="col" className="p-2 text-xs font-medium text-slate-500">
            参考标签 benign
          </th>
          <th scope="col" className="p-2 text-xs font-medium text-slate-500">
            参考标签 malignant
          </th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <th scope="row" className="p-2 text-xs font-medium text-slate-600">
            模型 benign
          </th>
          <td className="rounded bg-slate-50 p-2 font-semibold text-slate-800">TN {tn}</td>
          <td className="p-2 font-semibold text-risk-high">FN {fn}</td>
        </tr>
        <tr>
          <th scope="row" className="p-2 text-xs font-medium text-slate-600">
            模型 malignant
          </th>
          <td className="p-2 font-semibold text-slate-700">FP {fp}</td>
          <td className="rounded bg-slate-50 p-2 font-semibold text-slate-800">TP {tp}</td>
        </tr>
      </tbody>
    </table>
  );
}

function StatCard({
  title,
  subtitle,
  metrics,
  accent,
}: {
  title: string;
  subtitle: string;
  metrics: EvaluationMetrics;
  accent: string;
}) {
  return (
    <article className="card p-5">
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
      <p className={`mt-3 text-3xl font-bold ${accent}`}>{formatPercent(metrics.accuracy, 2)}</p>
      <p className="text-xs text-slate-500">Accuracy · n = {metrics.n}</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
        <div className="rounded-lg bg-slate-50 p-2">
          <dt>Recall（恶性）</dt>
          <dd className="font-semibold text-slate-800">{formatPercent(metrics.recall, 2)}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <dt>Specificity</dt>
          <dd className="font-semibold text-slate-800">{formatPercent(metrics.specificity, 2)}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <dt>ROC-AUC</dt>
          <dd className="font-semibold text-slate-800">{metrics.rocAuc.toFixed(4)}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <dt>PR-AUC</dt>
          <dd className="font-semibold text-slate-800">{metrics.prAuc.toFixed(4)}</dd>
        </div>
      </dl>
    </article>
  );
}

export default function EvaluationPage() {
  const accuracyDrop = pointDelta(INTERNAL_TEST.accuracy, EXTERNAL_TEST.accuracy);
  const recallDrop = pointDelta(INTERNAL_TEST.recall, EXTERNAL_TEST.recall);
  const specificityDrop = pointDelta(INTERNAL_TEST.specificity, EXTERNAL_TEST.specificity);

  return (
    <div className="space-y-6" data-testid="evaluation-page">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">模型评测</h1>
        <p className="mt-1 text-sm text-slate-600">
          冻结模型 <code>{MODEL_INFO.modelVersion}</code>（{MODEL_INFO.architecture}，
          输入 {MODEL_INFO.inputSize}×{MODEL_INFO.inputSize}）在两个数据集上的实测结果。
          指标直接来自评测脚本产出的 artifact，页面只做只读展示，不会重新运行推理。
        </p>
      </header>

      <Disclaimer />

      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard
          title="内部测试集"
          subtitle="训练所用数据集内的留出划分，评估一次，未参与调参"
          metrics={INTERNAL_TEST}
          accent="text-brand-700"
        />
        <StatCard
          title="独立外部测试集"
          subtitle="外部提供、与本项目训练数据独立的一批图像，冻结模型一次性评测"
          metrics={EXTERNAL_TEST}
          accent="text-slate-900"
        />
      </div>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">指标对比</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                <th scope="col" className="py-2 pr-3">指标</th>
                <th scope="col" className="py-2 pr-3 text-right">内部测试</th>
                <th scope="col" className="py-2 pr-3 text-right">独立外部测试</th>
                <th scope="col" className="py-2 text-right">差值</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-slate-100">
                <th scope="row" className="py-2 pr-3 text-left font-medium text-slate-700">样本数</th>
                <td className="py-2 pr-3 text-right text-slate-700">{INTERNAL_TEST.n}</td>
                <td className="py-2 pr-3 text-right text-slate-700">
                  {EXTERNAL_TEST.n}
                  <span className="ml-1 text-xs text-slate-400">
                    ({EXTERNAL_CLASS_BALANCE.benign} / {EXTERNAL_CLASS_BALANCE.malignant})
                  </span>
                </td>
                <td className="py-2 text-right text-slate-400">—</td>
              </tr>
              {METRIC_ROWS.map((row) => {
                const internal = INTERNAL_TEST[row.key];
                const external = EXTERNAL_TEST[row.key];
                const delta = pointDelta(internal, external);
                return (
                  <tr key={row.key} className="border-b border-slate-100">
                    <th scope="row" className="py-2 pr-3 text-left font-medium text-slate-700">
                      {row.label}
                    </th>
                    <td className="py-2 pr-3 text-right text-slate-700">
                      {formatPercent(internal, 2)}
                    </td>
                    <td className="py-2 pr-3 text-right font-semibold text-slate-900">
                      {formatPercent(external, 2)}
                    </td>
                    <td
                      className={`py-2 text-right ${delta < 0 ? 'text-risk-high' : 'text-slate-500'}`}
                    >
                      {delta > 0 ? '+' : ''}
                      {delta.toFixed(2)} pt
                    </td>
                  </tr>
                );
              })}
              <tr className="border-b border-slate-100">
                <th scope="row" className="py-2 pr-3 text-left font-medium text-slate-700">ROC-AUC</th>
                <td className="py-2 pr-3 text-right text-slate-700">
                  {INTERNAL_TEST.rocAuc.toFixed(4)}
                </td>
                <td className="py-2 pr-3 text-right font-semibold text-slate-900">
                  {EXTERNAL_TEST.rocAuc.toFixed(4)}
                </td>
                <td className="py-2 text-right text-risk-high">
                  {(EXTERNAL_TEST.rocAuc - INTERNAL_TEST.rocAuc).toFixed(4)}
                </td>
              </tr>
              <tr>
                <th scope="row" className="py-2 pr-3 text-left font-medium text-slate-700">PR-AUC</th>
                <td className="py-2 pr-3 text-right text-slate-700">
                  {INTERNAL_TEST.prAuc.toFixed(4)}
                </td>
                <td className="py-2 pr-3 text-right font-semibold text-slate-900">
                  {EXTERNAL_TEST.prAuc.toFixed(4)}
                </td>
                <td className="py-2 text-right text-risk-high">
                  {(EXTERNAL_TEST.prAuc - INTERNAL_TEST.prAuc).toFixed(4)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          训练阶段设定的准确率目标为 ≥ {formatPercent(MODEL_INFO.reportedAccuracyTarget, 0)}：
          内部测试集达标（{formatPercent(INTERNAL_TEST.accuracy, 2)}），
          独立外部测试集<strong>未达标</strong>（{formatPercent(EXTERNAL_TEST.accuracy, 2)}）。
        </p>
      </section>

      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h2 className="text-base font-semibold text-amber-900">外部测试暴露的问题</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-amber-900">
          <li>
            外部测试并未达到训练阶段设定的准确率目标，说明当前模型仍存在泛化限制。
          </li>
          <li>
            差距集中在<strong>恶性样本漏检</strong>：恶性召回从{' '}
            {formatPercent(INTERNAL_TEST.recall, 2)} 降到 {formatPercent(EXTERNAL_TEST.recall, 2)}
            （{recallDrop.toFixed(2)} pt），对应 {EXTERNAL_TEST.confusion.fn} 例恶性样本被判为良性。
          </li>
          <li>
            特异性基本稳定（{formatPercent(INTERNAL_TEST.specificity, 2)} →{' '}
            {formatPercent(EXTERNAL_TEST.specificity, 2)}，{specificityDrop.toFixed(2)} pt），
            整体准确率下降 {accuracyDrop.toFixed(2)} pt，因此问题不是简单的阈值偏移。
          </li>
          <li>
            由于缺乏采集设备、患者来源与病灶级元数据，<strong>无法对下降原因做严格归因</strong>；
            数据分布差异是可能因素之一，但不能断言已证明是 domain shift。
          </li>
          <li>
            项目保留首次冻结模型的真实测试结果，<strong>未针对测试集重新训练或调整最终阈值</strong>；
            阈值扫描仅作分析，未应用到模型。
          </li>
        </ul>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">混淆矩阵</h2>
        <div className="mt-3 grid gap-5 lg:grid-cols-2">
          <div className="rounded-xl bg-slate-50 p-4">
            <h3 className="text-sm font-semibold text-slate-800">内部测试集</h3>
            <ConfusionTable metrics={INTERNAL_TEST} label="内部测试集" />
          </div>
          <div className="rounded-xl bg-slate-50 p-4">
            <h3 className="text-sm font-semibold text-slate-800">独立外部测试集</h3>
            <ConfusionTable metrics={EXTERNAL_TEST} label="独立外部测试集" />
          </div>
        </div>
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <figure>
            <img
              src="/evaluation/internal_confusion_matrix.png"
              alt="内部测试集混淆矩阵图"
              className="w-full rounded-xl border border-slate-200 bg-white"
              loading="lazy"
            />
            <figcaption className="mt-2 text-xs text-slate-500">
              内部测试集混淆矩阵（n={INTERNAL_TEST.n}）
            </figcaption>
          </figure>
          <figure>
            <img
              src="/evaluation/external_confusion_matrix.png"
              alt="独立外部测试集混淆矩阵图"
              className="w-full rounded-xl border border-slate-200 bg-white"
              loading="lazy"
            />
            <figcaption className="mt-2 text-xs text-slate-500">
              独立外部测试集混淆矩阵（n={EXTERNAL_TEST.n}）
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">ROC 与 PR 曲线</h2>
        <div className="mt-3 grid gap-5 lg:grid-cols-2">
          <figure>
            <img
              src="/evaluation/external_roc_curve.png"
              alt="独立外部测试集 ROC 曲线"
              className="w-full rounded-xl border border-slate-200 bg-white"
              loading="lazy"
            />
            <figcaption className="mt-2 text-xs text-slate-500">
              ROC 曲线 · 独立外部测试集（AUC {EXTERNAL_TEST.rocAuc.toFixed(4)}）
            </figcaption>
          </figure>
          <figure>
            <img
              src="/evaluation/external_pr_curve.png"
              alt="独立外部测试集 PR 曲线"
              className="w-full rounded-xl border border-slate-200 bg-white"
              loading="lazy"
            />
            <figcaption className="mt-2 text-xs text-slate-500">
              PR 曲线 · 独立外部测试集（AUC {EXTERNAL_TEST.prAuc.toFixed(4)}）
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">评测可信度</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-700">
          <li>
            外部测试集与训练 / 验证 / 内部测试集的 SHA256 完全重合数：
            train {EXTERNAL_OVERLAP.train} / val {EXTERNAL_OVERLAP.val} / test{' '}
            {EXTERNAL_OVERLAP.test}（无字节级泄漏）。
          </li>
          <li>
            外部评测脚本只加载冻结权重做前向推理，不做任何训练；指标由独立复核脚本从预测结果重新计算并逐项比对。
          </li>
          <li>
            内部划分使用 group-aware 分层划分，重复图与近似重复图不会跨集合；
            但数据集没有 patient_id / lesion_id，内部指标仍属图像级、可能偏乐观。
          </li>
          <li>
            概率校准状态：{MODEL_INFO.calibration}
            —— 模型置信度是 softmax 输出，不能解释为患病概率。
          </li>
        </ul>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-900">局限与说明</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-700">
          本页用于作品展示与工程复盘，展示的是当前已冻结模型的既有指标，
          <strong>不代表新增的模型能力</strong>。在外部测试集上仍有{' '}
          {EXTERNAL_TEST.confusion.fn} 例恶性样本被漏判，因此在任何真实健康场景中，
          模型输出都只能作为参考，不能替代皮肤科医生的面诊与检查。本项目未取得医疗器械认证，
          也没有临床验证数据。
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to="/about" className="btn-secondary">
            关于本平台
          </Link>
          <Link to="/" className="btn-secondary">
            返回首页
          </Link>
        </div>
      </section>
    </div>
  );
}
