// Isolated public-data run, with or without a saved domain reference; this test does not save one.
// PLAYWRIGHT_MODULE may point to an existing Playwright installation.
import assert from "node:assert/strict";
import { test } from "node:test";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const url = process.env.ONTOPOC_REFERENCE_URL;
const savedAs = process.env.ONTOPOC_REFERENCE_RUN;
assert.ok(url && savedAs, "provide an isolated server and a saved public-data run");
test("domain correspondence draft survives tab and module navigation; cancel and a new run reset it", async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}), args: ["--disable-gpu", "--disable-software-rasterizer", "--single-process"] });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    const response = await fetch(`${url}/api/ontology/runs/${savedAs}`, { headers: { Connection: "close" } });
    assert.ok(response.ok); const run = await response.json();
    await page.goto(url);
    await page.evaluate(run => localStorage.setItem("ontopoc.studio.last-result", JSON.stringify(run)), run);
    await page.reload();
    const click = name => page.getByRole("button", { name, exact: true }).click();
    const checkTab = name => page.getByRole("tab", { name: new RegExp(name) }).click();
    const product = page.getByRole("combobox", { name: "Product 对应对象", exact: true });
    await click("数据体检"); await checkTab("对照标准");
    const reference = page.getByRole("combobox", { name: "选择领域参考", exact: true });
    await page.waitForFunction(() => document.querySelector('[aria-label="选择领域参考"]')?.disabled === false);
    const selectionValues = () => page.locator('.dr-panel select').evaluateAll(selects => selects.map(s => [s.getAttribute('aria-label'), s.value]));
    const savedSelections = await selectionValues();
    await reference.selectOption("ecommerce");
    await product.selectOption("__skip");
    await page.getByRole("textbox", { name: "Product 不适用原因", exact: true }).fill("本次文件没有商品明细");
    await checkTab("数据体检");
    assert.equal(await product.isVisible(), false, "inactive correspondence must not occupy the page or receive focus");
    await checkTab("对照标准");
    await product.waitFor();
    assert.equal(await product.inputValue(), "__skip", "checking data must not discard manual correspondence");
    assert.equal(await page.getByRole("textbox", { name: "Product 不适用原因", exact: true }).inputValue(), "本次文件没有商品明细");
    await click("本体管理");
    assert.equal(await product.isVisible(), false);
    await click("数据体检"); await checkTab("对照标准");
    assert.equal(await product.inputValue(), "__skip", "opening another module must retain the draft");
    await click("取消修改");
    assert.deepEqual(await selectionValues(), savedSelections, "cancel restores the original saved reference and choices, including no reference");
    await reference.selectOption("ecommerce");
    await product.selectOption("__skip");
    await page.getByRole("textbox", { name: "Product 不适用原因", exact: true }).fill("仍是旧运行的草稿");
    await click("新建"); await click("打开示例数据表");
    await page.getByRole("heading", { name: /本体管理/ }).waitFor();
    await click("数据体检"); await checkTab("对照标准");
    assert.equal(await product.count(), 0, "a new run must not inherit the previous draft");
  } finally { await browser.close(); }
});
