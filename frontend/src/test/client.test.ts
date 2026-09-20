import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { ApiError, api } from '../api/client';

describe('api client', () => {
  beforeEach(() => {
    document.cookie = 'csrf_token=test-csrf-token; path=/';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  it('parses the unified error contract', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ error: { code: 'INVALID_IMAGE', message: '上传文件不是有效图片' } }),
          { status: 400, headers: { 'content-type': 'application/json' } },
        ),
      ),
    );
    await expect(api.login({ identifier: 'a', password: 'b' })).rejects.toMatchObject({
      code: 'INVALID_IMAGE',
      status: 400,
      message: '上传文件不是有效图片',
    });
  });

  it('sends the CSRF header on state-changing requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'ok' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    await api.logout();
    const [, init] = fetchMock.mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get('X-CSRF-Token')).toBe('test-csrf-token');
    expect(init.credentials).toBe('include');
  });

  it('maps network failures to a friendly ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')));
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
    await expect(api.health()).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
  });

  it('sends the image as multipart form data with an idempotency key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 1 }), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const file = new File(['x'], 'a.jpg', { type: 'image/jpeg' });
    await api.detect(file, { idempotencyKey: 'key-123' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/detections');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Headers).get('Idempotency-Key')).toBe('key-123');
  });

  it('builds the detection image URL', () => {
    expect(api.detectionImageUrl(42)).toMatch(/\/detections\/42\/image$/);
  });
});
