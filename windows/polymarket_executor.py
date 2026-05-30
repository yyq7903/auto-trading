# -*- coding: utf-8 -*-
"""
polymarket_executor.py — 最终版下单执行器
输入: slug, direction, amount
输出: 成交结果(orderID,status,makingAmount,tx)
验证: 通过 CLI 查询确认
"""
import io, sys, json, time, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

CHROME_PROFILE = r"C:\temp\chrome-profile-bot"
SAVE_DIR = r"C:\Users\yyq\Desktop\polymarket项目\btc5m数据"
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(r"C:\temp\debug", exist_ok=True)

def log(msg, tag="EXEC"):
    print(f"[{tag}] {time.strftime('%H:%M:%S')} {msg}", flush=True)

def place_order(slug: str, direction: str = "Up", amount_usd: float = 1.0):
    """
    下单主函数
    slug: btc-updown-5m-{unix_timestamp}
    direction: "Up" or "Down"
    amount_usd: 下单金额（默认 $1）
    """
    ts = str(int(time.time()))
    result = {
        "success": False,
        "slug": slug,
        "direction": direction,
        "amount": amount_usd,
        "orderID": None,
        "status": None,
        "makingAmount": None,
        "takingAmount": None,
        "transactionsHashes": None,
        "error": None,
    }

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=CHROME_PROFILE, channel="chrome",
        headless=False, slow_mo=100,
    )
    page = context.new_page()

    # === 监听 CLOB 成交响应 ===
    order_response = [None]

    def on_response(response):
        url = response.url
        if "clob.polymarket.com/order" in url and response.status == 200:
            try:
                data = response.json()
                if data.get("status") == "matched" or data.get("success"):
                    order_response[0] = data
                    log(f"✅ 成交! orderID={data.get('orderID','')[:30]} status={data.get('status')} "
                        f"making=${data.get('makingAmount','?')} tx={str(data.get('transactionsHashes',''))[:30]}", "CLOB")
            except:
                pass

    page.on("response", on_response)

    try:
        # 导航到市场
        url = f"https://polymarket.com/zh/event/{slug}"
        log(f"导航: {slug}")
        page.goto(url, timeout=20000, wait_until="domcontentloaded")

        # 等待交易面板加载（最核心的等待）
        for wait_i in range(15):
            page_ready = page.evaluate("""() => {
                const inp = [...document.querySelectorAll('input')].find(i =>
                    i.offsetParent && (i.placeholder?.includes('$') || i.placeholder === '0'));
                const btn = [...document.querySelectorAll('button')].find(b => {
                    const t = b.innerText?.trim() || '';
                    return (t === '买入\\u00a0Up' || t === '买入 Up' || t === '交易 Up' ||
                            t === '买入\\u00a0Down' || t === '买入 Down' || t === '交易 Down')
                        && !b.disabled && b.offsetParent;
                });
                return {has_input: !!inp, has_button: !!btn};
            }""")
            if page_ready.get("has_input") and page_ready.get("has_button"):
                log(f"面板就绪 (t+{wait_i+1}s)")
                break
            time.sleep(1)
        else:
            log("❌ 交易面板未就绪", "FAIL")
            result["error"] = "PANEL_NOT_READY"
            return result

        # 填金额
        filled = page.evaluate(f"""() => {{
            const inp = [...document.querySelectorAll('input')].find(i =>
                i.offsetParent && (i.placeholder?.includes('$') || i.placeholder === '0'));
            if (!inp) return false;
            const ns = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            ns.call(inp, '{amount_usd}');
            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
            return true;
        }}""")
        log(f"金额 ${amount_usd}: {'✅' if filled else '❌'}")
        time.sleep(1)

        # 点击买入按钮 — 使用 Playwright click (最可靠)
        buy_text = f"买入\u00a0{direction}" if direction in ("Up","Down") else None
        alt_texts = [f"买入\u00a0{direction}", f"买入 {direction}", f"交易 {direction}"]

        clicked = False
        for text in ([buy_text] + alt_texts) if buy_text else alt_texts:
            if clicked: break
            for btn in page.query_selector_all("button"):
                try:
                    if btn.is_visible() and not btn.is_disabled():
                        btn_text = btn.inner_text().strip()
                        # 使用 \u00a0 和空格都匹配
                        if btn_text.replace('\u00a0', ' ') == text.replace('\u00a0', ' '):
                            btn.click()
                            log(f"已点击: {text}", "CLICK")
                            clicked = True
                            break
                except:
                    pass
            if not clicked:
                # 备用: 用 evaluate 触发
                clicked = page.evaluate(f"""() => {{
                    const matches = ['买入\\u00a0{direction}', '买入 {direction}', '交易 {direction}'];
                    for (const b of document.querySelectorAll('button')) {{
                        const t = b.innerText?.trim() || '';
                        if (matches.includes(t) && !b.disabled && b.offsetParent) {{
                            b.dispatchEvent(new MouseEvent('click', {{bubbles:true,cancelable:true}}));
                            return true;
                        }}
                    }}
                    return false;
                }}""")
                if clicked:
                    log(f"已触发(JS): 买入 {direction}", "CLICK")

        if not clicked:
            log(f"❌ 未找到按钮: 买入 {direction}", "FAIL")
            result["error"] = "NO_BUTTON"
            return result

        # 等待成交结果
        for wait_i in range(10):
            time.sleep(2)
            if order_response[0] is not None:
                break
            log(f"等待成交... ({wait_i+1}/10)", "WAIT")

        if order_response[0] is not None:
            data = order_response[0]
            result["success"] = True
            result["orderID"] = data.get("orderID")
            result["status"] = data.get("status")
            result["makingAmount"] = data.get("makingAmount")
            result["takingAmount"] = data.get("takingAmount")
            result["transactionsHashes"] = data.get("transactionsHashes")
            result["errorMsg"] = data.get("errorMsg", "")
            log(f"🎉 成交! ID={result['orderID']}", "DONE")
        else:
            log("⚠️ 未捕获到成交响应（可能超时或未成交）", "WARN")
            # 截屏留档
            try:
                page.screenshot(path=os.path.join(SAVE_DIR, f"timeout_{ts}.png"))
            except:
                pass

        # 写 trades.jsonl
        trade_record = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "slug": slug,
            "direction": direction,
            "amount": amount_usd,
            "orderID": result["orderID"],
            "status": result["status"],
            "makingAmount": result["makingAmount"],
            "takingAmount": result["takingAmount"],
            "txHashes": result["transactionsHashes"],
            "mode": "live",
        }
        trades_path = os.path.join(SAVE_DIR, "trades.jsonl")
        try:
            with open(trades_path, "a") as f:
                f.write(json.dumps(trade_record, ensure_ascii=False) + "\n")
            log(f"trades.jsonl 已写入", "TRADE")
        except Exception as e:
            log(f"写入 trades.jsonl 失败: {e}", "WARN")

        return result

    except Exception as e:
        log(f"❌ 异常: {type(e).__name__}: {e}", "FAIL")
        import traceback; traceback.print_exc()
        result["error"] = f"{type(e).__name__}: {e}"
        return result
    finally:
        try: page.close()
        except: pass
        try: context.close()
        except: pass
        try: pw.stop()
        except: pass


if __name__ == "__main__":
    import sys as _sys
    n = int(time.time())
    c = (n // 300) * 300
    slug = f"btc-updown-5m-{c}"
    direction = _sys.argv[1] if len(_sys.argv) > 1 else "Up"
    amount = float(_sys.argv[2]) if len(_sys.argv) > 2 else 1.0
    override_slug = _sys.argv[3] if len(_sys.argv) > 3 else None
    if override_slug:
        slug = override_slug

    print(f"\n{'='*50}")
    print(f"Polymarket Executor")
    print(f"市场: {slug} (剩余 {c+300-n}s)")
    print(f"方向: {direction}  |  金额: ${amount}")
    print(f"{'='*50}\n")

    r = place_order(slug, direction, amount)

    print(f"\n{'='*50}")
    print(f"结果: {'✅ 成交' if r['success'] else '❌ 失败'}")
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print(f"{'='*50}")
