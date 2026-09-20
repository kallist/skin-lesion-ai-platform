/** Formatting helpers shared by the UI. */

export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDateTime(iso: string): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB ?? 10);
export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp'];
export const ACCEPTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp'];

export interface FileValidationResult {
  ok: boolean;
  error?: string;
}

/** Client-side pre-validation (the server validates again, authoritatively). */
export function validateImageFile(file: File, maxMb: number = MAX_UPLOAD_MB): FileValidationResult {
  const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  const typeOk = ACCEPTED_TYPES.includes(file.type);
  const extOk = ACCEPTED_EXTENSIONS.includes(extension);
  if (!typeOk && !extOk) {
    return { ok: false, error: '仅支持 JPG / PNG / WEBP / BMP 格式的图片' };
  }
  if (file.size > maxMb * 1024 * 1024) {
    return { ok: false, error: `图片大小不能超过 ${maxMb} MB（当前 ${formatBytes(file.size)}）` };
  }
  if (file.size === 0) {
    return { ok: false, error: '文件为空，请重新选择' };
  }
  return { ok: true };
}

export function predictionLabel(prediction: 'benign' | 'malignant'): string {
  return prediction === 'malignant' ? '恶性倾向' : '良性倾向';
}

export function predictionLabelEn(prediction: 'benign' | 'malignant'): string {
  return prediction === 'malignant' ? 'Malignant' : 'Benign';
}

/** Non-colour-dependent status text (accessibility requirement). */
export function predictionSymbol(prediction: 'benign' | 'malignant'): string {
  return prediction === 'malignant' ? '⚠' : '✓';
}
