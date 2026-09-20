import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import Disclaimer from '../components/Disclaimer';
import HistoryThumbnail from '../components/HistoryThumbnail';
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../components/States';
import type { Detection, DetectionListItem } from '../types';
import { formatDateTime, formatPercent, predictionLabel, predictionLabelEn, predictionSymbol } from '../utils/format';

export default function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [candidates, setCandidates] = useState<DetectionListItem[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [details, setDetails] = useState<Detection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCandidates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await api.listDetections({ page: 1, pageSize: 100 });
      setCandidates(page.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '加载历史记录失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates]);

  // Initialise selection from ?ids=1,2
  useEffect(() => {
    const raw = searchParams.get('ids');
    if (!raw) return;
    const ids = raw
      .split(',')
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isFinite(value))
      .slice(0, 2);
    if (ids.length) setSelected(ids);
  }, [searchParams]);

  useEffect(() => {
    if (selected.length === 0) {
      setDetails([]);
      return;
    }
    let cancelled = false;
    Promise.all(selected.map((id) => api.getDetection(id)))
      .then((results) => {
        if (!cancelled) setDetails(results);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : '加载对比数据失败');
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const toggle = (id: number) => {
    setSelected((current) => {
      const next = current.includes(id)
        ? current.filter((value) => value !== id)
        : [...current, id].slice(-2);
      setSearchParams(next.length ? { ids: next.join(',') } : {}, { replace: true });
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">历史记录对比</h1>
        <p className="mt-1 text-sm text-slate-600">
          选择两条历史记录，并排比较图片、预测结果、置信度与检测时间。
        </p>
      </header>

      <Disclaimer variant="compact" />

      {loading && <LoadingPanel label="正在加载历史记录…" rows={2} />}
      {!loading && error && <ErrorPanel message={error} onRetry={loadCandidates} />}

      {!loading && !error && candidates.length === 0 && (
        <EmptyPanel
          title="还没有可对比的记录"
          description="至少需要两条检测记录才能进行对比。"
          action={
            <Link to="/detect" className="btn-primary">
              去检测
            </Link>
          }
        />
      )}

      {!loading && !error && candidates.length > 0 && (
        <>
          <section className="card p-5" aria-labelledby="select-heading">
            <h2 id="select-heading" className="text-base font-semibold text-slate-900">
              选择两条记录（最多两条）
            </h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {candidates.map((item) => {
                const checked = selected.includes(item.id);
                return (
                  <label
                    key={item.id}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 text-sm transition-colors ${
                      checked ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                      checked={checked}
                      onChange={() => toggle(item.id)}
                      data-testid={`compare-select-${item.id}`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-slate-800">
                        #{item.id} · {item.original_filename}
                      </span>
                      <span className="block text-xs text-slate-500">
                        {predictionLabel(item.prediction)} · {formatPercent(item.confidence, 1)} ·{' '}
                        {formatDateTime(item.created_at)}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </section>

          {details.length > 0 && (
            <section aria-labelledby="compare-heading" className="space-y-4">
              <h2 id="compare-heading" className="text-lg font-bold text-slate-900">
                对比结果
              </h2>
              <div className="grid gap-4 md:grid-cols-2">
                {details.map((detail) => (
                  <article key={detail.id} className="card p-4" data-testid={`compare-panel-${detail.id}`}>
                    <HistoryThumbnail
                      detectionId={detail.id}
                      alt={`记录 #${detail.id} 的图片`}
                      className="h-48 w-full"
                    />
                    <h3 className="mt-3 text-sm font-semibold text-slate-900">
                      记录 #{detail.id}
                    </h3>
                    <dl className="mt-2 space-y-1.5 text-sm">
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-500">预测</dt>
                        <dd
                          className={`font-semibold ${
                            detail.prediction === 'malignant' ? 'text-risk-high' : 'text-risk-low'
                          }`}
                        >
                          <span aria-hidden="true">{predictionSymbol(detail.prediction)} </span>
                          {predictionLabel(detail.prediction)} ({predictionLabelEn(detail.prediction)})
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-500">置信度</dt>
                        <dd className="font-medium text-slate-800">{formatPercent(detail.confidence, 1)}</dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-500">良性概率</dt>
                        <dd className="text-slate-800">{formatPercent(detail.probabilities.benign, 1)}</dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-500">恶性概率</dt>
                        <dd className="text-slate-800">{formatPercent(detail.probabilities.malignant, 1)}</dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-500">检测时间</dt>
                        <dd className="text-slate-800">{formatDateTime(detail.created_at)}</dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-slate-500">模型版本</dt>
                        <dd className="break-all text-right text-slate-800">{detail.model_version}</dd>
                      </div>
                    </dl>
                    <Link to={`/history/${detail.id}`} className="btn-secondary mt-4 w-full">
                      查看详情
                    </Link>
                  </article>
                ))}
              </div>
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                两次检测的差异可能来自拍摄角度、光线或皮损本身的变化，
                结果对比仅供观察趋势，不能作为疗效判断依据。
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
