import { useCallback, useEffect, useRef, useState } from 'react';
import { ACCEPTED_EXTENSIONS, formatBytes, validateImageFile } from '../utils/format';

export interface ImageUploaderProps {
  file: File | null;
  previewUrl: string | null;
  onSelect: (file: File) => void;
  onClear: () => void;
  disabled?: boolean;
  error?: string | null;
}

/**
 * Drag & drop / click uploader with preview, replace and remove.
 * Keyboard accessible: the drop zone is a real button.
 */
export default function ImageUploader({
  file,
  previewUrl,
  onSelect,
  onClear,
  disabled = false,
  error = null,
}: ImageUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setLocalError(null);
  }, [file]);

  const handleFiles = useCallback(
    (candidates: FileList | null) => {
      if (!candidates || candidates.length === 0) return;
      const candidate = candidates[0];
      const result = validateImageFile(candidate);
      if (!result.ok) {
        setLocalError(result.error ?? '文件无效');
        return;
      }
      setLocalError(null);
      onSelect(candidate);
    },
    [onSelect],
  );

  const openPicker = () => {
    if (!disabled) inputRef.current?.click();
  };

  const message = error ?? localError;

  return (
    <div className="space-y-3">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (disabled) return;
          handleFiles(event.dataTransfer.files);
        }}
        className={`rounded-2xl border-2 border-dashed p-4 transition-colors ${
          dragging ? 'border-brand-500 bg-brand-50' : 'border-slate-300 bg-slate-50'
        } ${disabled ? 'opacity-60' : ''}`}
        data-testid="dropzone"
        data-dragging={dragging ? 'true' : 'false'}
      >
        {!file && (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <span aria-hidden="true" className="text-4xl">
              🖼️
            </span>
            <div>
              <p className="text-base font-semibold text-slate-800">
                拖拽图片到此处，或点击选择文件
              </p>
              <p className="mt-1 text-sm text-slate-500">
                支持 JPG / PNG / WEBP / BMP，单张不超过 10 MB
              </p>
            </div>
            <button
              type="button"
              className="btn-primary"
              onClick={openPicker}
              disabled={disabled}
              data-testid="select-file-button"
            >
              选择图片
            </button>
          </div>
        )}

        {file && previewUrl && (
          <div className="flex flex-col gap-4 sm:flex-row">
            <img
              src={previewUrl}
              alt={`待检测图片预览：${file.name}`}
              className="mx-auto max-h-64 w-auto max-w-full rounded-xl border border-slate-200 object-contain sm:mx-0"
              data-testid="preview-image"
            />
            <div className="flex flex-1 flex-col justify-between gap-3">
              <dl className="space-y-1 text-sm">
                <div className="flex gap-2">
                  <dt className="w-16 shrink-0 text-slate-500">文件名</dt>
                  <dd className="break-all font-medium text-slate-800" data-testid="file-name">
                    {file.name}
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dt className="w-16 shrink-0 text-slate-500">大小</dt>
                  <dd className="text-slate-800">{formatBytes(file.size)}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="w-16 shrink-0 text-slate-500">类型</dt>
                  <dd className="text-slate-800">{file.type || '未知'}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={openPicker}
                  disabled={disabled}
                  data-testid="replace-file-button"
                >
                  更换图片
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={onClear}
                  disabled={disabled}
                  data-testid="remove-file-button"
                >
                  移除图片
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS.join(',')}
        className="hidden"
        aria-label="选择皮肤病变图片"
        data-testid="file-input"
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = '';
        }}
      />

      {message && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {message}
        </p>
      )}
    </div>
  );
}
