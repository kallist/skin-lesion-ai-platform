import type { Detection } from '../types';
import { formatDateTime, formatPercent, predictionLabel, predictionLabelEn, predictionSymbol } from '../utils/format';

const tone = {
  malignant: {
    wrap: 'border-risk-high/30 bg-risk-highBg',
    title: 'text-risk-high',
    bar: 'bg-risk-high',
  },
  benign: {
    wrap: 'border-risk-low/30 bg-risk-lowBg',
    title: 'text-risk-low',
    bar: 'bg-risk-low',
  },
} as const;

/** Result panel: prediction, confidence, both class probabilities, advice. */
export default function ResultCard({ detection }: { detection: Detection }) {
  const style = tone[detection.prediction];
  const label = predictionLabel(detection.prediction);

  return (
    <section
      aria-labelledby="result-heading"
      className={`card animate-fade-in border p-5 ${style.wrap}`}
      data-testid="result-card"
      data-prediction={detection.prediction}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="result-heading" className="text-sm font-semibold uppercase tracking-wide text-slate-600">
            检测结果
          </h2>
          <p className={`mt-1 flex items-center gap-2 text-2xl font-bold ${style.title}`}>
            <span aria-hidden="true">{predictionSymbol(detection.prediction)}</span>
            <span>{label}</span>
            <span className="text-base font-medium text-slate-500">
              ({predictionLabelEn(detection.prediction)})
            </span>
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs font-medium text-slate-500">模型置信度</p>
          <p className="text-2xl font-bold text-slate-900" data-testid="confidence">
            {formatPercent(detection.confidence, 1)}
          </p>
        </div>
      </div>

      <div className="mt-5 space-y-3" data-testid="probability-bars">
        {(['benign', 'malignant'] as const).map((cls) => {
          const value = detection.probabilities[cls];
          const barClass = cls === 'malignant' ? 'bg-risk-high' : 'bg-risk-low';
          return (
            <div key={cls}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="font-medium text-slate-700">
                  {cls === 'benign' ? '良性倾向' : '恶性倾向'}{' '}
                  <span className="text-slate-400">({cls})</span>
                </span>
                <span className="font-semibold text-slate-900">{formatPercent(value, 1)}</span>
              </div>
              <div
                className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200"
                role="progressbar"
                aria-valuenow={Math.round(value * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${cls} 概率`}
              >
                <div className={`h-full rounded-full ${barClass}`} style={{ width: `${value * 100}%` }} />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-5 rounded-xl border border-slate-200 bg-white/70 p-4">
        <h3 className="text-sm font-semibold text-slate-800">健康建议</h3>
        <p className="mt-1 text-sm leading-relaxed text-slate-700" data-testid="advice">
          {detection.advice}
        </p>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs text-slate-600 sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">模型版本</dt>
          <dd className="font-medium text-slate-800" data-testid="model-version">
            {detection.model_version}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">检测时间</dt>
          <dd className="font-medium text-slate-800">{formatDateTime(detection.created_at)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">记录编号</dt>
          <dd className="font-medium text-slate-800">#{detection.id}</dd>
        </div>
      </dl>

      <p
        className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
        data-testid="result-disclaimer"
      >
        {detection.disclaimer} 模型置信度并不等同于真实临床患病概率。
      </p>
    </section>
  );
}
