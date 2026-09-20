/**
 * End-to-end happy path against the real running backend + built frontend.
 *
 * The test creates a unique account, uploads a real JPEG, runs detection,
 * checks the result panel, then walks the history / detail / compare / export
 * / logout flow.
 *
 * Inference backend: by default the suite runs against whatever the API is
 * serving (real model or stub, controlled by MODEL_BACKEND on the server).
 * The `real model smoke test` block below is skipped when MODEL_BACKEND=stub;
 * it asserts the trained checkpoint described in docs/testing/TEST_REPORT.md.
 */
import { expect, test, type Page } from '@playwright/test';
import { createHash, randomUUID } from 'node:crypto';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const API_URL = process.env.E2E_API_URL || 'http://127.0.0.1:8000';

/** Minimal valid 64x64 RGB JPEG (generated at runtime, no fixture download). */
function makeJpeg(): string {
  // A tiny JPEG produced by encoding a solid-colour bitmap via a data URL is
  // not possible in Node without a codec, so we ship a hand-encoded 8x8 JPEG.
  const base64 =
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a' +
    'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy' +
    'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAIAAgDASIA' +
    'AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA' +
    'AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3' +
    'ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm' +
    'p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA' +
    'AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx' +
    'BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK' +
    'U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3' +
    'uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iii' +
    'gD//2Q==';
  const dir = mkdtempSync(path.join(tmpdir(), 'skin-e2e-'));
  const file = path.join(dir, 'lesion.jpg');
  writeFileSync(file, Buffer.from(base64, 'base64'));
  return file;
}

async function registerAndLogin(page: Page, username: string): Promise<void> {
  await page.goto('/register');
  await page.getByTestId('register-email').fill(`${username}@example.com`);
  await page.getByTestId('register-username').fill(username);
  await page.getByTestId('register-password').fill('E2ePassw0rd!');
  await page.getByTestId('register-confirm').fill('E2ePassw0rd!');
  await page.getByTestId('register-submit').click();
  await expect(page).toHaveURL(/\/detect$/);
  await expect(page.getByRole('heading', { name: '皮肤病变检测' })).toBeVisible();
}

/** On narrow viewports the navigation is collapsed behind the "菜单" button. */
async function openNavIfCollapsed(page: Page): Promise<void> {
  const toggle = page.getByRole('button', { name: '菜单' });
  if (await toggle.isVisible().catch(() => false)) {
    await toggle.click();
  }
}

/** Click a top-level navigation link (works on desktop and mobile layouts). */
async function navTo(page: Page, name: string): Promise<void> {
  await openNavIfCollapsed(page);
  await page.getByRole('link', { name, exact: true }).first().click();
}

test.describe('skin lesion detection happy path', () => {
  test('register -> upload -> detect -> history -> detail -> logout', async ({ page }) => {
    const username = `e2e${randomUUID().replace(/-/g, '').slice(0, 10)}`;

    // ---------- landing page ----------
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('皮肤病变智能识别与');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('辅助分析平台');
    await expect(page.getByText('不能替代专业医生诊断').first()).toBeVisible();

    // ---------- register (auto-login) ----------
    await registerAndLogin(page, username);

    // ---------- upload + preview ----------
    const jpeg = makeJpeg();
    await page.getByTestId('file-input').setInputFiles(jpeg);
    await expect(page.getByTestId('preview-image')).toBeVisible();
    await expect(page.getByTestId('file-name')).toContainText('lesion.jpg');

    // ---------- detect ----------
    const detectButton = page.getByTestId('detect-button');
    await expect(detectButton).toBeEnabled();
    await detectButton.click();

    const result = page.getByTestId('result-card');
    await expect(result).toBeVisible({ timeout: 45_000 });
    const prediction = await result.getAttribute('data-prediction');
    expect(['benign', 'malignant']).toContain(prediction);
    await expect(page.getByTestId('confidence')).toContainText('%');
    // the result panel must always carry the medical disclaimer wording
    await expect(page.getByTestId('result-disclaimer')).toContainText('不能替代专业医生诊断');
    await expect(page.getByTestId('result-disclaimer')).toContainText('不等同于真实临床患病概率');
    await expect(page.getByTestId('model-version')).not.toBeEmpty();

    // ---------- history ----------
    await navTo(page, '全部历史记录');
    await expect(page).toHaveURL(/\/history$/);
    const items = page.getByTestId('history-item');
    await expect(items.first()).toBeVisible();
    const count = await items.count();
    expect(count).toBeGreaterThan(0);

    // ---------- detail ----------
    await items.first().getByRole('link', { name: '查看详情' }).click();
    await expect(page).toHaveURL(/\/history\/\d+$/);
    await expect(page.getByTestId('result-card')).toBeVisible();
    await expect(page.getByTestId('history-image')).toBeVisible();

    // ---------- compare (needs two records) ----------
    await page.goto('/detect');
    await page.getByTestId('file-input').setInputFiles(jpeg);
    await page.getByTestId('detect-button').click();
    await expect(page.getByTestId('result-card')).toBeVisible({ timeout: 45_000 });

    await page.goto('/history');
    const boxes = page.locator('[data-testid^="select-detection-"]');
    await expect(boxes.first()).toBeVisible();
    await boxes.nth(0).check();
    await boxes.nth(1).check();
    await page.getByTestId('compare-selected-button').click();
    await expect(page).toHaveURL(/\/compare/);
    await expect(page.locator('[data-testid^="compare-panel-"]')).toHaveCount(2);

    // ---------- CSV export ----------
    await page.goto('/history');
    const downloadPromise = page.waitForEvent('download');
    await page.getByTestId('export-csv-button').click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.csv$/);

    // ---------- profile ----------
    await navTo(page, username);
    await expect(page.getByRole('heading', { name: '个人信息' })).toBeVisible();
    await page.getByTestId('profile-fullname').fill('E2E Tester');
    await page.getByTestId('profile-save').click();
    await expect(page.getByText('个人信息已更新')).toBeVisible();

    // ---------- model evaluation page (static, public) ----------
    await navTo(page, '模型评测');
    await expect(page).toHaveURL(/\/evaluation$/);
    await expect(page.getByTestId('evaluation-page')).toContainText('78.54%');

    // ---------- logout ----------
    await openNavIfCollapsed(page);
    await page.getByRole('button', { name: '退出' }).click();
    await expect(page).toHaveURL(/\/$/);
    await page.goto('/history');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('rejects a non-image upload before any request is sent', async ({ page }) => {
    const username = `e2e${randomUUID().replace(/-/g, '').slice(0, 10)}`;
    await registerAndLogin(page, username);

    const dir = mkdtempSync(path.join(tmpdir(), 'skin-e2e-'));
    const bogus = path.join(dir, 'not-an-image.txt');
    writeFileSync(bogus, 'definitely not an image');

    await page.getByTestId('file-input').setInputFiles(bogus);
    await expect(page.getByRole('alert')).toContainText('仅支持 JPG');
    await expect(page.getByTestId('preview-image')).toHaveCount(0);
  });

  test('protected route redirects anonymous visitors to login', async ({ page }) => {
    await page.goto('/detect');
    await expect(page).toHaveURL(/\/login$/);
  });
});

test.describe('real model smoke test', () => {
  test.skip(
    process.env.MODEL_BACKEND === 'stub',
    'MODEL_BACKEND=stub: real-model smoke test skipped by configuration',
  );

  test('served model is the trained ResNet checkpoint (not the stub)', async ({ request }) => {
    const response = await request.get(`${API_URL}/api/v1/model/info`);
    expect(response.ok()).toBeTruthy();
    const info = await response.json();
    expect(info.available).toBeTruthy();
    expect(info.architecture).toMatch(/resnet(18|34|50|101)/);
    expect(info.model_version).not.toContain('stub');
    expect(info.class_mapping).toMatchObject({ benign: 0, malignant: 1 });
    expect(info.input_size).toBe(224);
    expect(info.calibration).toBe('NOT IMPLEMENTED');
  });

  test('real inference returns real probabilities from an authenticated session', async ({
    playwright,
  }) => {
    // The detection endpoint requires a session, so create a throwaway account
    // first and reuse its cookie jar for the inference request.
    const context = await playwright.request.newContext({ baseURL: API_URL });
    const username = `smoke${randomUUID().replace(/-/g, '').slice(0, 10)}`;
    const register = await context.post(`${API_URL}/api/v1/auth/register`, {
      data: {
        email: `${username}@example.com`,
        username,
        password: 'Sm0keTest!pass',
      },
    });
    expect(register.status()).toBe(201);

    // the detection endpoint is CSRF protected: echo the double-submit token
    const cookies = await context.storageState();
    const csrf =
      cookies.cookies.find((cookie) => cookie.name === 'csrf_token')?.value ?? '';

    const jpeg = makeJpeg();
    const fs = await import('node:fs');
    const response = await context.post(`${API_URL}/api/v1/detections`, {
      multipart: {
        image: {
          name: 'smoke.jpg',
          mimeType: 'image/jpeg',
          buffer: fs.readFileSync(jpeg),
        },
        save_history: 'false',
      },
      headers: {
        'Idempotency-Key': createHash('sha256').update(jpeg).digest('hex').slice(0, 32),
        'X-CSRF-Token': csrf,
      },
    });
    expect([200, 201]).toContain(response.status());
    const body = await response.json();
    expect(['benign', 'malignant']).toContain(body.prediction);
    expect(body.probabilities.benign + body.probabilities.malignant).toBeCloseTo(1, 4);
    expect(body.model_version).not.toContain('stub');
    await context.dispose();
  });
});
