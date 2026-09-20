/** Loading / empty / error panels with consistent a11y semantics. */

export function LoadingPanel({ label = '正在加载…', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite" data-testid="loading-panel">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="card animate-pulse p-4">
          <div className="h-4 w-1/3 rounded bg-slate-200" />
          <div className="mt-3 h-3 w-2/3 rounded bg-slate-100" />
          <div className="mt-2 h-3 w-1/2 rounded bg-slate-100" />
        </div>
      ))}
    </div>
  );
}

export function EmptyPanel({
  title,
  description,
  action,
  icon = '📭',
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: string;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 p-10 text-center" data-testid="empty-panel">
      <span aria-hidden="true" className="text-4xl">
        {icon}
      </span>
      <div>
        <h3 className="text-base font-semibold text-slate-800">{title}</h3>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="card border-red-200 bg-red-50 p-5 text-sm text-red-800"
      data-testid="error-panel"
    >
      <p className="font-semibold">出错了</p>
      <p className="mt-1">{message}</p>
      {onRetry && (
        <button type="button" className="btn-secondary mt-3" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  );
}
