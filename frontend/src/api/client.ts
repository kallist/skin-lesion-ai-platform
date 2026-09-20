/**
 * Typed API client.
 *
 * - Always sends cookies (`credentials: 'include'`).
 * - Echoes the CSRF token for state-changing requests (double-submit pattern).
 * - Normalises the backend error contract into `ApiError`.
 */
import type {
  AuthResponse,
  Detection,
  DetectionPage,
  Health,
  ModelInfo,
  User,
} from '../types';

const BASE = import.meta.env.VITE_API_BASE ?? '/api/v1';

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function readCookie(name: string): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : '';
}

export function getCsrfToken(): string {
  return readCookie('csrf_token');
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');

  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = getCsrfToken();
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers, credentials: 'include' });
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '网络连接失败，请检查后端服务是否已启动');
  }

  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    if (!response.ok) {
      throw new ApiError(response.status, 'UNEXPECTED_RESPONSE', '服务器返回了非预期响应');
    }
    return (await response.text()) as unknown as T;
  }

  const body = await response.json();
  if (!response.ok) {
    const error = body?.error ?? {};
    throw new ApiError(
      response.status,
      error.code ?? 'UNKNOWN_ERROR',
      error.message ?? '请求失败，请稍后重试',
      error.details,
    );
  }
  return body as T;
}

export const api = {
  // ---------- auth ----------
  register(payload: {
    email: string;
    username: string;
    password: string;
    full_name?: string;
  }): Promise<AuthResponse> {
    return request('/auth/register', { method: 'POST', body: JSON.stringify(payload) });
  },

  login(payload: { identifier: string; password: string }): Promise<AuthResponse> {
    return request('/auth/login', { method: 'POST', body: JSON.stringify(payload) });
  },

  logout(): Promise<{ message: string }> {
    return request('/auth/logout', { method: 'POST' });
  },

  session(): Promise<AuthResponse> {
    return request('/auth/session');
  },

  // ---------- users ----------
  me(): Promise<User> {
    return request('/users/me');
  },

  updateProfile(payload: { full_name?: string | null; username?: string }): Promise<User> {
    return request('/users/me', { method: 'PATCH', body: JSON.stringify(payload) });
  },

  deleteAccount(): Promise<{ message: string }> {
    return request('/users/me', { method: 'DELETE' });
  },

  // ---------- detection ----------
  async detect(
    file: File,
    options: { saveHistory?: boolean; idempotencyKey?: string; signal?: AbortSignal } = {},
  ): Promise<Detection> {
    const form = new FormData();
    form.append('image', file, file.name);
    form.append('save_history', String(options.saveHistory ?? true));
    const headers: Record<string, string> = {};
    if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
    return request<Detection>('/detections', {
      method: 'POST',
      body: form,
      headers,
      signal: options.signal,
    });
  },

  listDetections(params: { page?: number; pageSize?: number; prediction?: string } = {}) {
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.pageSize) query.set('page_size', String(params.pageSize));
    if (params.prediction) query.set('prediction', params.prediction);
    const suffix = query.toString() ? `?${query}` : '';
    return request<DetectionPage>(`/detections${suffix}`);
  },

  getDetection(id: number): Promise<Detection> {
    return request(`/detections/${id}`);
  },

  detectionImageUrl(id: number): string {
    return `${BASE}/detections/${id}/image`;
  },

  async fetchDetectionImage(id: number, signal?: AbortSignal): Promise<Blob> {
    const response = await fetch(`${BASE}/detections/${id}/image`, {
      credentials: 'include',
      signal,
    });
    if (!response.ok) {
      throw new ApiError(response.status, 'IMAGE_UNAVAILABLE', '历史图片不可用或已被删除');
    }
    return response.blob();
  },

  deleteDetection(id: number): Promise<{ message: string }> {
    return request(`/detections/${id}`, { method: 'DELETE' });
  },

  async exportCsv(): Promise<Blob> {
    const response = await fetch(`${BASE}/detections/export`, { credentials: 'include' });
    if (!response.ok) {
      throw new ApiError(response.status, 'EXPORT_FAILED', '导出失败，请稍后重试');
    }
    return response.blob();
  },

  // ---------- system ----------
  health(): Promise<Health> {
    return request('/health');
  },

  modelInfo(): Promise<ModelInfo> {
    return request('/model/info');
  },
};
