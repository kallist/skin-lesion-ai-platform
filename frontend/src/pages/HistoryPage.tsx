import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import HistoryItem from '../components/HistoryItem';
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../components/States';
import Disclaimer from '../components/Disclaimer';
import { useToasts } from '../hooks/useToasts';
import type { DetectionPage } from '../types';

const PAGE_SIZE = 10;

export default function HistoryPage() {
  const { push } = useToasts();
  const navigate = useNavigate();
  const [data, setData] = useState<DetectionPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [prediction, setPrediction] = useState<'' | 'benign' | 'malignant'>('');
  const [selected, setSelected] = useState<number[]>([]);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.listDetections({
        page,
        pageSize: PAGE_SIZE,
        prediction: prediction || undefined,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '加载历史记录失败');
    } finally {
      setLoading(false);
    }
  }, [page, prediction]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleSelect = (id: number) => {
    setSelected((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= 2) return [current[1], id]; // keep at most two
      return [...current, id];
    });
  };

  const onExport = async () => {
    setExporting(true);
    try {
      const blob = await api.exportCsv();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `detection_history_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      push('导出成功', 'success');
    } catch (err) {
      push(err instanceof ApiError ? err.message : '导出失败', 'error');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">检测历史</h1>
          <p className="mt-1 text-sm text-slate-600">
            这里只显示你自己的检测记录，图片经加密存储、仅在授权后解密展示。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/detect" className="btn-primary">
            新建检测
          </Link>
          <button
            type="button"
            className="btn-secondary"
            onClick={onExport}
            disabled={exporting || !data?.total}
            data-testid="export-csv-button"
          >
            {exporting ? '导出中…' : '导出 CSV'}
          </button>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium text-slate-700" htmlFor="filter-prediction">
          筛选
        </label>
        <select
          id="filter-prediction"
          className="input w-auto"
          value={prediction}
          onChange={(event) => {
            setPrediction(event.target.value as typeof prediction);
            setPage(1);
          }}
          data-testid="filter-prediction"
        >
          <option value="">全部结果</option>
          <option value="benign">仅良性倾向</option>
          <option value="malignant">仅恶性倾向</option>
        </select>

        {selected.length > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-600">已选择 {selected.length} 条</span>
            <button
              type="button"
              className="btn-secondary"
              disabled={selected.length !== 2}
              onClick={() => navigate(`/compare?ids=${selected.join(',')}`)}
              data-testid="compare-selected-button"
            >
              对比这两条
            </button>
            <button type="button" className="btn-secondary" onClick={() => setSelected([])}>
              清除选择
            </button>
          </div>
        )}
      </div>

      {loading && <LoadingPanel label="正在加载检测历史…" />}
      {!loading && error && <ErrorPanel message={error} onRetry={load} />}

      {!loading && !error && data && data.items.length === 0 && (
        <EmptyPanel
          title="还没有检测记录"
          description="上传第一张皮肤病变图片，检测结果会自动保存到这里。"
          action={
            <Link to="/detect" className="btn-primary">
              开始第一次检测
            </Link>
          }
        />
      )}

      {!loading && !error && data && data.items.length > 0 && (
        <>
          <p className="text-sm text-slate-500" data-testid="history-total">
            共 {data.total} 条记录，第 {data.page} / {data.pages} 页
          </p>
          <div className="space-y-3">
            {data.items.map((item) => (
              <HistoryItem
                key={item.id}
                item={item}
                selected={selected.includes(item.id)}
                onToggleSelect={toggleSelect}
              />
            ))}
          </div>

          <nav className="flex items-center justify-center gap-3" aria-label="分页">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              disabled={data.page <= 1}
            >
              上一页
            </button>
            <span className="text-sm text-slate-600">
              {data.page} / {data.pages}
            </span>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setPage((value) => value + 1)}
              disabled={data.page >= data.pages}
            >
              下一页
            </button>
          </nav>
        </>
      )}

      <Disclaimer variant="compact" />
    </div>
  );
}
