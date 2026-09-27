// Isolated public-data run only. Saves one domain mapping; model/health responses are controlled.
import assert from 'node:assert/strict';
import { test } from 'node:test';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const url = process.env.ONTOPOC_REFERENCE_URL, savedAs = process.env.ONTOPOC_REFERENCE_RUN;
assert.ok(url && savedAs, 'provide an isolated server and saved public-data run');
test('QA response preserves the draft while explicit save and changed ontology refresh it', async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}), args: ['--disable-gpu', '--disable-software-rasterizer', '--single-process'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    const getRun = async () => { const r = await fetch(`${url}/api/ontology/runs/${savedAs}`, { headers: { Connection: 'close' } }); assert.ok(r.ok); return r.json(); };
    let answer = await getRun();
    await page.route('**/api/ontology/health', route => route.fulfill({ json: { model_ready: true, stale: false } }));
    await page.route('**/api/ontology/ask', route => route.fulfill({ json: structuredClone(answer) }));
    await page.goto(url);
    await page.evaluate(run => localStorage.setItem('ontopoc.studio.last-result', JSON.stringify(run)), answer);
    await page.reload();
    const click = name => page.getByRole('button', { name, exact: true }).click();
    const referenceTab = async () => { await click('数据体检'); await page.getByRole('tab', { name: /对照标准/ }).click(); };
    const product = page.getByRole('combobox', { name: 'Product 对应对象', exact: true });
    const reason = page.getByRole('textbox', { name: 'Product 不适用原因', exact: true });
    const ask = async () => {
      await click('智能问答');
      await page.locator('#os-question').fill('客户有多少？');
      const response = page.waitForResponse(r => r.url().endsWith('/api/ontology/ask'));
      await page.locator('#os-question').press('Enter');
      assert.equal((await response).status(), 200);
      await page.getByRole('button', { name: '问', exact: true }).waitFor();
      await referenceTab();
      await page.waitForFunction(() => document.querySelector('[aria-label="选择领域参考"]')?.disabled === false);
    };
    await referenceTab();
    await page.getByRole('combobox', { name: '选择领域参考', exact: true }).selectOption('ecommerce');
    await product.selectOption('__skip'); await reason.fill('本次没有商品明细');
    await ask();
    assert.equal(await product.count(), 1, 'QA must preserve the selected draft reference');
    assert.equal(await product.inputValue(), '__skip');
    assert.equal(await reason.inputValue(), '本次没有商品明细');
    await click('预览差异'); await click('确认对应并保存');
    await page.locator('.dr-saved').waitFor();
    assert.doesNotMatch(await page.locator('.dr-actions').innerText(), /尚未保存/);
    await reason.fill('未保存的新原因'); await click('取消修改');
    assert.equal(await reason.inputValue(), '本次没有商品明细', 'cancel must restore the newly saved record');
    answer = await getRun();
    answer.ontology.object_types[0].label += '（已修订）';
    await page.route(`**/api/ontology/runs/${savedAs}/reference`, async route => {
      const response = await route.fetch(); const ctx = await response.json();
      await route.fulfill({ json: { ...ctx, stale: ['本次本体或字段已变化，请重新核对并确认对应。'] } });
    });
    await reason.fill('不应沿用到变更后的本体');
    await ask();
    assert.equal(await product.inputValue(), '', 'a changed ontology must reload and clear stale correspondence');
    assert.match(await page.locator('.dr-panel').innerText(), /本次本体或字段已变化/);
  } finally { await browser.close(); }
});
