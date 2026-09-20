/**
 * Presentation check: verify the running product against a real headless browser.
 *
 * Why this exists: screenshots are load-bearing evidence in the README, but a PNG
 * committed to a repository cannot prove anything by itself.  This script drives the
 * real UI and asserts on the live DOM, so the branding, the medical wording and the
 * evaluation page contents are checkable without looking at any image.
 *
 * Requires a running backend (default http://127.0.0.1:8000) and a served frontend
 * build (default http://localhost:4173, e.g. `npm run preview`).
 *
 * Usage (repository root):
 *   node scripts/presentation_check.mjs [--base-url http://localhost:4173]
 * Exit code 0 = all checks passed.
 */

import { chromium } from '../frontend/node_modules/playwright/index.mjs';

const args = process.argv.slice(2);
function argValue(name, fallback) {
  const index = args.indexOf(name);
  return index !== -1 && args[index + 1] ? args[index + 1] : fallback;
}

const BASE_URL = argValue('--base-url', 'http://localhost:4173');
const API_URL = argValue('--api-url', 'http://127.0.0.1:8000');

const results = [];
function check(name, condition, detail = '') {
  results.push({ name, ok: Boolean(condition), detail });
  console.log(`${condition ? '[ok]  ' : '[FAIL]'} ${name}${detail ? ` — ${detail}` : ''}`);
}

async function main() {
  // the API must be reachable, otherwise every DOM assertion below is meaningless
  const health = await fetch(`${API_URL}/api/v1/health`).then((r) => r.json());
  check('backend healthy and serving the trained model', health.status === 'ok' && health.model === true,
    `model_version=${health.model_version}`);

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });

  // ---------- landing page ----------
  await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle' });
  const h1 = (await page.locator('h1').first().innerText()).replace(/\s+/g, '');
  check('homepage headline is the rebranded product name',
    h1.includes('皮肤病变智能识别') && h1.includes('辅助分析平台'), h1);

  const body = await page.locator('body').innerText();
  check('homepage states the project is not a commercial product / not deployed',
    body.includes('不是该公司的商业产品或生产系统') && body.includes('没有在任何医疗机构上线使用'));
  check('homepage states it is not for diagnosis',
    body.includes('不能替代专业医生诊断'));
  check('homepage does not present itself as a school assignment',
    !body.includes('学校实习') && !body.includes('作业') && !body.includes('老师'));

  const forbidden = ['确诊', '你患有皮肤癌', '100%', '无需就医', '保证'];
  const offenders = forbidden.filter((word) => body.includes(word));
  check('no forbidden medical wording on the homepage', offenders.length === 0, offenders.join(', '));

  const navLabels = await page.locator('header nav a').allInnerTexts();
  check('navigation exposes the product surfaces',
    ['关于', '模型评测'].every((label) => navLabels.some((text) => text.trim() === label)),
    navLabels.map((t) => t.trim()).join(' | '));

  // ---------- model evaluation page ----------
  await page.goto(`${BASE_URL}/evaluation`, { waitUntil: 'networkidle' });
  const evalText = await page.locator('[data-testid="evaluation-page"]').innerText();
  check('evaluation page shows the internal result', evalText.includes('92.96%'));
  check('evaluation page shows the independent external result', evalText.includes('78.54%'));
  check('evaluation page states the external target was not met', evalText.includes('未达标'));
  check('evaluation page discloses the false negatives', evalText.includes('137'));
  check('evaluation page refuses to over-attribute the drop',
    evalText.includes('无法对下降原因做严格归因'));
  check('evaluation page states the model is not a new capability',
    evalText.includes('不代表新增的模型能力'));

  const plots = await page.locator('[data-testid="evaluation-page"] img').count();
  const brokenPlots = await page.evaluate(() =>
    Array.from(document.querySelectorAll('[data-testid="evaluation-page"] img'))
      .filter((img) => img.complete && img.naturalWidth === 0).length,
  );
  check('evaluation plots are served and decoded', plots >= 4 && brokenPlots === 0,
    `${plots} img, ${brokenPlots} broken`);

  // ---------- about page ----------
  await page.goto(`${BASE_URL}/about`, { waitUntil: 'networkidle' });
  const aboutText = await page.locator('body').innerText();
  check('about page states the internship context accurately',
    aboutText.includes('广州泰迪智能科技有限公司相关人员参与项目指导与实践'));
  check('about page lists known limitations', aboutText.includes('已知局限'));
  check('about page documents the AI-assisted development process',
    aboutText.includes('AI 辅助开发') || aboutText.includes('AI Coding Agent'));

  // ---------- metadata ----------
  const title = await page.title();
  check('document title uses the new product name',
    title.includes('皮肤病变智能识别与辅助分析平台'), title);

  await browser.close();

  const failed = results.filter((item) => !item.ok);
  console.log(`\nPRESENTATION CHECK: ${failed.length === 0 ? 'PASS' : 'FAIL'} ` +
    `(${results.length - failed.length}/${results.length} checks passed)`);
  process.exit(failed.length === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error('[FAIL]', error);
  process.exit(1);
});
