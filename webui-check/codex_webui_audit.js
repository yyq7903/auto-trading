const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const BASE_URL = "http://localhost:5175/";
const OUT_DIR = "C:\\Users\\yyq\\Desktop\\自动交易\\webui\\截图\\新WebUI\\Codex验收";

async function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pageSnapshot(page) {
  return await page.evaluate(() => {
    const cards = [...document.querySelectorAll(".card-title")].map((x) => (x.textContent || "").trim());
    const buttons = [...document.querySelectorAll("button")].map((b) => ({
      text: (b.textContent || "").trim(),
      disabled: b.disabled,
    }));
    const tables = [...document.querySelectorAll("table")].map((table) => ({
      headers: [...table.querySelectorAll("thead th")].map((th) => {
        const style = getComputedStyle(th);
        return { text: (th.textContent || "").trim(), position: style.position, top: style.top };
      }),
      rows: table.querySelectorAll("tbody tr").length,
    }));
    const charts = [...document.querySelectorAll("canvas")].map((c) => ({
      width: c.width,
      height: c.height,
    }));
    const scrollContainers = [...document.querySelectorAll("*")]
      .filter((el) => el.scrollHeight > el.clientHeight + 20)
      .slice(0, 12)
      .map((el) => ({
        tag: el.tagName,
        cls: el.className,
        height: el.clientHeight,
        scrollHeight: el.scrollHeight,
        overflowY: getComputedStyle(el).overflowY,
      }));
    return {
      cards,
      buttons,
      tables,
      charts,
      scrollContainers,
      scrollHeight: document.body.scrollHeight,
      clientHeight: document.documentElement.clientHeight,
      bodyTextStart: (document.body.textContent || "").replace(/\s+/g, " ").slice(0, 800),
    };
  });
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });

  const consoleMessages = [];
  const requestFailures = [];
  const apiTimings = [];
  const requestStarts = new Map();

  page.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) {
      consoleMessages.push(`${msg.type()}: ${msg.text()}`);
    }
  });
  page.on("request", (req) => {
    if (req.url().includes("/api/")) requestStarts.set(req.url(), Date.now());
  });
  page.on("response", (res) => {
    const url = res.url();
    if (!url.includes("/api/")) return;
    const started = requestStarts.get(url);
    apiTimings.push({
      url: url.replace(BASE_URL, "/"),
      status: res.status(),
      ms: started ? Date.now() - started : -1,
    });
  });
  page.on("requestfailed", (req) => {
    requestFailures.push(`${req.method()} ${req.url()} ${req.failure()?.errorText || ""}`);
  });

  await page.goto(BASE_URL, { waitUntil: "networkidle", timeout: 40_000 });
  await wait(2500);

  const audit = {
    timestamp: new Date().toISOString(),
    pages: {},
    consoleMessages,
    requestFailures,
    apiTimings,
  };

  await page.screenshot({ path: path.join(OUT_DIR, "23_续接验收_交易控制.png"), fullPage: true });
  audit.pages.trade = await pageSnapshot(page);

  for (const [tabText, fileName, key] of [
    ["市场数据", "24_续接验收_市场数据.png", "market"],
    ["数据分析", "25_续接验收_数据分析.png", "analytics"],
    ["用户中心", "26_续接验收_用户中心.png", "user"],
  ]) {
    await page.getByRole("button", { name: new RegExp(tabText) }).click();
    await wait(2500);
    await page.screenshot({ path: path.join(OUT_DIR, fileName), fullPage: true });
    audit.pages[key] = await pageSnapshot(page);
  }

  await page.getByRole("button", { name: /交易控制/ }).click();
  await wait(1000);
  const nextPageButton = page.locator(".pagination .page-btn", { hasText: /^2$/ }).first();
  if (await nextPageButton.count()) {
    await nextPageButton.click();
    await wait(800);
    await page.screenshot({ path: path.join(OUT_DIR, "27_续接验收_交易记录分页.png"), fullPage: true });
    audit.pages.tradeAfterPagination = await pageSnapshot(page);
  }

  fs.writeFileSync(path.join(OUT_DIR, "codex_webui_audit_report.json"), JSON.stringify(audit, null, 2), "utf-8");
  await browser.close();
})();
