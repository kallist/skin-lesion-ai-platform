import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import Disclaimer from '../components/Disclaimer';
import ImageUploader from '../components/ImageUploader';
import ResultCard from '../components/ResultCard';
import { ErrorPanel } from '../components/States';
import { useToasts } from '../hooks/useToasts';
import type { Detection } from '../types';

type Phase = 'idle' | 'uploading' | 'processing' | 'success' | 'error';

function newIdempotencyKey(): string {
  const random = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(random, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export default function DetectPage() {
  const { push } = useToasts();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [result, setResult] = useState<Detection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveHistory, setSaveHistory] = useState(true);
  const idempotencyKey = useRef<string | null>(null);

  // Object-URL lifecycle: always revoke the previous preview.
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const busy = phase === 'uploading' || phase === 'processing';

  const onSelect = (selected: File) => {
    setFile(selected);
    setResult(null);
    setError(null);
    setPhase('idle');
    idempotencyKey.current = newIdempotencyKey();
  };

  const onClear = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setPhase('idle');
    idempotencyKey.current = null;
  };

  const onDetect = async () => {
    if (!file || busy) return;
    setError(null);
    setResult(null);
    setPhase('uploading');
    if (!idempotencyKey.current) idempotencyKey.current = newIdempotencyKey();

    // switch the label as soon as the request leaves the browser
    const processingTimer = window.setTimeout(() => setPhase('processing'), 350);
    try {
      const detection = await api.detect(file, {
        saveHistory,
        idempotencyKey: idempotencyKey.current,
      });
      setResult(detection);
      setPhase('success');
      push('检测完成', 'success');
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : '检测失败，请稍后重试或更换一张图片';
      setError(message);
      setPhase('error');
    } finally {
      window.clearTimeout(processingTimer);
    }
  };

  const buttonLabel = useMemo(() => {
    if (phase === 'uploading') return '上传中…';
    if (phase === 'processing') return '模型推理中…';
    return '开始检测';
  }, [phase]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">皮肤病变检测</h1>
          <p className="mt-1 text-sm text-slate-600">
            上传一张清晰的皮肤病变照片，系统将给出良性 / 恶性倾向判断。
          </p>
        </div>
        <Link to="/history" className="btn-secondary">
          查看历史记录
        </Link>
      </header>

      <Disclaimer />

      <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
        <section className="card p-5" aria-labelledby="upload-heading">
          <h2 id="upload-heading" className="text-base font-semibold text-slate-900">
            1. 上传图片
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            尽量使用光线均匀、对焦清晰、包含病变区域的照片。
          </p>

          <div className="mt-4">
            <ImageUploader
              file={file}
              previewUrl={previewUrl}
              onSelect={onSelect}
              onClear={onClear}
              disabled={busy}
            />
          </div>

          <div className="mt-4 flex items-center gap-2">
            <input
              id="save-history"
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
              checked={saveHistory}
              onChange={(event) => setSaveHistory(event.target.checked)}
              disabled={busy}
              data-testid="save-history-checkbox"
            />
            <label htmlFor="save-history" className="text-sm text-slate-700">
              保存到我的检测历史（图片将加密存储）
            </label>
          </div>

          <button
            type="button"
            className="btn-primary mt-5 w-full"
            onClick={onDetect}
            disabled={!file || busy}
            data-testid="detect-button"
            aria-busy={busy}
          >
            {busy && (
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
              />
            )}
            {buttonLabel}
          </button>

          {phase === 'processing' && (
            <p role="status" aria-live="polite" className="mt-3 text-sm text-slate-600">
              正在对图像做 224×224 归一化预处理并运行 ResNet 推理，请稍候…
            </p>
          )}
        </section>

        <section aria-labelledby="result-region-heading" className="space-y-4">
          <h2 id="result-region-heading" className="sr-only">
            检测结果区域
          </h2>

          {phase === 'idle' && !result && (
            <div className="card grid place-items-center p-10 text-center text-sm text-slate-500">
              <span aria-hidden="true" className="text-4xl">
                🔬
              </span>
              <p className="mt-3">上传图片并点击「开始检测」后，结果会显示在这里。</p>
            </div>
          )}

          {busy && (
            <div className="card animate-pulse p-5" data-testid="result-skeleton">
              <div className="h-4 w-1/4 rounded bg-slate-200" />
              <div className="mt-4 h-8 w-1/2 rounded bg-slate-200" />
              <div className="mt-5 space-y-3">
                <div className="h-2.5 w-full rounded bg-slate-100" />
                <div className="h-2.5 w-full rounded bg-slate-100" />
              </div>
              <p className="sr-only">正在检测</p>
            </div>
          )}

          {phase === 'error' && error && (
            <ErrorPanel message={error} onRetry={onDetect} />
          )}

          {result && <ResultCard detection={result} />}

          {result && (
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary" onClick={onClear}>
                检测另一张图片
              </button>
              <Link to={`/history/${result.id}`} className="btn-secondary">
                查看该记录详情
              </Link>
              <Link to="/history" className="btn-secondary">
                全部历史记录
              </Link>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
