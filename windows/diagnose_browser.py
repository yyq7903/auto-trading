# -*- coding: utf-8 -*-
"""
Polymarket Playwright 自动化链路诊断工具
诊断浏览器加载后"无任何动作"的问题
"""
import io, sys, time, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

CHROME_PROFILE = r"C:\temp\chrome-profile-bot"
LOG_DIR = r"C:\Users\yyq\Desktop\polymarket项目\btc5m数据"
os.makedirs(LOG_DIR, exist_ok=True)
TRACE_PATH = os.path.join(LOG_DIR, "trace_diagnose.zip")

def log(msg, tag="DIAG"):
    ts = time.strftime("%H:%M:%S")
    print(f"[{tag}] {ts} {msg}", flush=True)

print("=" * 60)
print("  Polymarket Playwright 链路诊断")
print("=" * 60)

pw = sync_playwright().start()
context = pw.chromium.launch_persistent_context(
    user_data_dir=CHROME_PROFILE,
    channel="chrome",
    headless=False,
    slow_mo=300,  # 慢动作300ms，让你能观察
    args=["--no-first-run"],
)
page = context.new_page()

# ===== 开启 tracing =====
context.tracing.start(screenshots=True, snapshots=True, sources=True)

log("[1/8] 页面打开", "STEP")
page.goto("https://polymarket.com/zh", timeout=60000)
time.sleep(5)

# ===== 1. 页面是否真正加载完成 =====
log("=" * 50, "CHECK")
log("第1步: 页面加载状态", "CHECK")
print(f"  current_url : {page.url}", flush=True)
print(f"  readyState  : {page.evaluate('document.readyState')}", flush=True)
print(f"  page.title  : {page.title()}", flush=True)

# 检查是否卡在 Cloudflare
body_text = page.inner_text("body")
if "cf-browser-verification" in body_text or "Checking your browser" in body_text:
    log("❌ 卡在 Cloudflare 验证！", "CHECK")
else:
    log("✅ 通过 Cloudflare", "CHECK")

# ===== 2. 登录状态诊断 =====
log("=" * 50, "CHECK")
log("第2步: 登录状态", "CHECK")

# 看页面实际文本中有没有这些关键词
login_keywords = ["连接钱包", "Connect Wallet", "Connect wallet", "登陆", "登录", "Log In", "Sign In"]
wallet_keywords = ["钱包余额", "Balance", "我的钱包", "Account", profile := "0x"]

found_login = False
for kw in login_keywords:
    if kw.lower() in body_text.lower():
        log(f"⚠️ 发现登录提示词: '{kw}'", "CHECK")
        found_login = True

if found_login:
    log("❌ 页面显示需要登录", "CHECK")
else:
    log("✅ 未发现登录按钮（已登录？）", "CHECK")

# 尝试查找登录按钮的具体位置
login_btns = page.query_selector_all("button")
log(f"  页面上共有 {len(login_btns)} 个 <button> 元素", "CHECK")
for i, btn in enumerate(login_btns[:20]):  # 前20个
    try:
        if btn.is_visible():
            txt = btn.inner_text().strip()[:60]
            log(f"  button[{i}]: visible=True text='{txt}'", "CHECK")
    except:
        pass

# 检查钱包地址
wallet_elements = page.query_selector_all("[class*=wallet], [class*=address], [class*=account]")
log(f"  钱包相关元素: {len(wallet_elements)} 个", "CHECK")

# 检查 Connect Wallet 是否可见
try:
    connect_btn = page.locator("button:has-text('Connect')")
    connect_count = connect_btn.count()
    if connect_count > 0:
        log(f"⚠️ 'Connect' 按钮可见: {connect_count} 个", "CHECK")
    else:
        log("✅ 无 'Connect' 按钮（已登录）", "CHECK")
except Exception as e:
    log(f"  Connect 检查异常: {e}", "CHECK")

# ===== 3. 记录当前完整 body 文本（前2000字符）=====
log("=" * 50, "CHECK")
log("第3步: 页面文本摘要（前1500字符）", "CHECK")
print(body_text[:1500], flush=True)
print("...（截断）", flush=True)

# ===== 4. Selector 检查 =====
log("=" * 50, "CHECK")
log("第4步: 交易相关 Selector 检查", "CHECK")

selectors_to_check = [
    ("Buy 按钮", "button:has-text('Buy')"),
    ("买入 按钮", "button:has-text('买入')"),
    ("YES 按钮", "button:has-text('YES')"),
    ("NO 按钮", "button:has-text('NO')"),
    ("价格输入框", "input[type='number']"),
    ("确认按钮", "button:has-text('Confirm')"),
    ("下单按钮", "button:has-text('Place')"),
    ("确认 按钮(chinese)", "button:has-text('确认')"),
]

for name, sel in selectors_to_check:
    try:
        count = page.locator(sel).count()
        visible = False
        if count > 0:
            visible = page.locator(sel).first.is_visible()
        status = "✅" if (count > 0 and visible) else "⚠️"
        log(f"  {status} {name}: locator='{sel}' count={count} visible={visible}", "SELECTOR")
    except Exception as e:
        log(f"  ❌ {name}: 异常 {e}", "SELECTOR")

# ===== 5. iframe 检查 =====
log("=" * 50, "CHECK")
log("第5步: iframe 检查", "CHECK")
frames = page.frames
log(f"  共有 {len(frames)} 个 frame", "CHECK")
for i, f in enumerate(frames):
    try:
        log(f"  frame[{i}]: url={f.url[:100]}", "CHECK")
    except:
        log(f"  frame[{i}]: <无法读取>", "CHECK")

# ===== 6. 阻塞弹窗检查 =====
log("=" * 50, "CHECK")
log("第6步: 阻塞弹窗/模态框检查", "CHECK")

blocking_patterns = [
    ("风险提示", ["风险", "risk", "warning"]),
    ("地区限制", ["地区", "region", "restricted", "not available in"]),
    ("Onboarding", ["onboarding", "介绍", "第一步", "welcome", "开始使用"]),
    ("Cookie", ["cookie", "Cookies"]),
    ("模态框", ["modal", "overlay"]),
]

for name, patterns in blocking_patterns:
    for pat in patterns:
        if pat.lower() in body_text.lower():
            log(f"⚠️ 发现阻塞提示: '{name}' (关键词: '{pat}')", "CHECK")
            break

# 检查全屏遮罩
try:
    overlays = page.query_selector_all("[class*=overlay], [class*=modal], [role=dialog]")
    for ol in overlays:
        if ol.is_visible():
            log(f"⚠️ 可见遮罩/模态框: {ol.inner_text()[:100]}", "CHECK")
except:
    pass

# ===== 7. 截图 =====
log("=" * 50, "CHECK")
log("第7步: 截取页面截图", "CHECK")
screenshot_path = os.path.join(LOG_DIR, f"diagnose_{time.strftime('%Y%m%d_%H%M%S')}.png")
page.screenshot(path=screenshot_path, full_page=True)
log(f"  📸 截图已保存: {screenshot_path}", "CHECK")

# ===== 8. 保存 trace =====
log("=" * 50, "CHECK")
log("第8步: 保存 Trace", "CHECK")
context.tracing.stop(path=TRACE_PATH)
log(f"  📦 Trace 已保存: {TRACE_PATH}", "CHECK")

log("=" * 60, "DONE")
log("诊断完成！查看以上信息分析问题", "DONE")
log(f"截图: {screenshot_path}", "DONE")
log(f"Trace: {TRACE_PATH}", "DONE")
print("", flush=True)

# 保持浏览器打开10秒让你观察
log("浏览器保持10秒供观察...", "WAIT")
time.sleep(10)
log("诊断结束，关闭浏览器", "WAIT")
context.close()
pw.stop()
