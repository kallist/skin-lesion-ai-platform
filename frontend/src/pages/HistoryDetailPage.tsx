import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import ConfirmDialog from '../components/ConfirmDialog';
import Disclaimer from '../components/Disclaimer';
import ResultCard from '../components/ResultCard';
import { ErrorPanel, LoadingPanel } from '../components/States';
import { useToasts } from '../hooks/useToasts';
import type { Detection } from '../types';
import { formatDateTime, formatPercent, predictionLabel } from '../utils/format';

export default function HistoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const detectionId = Number(id);
  const navigate = useNavigate();
  const { push } = useToasts();
  const [detection, setDetection] = useState<Detection | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(detectionId)) {
      setError('记录编号无效');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    // release the previous object URL before replacing it (avoid blob leaks)
    setImageUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
    try {
      const result = await api.getDetection(detectionId);
      setDetection(result);
      if (result.image_available) {
        try {
          const blob = await api.fetchDetectionImage(detectionId);
          setImageUrl(URL.createObjectURL(blob));
        } catch (err) {
          setImageError(err instanceof ApiError ? err.message : '图片不可用');
        }
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '加载记录失败');
    } finally {
      setLoading(false);
    }
  }, [detectionId]);

  useEffect(() => {
    void load();
    return () => {
      setImageUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return null;
      });
    };
  }, [load]);

  const onDelete = async () => {
    setDeleting(true);
    try {
      await api.deleteDetection(detectionId);
      push('检测记录已删除', 'success');
      navigate('/history', { replace: true });
    } catch (err) {
      push(err instanceof ApiError ? err.message : '删除失败', 'error');
    } finally {
      setDeleting(false);
      setConfirmOpen(false);
    }
  };

  if (loading) return <LoadingPanel label="正在加载检测记录…" rows={2} />;
  if (error) return <ErrorPanel message={error} onRetry={load} />;
  if (!detection) return <ErrorPanel message="记录不存在" />;

  return (
    <div className="space-y-6">
      <nav aria-label="面包屑" className="text-sm text-slate-500">
        <Link to="/history" className="hover:underline">
          检测历史
        </Link>
        <span className="mx-1">/</span>
        <span className="text-slate-700">记录 #{detection.id}</span>
      </nav>

      <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
        <section className="card p-5" aria-labelledby="image-heading">
          <h2 id="image-heading" className="text-base font-semibold text-slate-900">
            当时的检测图片
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            文件：{detection.original_filename} · {formatDateTime(detection.created_at)}
          </p>
          <div className="mt-4">
            {imageUrl ? (
              <img
                src={imageUrl}
                alt={`检测记录 #${detection.id} 的皮肤病变图片`}
                className="mx-auto max-h-[420px] w-auto max-w-full rounded-xl border border-slate-200 object-contain"
                data-testid="history-image"
              />
            ) : (
              <div
                className="grid place-items-center rounded-xl border border-dashed border-slate-300 bg-slate-50 p-10 text-sm text-slate-500"
                data-testid="history-image-missing"
              >
                {imageError ?? (detection.image_available ? '图片加载中…' : '该记录没有保存图片')}
              </div>
            )}
          </div>
        </section>

        <div className="space-y-4">
          <ResultCard detection={detection} />

          <div className="card p-5">
            <h2 className="text-sm font-semibold text-slate-900">记录信息</h2>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-slate-500">预测结果</dt>
                <dd className="font-medium text-slate-800">{predictionLabel(detection.prediction)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">置信度</dt>
                <dd className="font-medium text-slate-800">{formatPercent(detection.confidence, 1)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">模型版本</dt>
                <dd className="font-medium text-slate-800">{detection.model_version}</dd>
              </div>
              <div>
                <dt className="text-slate-500">检测时间</dt>
                <dd className="font-medium text-slate-800">{formatDateTime(detection.created_at)}</dd>
              </div>
            </dl>

            <div className="mt-5 flex flex-wrap gap-2">
              <Link to={`/compare?ids=${detection.id}`} className="btn-secondary">
                加入对比
              </Link>
              <button
                type="button"
                className="btn-danger"
                onClick={() => setConfirmOpen(true)}
                data-testid="delete-detection-button"
              >
                删除该记录
              </button>
            </div>
          </div>
        </div>
      </div>

      <Disclaimer variant="compact" />

      <ConfirmDialog
        open={confirmOpen}
        title="删除这条检测记录？"
        description="删除后该记录及其加密存储的图片将无法恢复。"
        confirmLabel="删除"
        danger
        busy={deleting}
        onConfirm={onDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
