import { useEffect, useState } from 'react';
import { api } from '../api/client';

/** Lazily loads a decrypted history thumbnail via the authenticated endpoint. */
export default function HistoryThumbnail({
  detectionId,
  alt,
  className = 'h-16 w-16',
}: {
  detectionId: number;
  alt: string;
  className?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    api
      .fetchDetectionImage(detectionId, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => setFailed(true));
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [detectionId]);

  if (failed) {
    return (
      <div
        className={`${className} grid place-items-center rounded-lg border border-slate-200 bg-slate-100 text-xs text-slate-400`}
        title="图片不可用"
      >
        无图
      </div>
    );
  }

  if (!url) {
    return <div className={`${className} animate-pulse rounded-lg bg-slate-200`} aria-hidden="true" />;
  }

  return (
    <img
      src={url}
      alt={alt}
      loading="lazy"
      className={`${className} rounded-lg border border-slate-200 object-cover`}
    />
  );
}
