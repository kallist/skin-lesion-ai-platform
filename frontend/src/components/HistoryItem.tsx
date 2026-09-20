import { Link } from 'react-router-dom';
import HistoryThumbnail from './HistoryThumbnail';
import type { DetectionListItem } from '../types';
import {
  formatDateTime,
  formatPercent,
  predictionLabel,
  predictionLabelEn,
  predictionSymbol,
} from '../utils/format';

/** One history row: card layout on mobile, table-like grid on desktop. */
export default function HistoryItem({
  item,
  selected,
  onToggleSelect,
}: {
  item: DetectionListItem;
  selected?: boolean;
  onToggleSelect?: (id: number) => void;
}) {
  const malignant = item.prediction === 'malignant';
  return (
    <article
      className="card flex flex-col gap-4 p-4 sm:flex-row sm:items-center"
      data-testid="history-item"
      data-detection-id={item.id}
    >
      {onToggleSelect && (
        <div className="flex items-center">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            checked={Boolean(selected)}
            onChange={() => onToggleSelect(item.id)}
            aria-label={`选择记录 #${item.id} 用于对比`}
            data-testid={`select-detection-${item.id}`}
          />
        </div>
      )}

      <HistoryThumbnail
        detectionId={item.id}
        alt={`检测记录 #${item.id} 的皮肤图片缩略图`}
        className="h-20 w-20 shrink-0"
      />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`badge ${
              malignant ? 'bg-risk-highBg text-risk-high' : 'bg-risk-lowBg text-risk-low'
            }`}
          >
            <span aria-hidden="true">{predictionSymbol(item.prediction)}</span>
            {predictionLabel(item.prediction)}
          </span>
          <span className="text-xs text-slate-500">
            {predictionLabelEn(item.prediction)} · {formatPercent(item.confidence, 1)}
          </span>
        </div>
        <p className="mt-1.5 truncate text-sm font-medium text-slate-800" title={item.original_filename}>
          {item.original_filename}
        </p>
        <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
          <div className="flex gap-1">
            <dt>时间</dt>
            <dd className="text-slate-700">{formatDateTime(item.created_at)}</dd>
          </div>
          <div className="flex gap-1">
            <dt>模型</dt>
            <dd className="text-slate-700">{item.model_version}</dd>
          </div>
          <div className="flex gap-1">
            <dt>良性</dt>
            <dd className="text-slate-700">{formatPercent(item.probabilities.benign, 1)}</dd>
          </div>
          <div className="flex gap-1">
            <dt>恶性</dt>
            <dd className="text-slate-700">{formatPercent(item.probabilities.malignant, 1)}</dd>
          </div>
        </dl>
      </div>

      <div className="flex shrink-0 gap-2">
        <Link to={`/history/${item.id}`} className="btn-secondary">
          查看详情
        </Link>
      </div>
    </article>
  );
}
