#!/usr/bin/env python3
"""Single-threaded Polymarket Browser Executor"""
import json, time, sys, traceback, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

PORT = 8789
MAX_ORDER_AMOUNT = 1.0
PROFILE = Path(r"C:\temp\chrome-profile-bot")
DEBUG_DIR = Path(r"C:\Users\yyq\Desktop\自动交易\runtime\debug")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
CRED_FILE = Path(r"C:\Users\yyq\Desktop\自动交易\runtime\clob_api_key_map.json")

state = {"ready": False, "started_at": None, "last_order": None, "last_error": None, "order_count": 0}
playwright = None
browser_context = None


def log(msg, tag="SERV"):
    print(f"[{tag}] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def init_browser():
    global playwright, browser_context
    log("Starting Chrome...", "INIT")
    playwright = sync_playwright().start()
    browser_context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        channel="chrome",
        headless=False,
        slow_mo=80,
        args=["--no-first-run", "--disable-blink-features=AutomationControlled"],
    )
    state["ready"] = True
    state["started_at"] = datetime.now().isoformat(timespec="seconds")
    log("Chrome ready", "INIT")


def place_order(slug, direction, amount):
    """Execute a Market order via browser automation."""
    if direction not in ("Up", "Down"):
        return {"success": False, "error": "BAD_DIRECTION"}
    amount = round(float(amount), 2)
    if amount <= 0:
        return {"success": False, "error": "BAD_AMOUNT"}
    if amount > MAX_ORDER_AMOUNT:
        return {"success": False, "error": "AMOUNT_EXCEEDS_LIMIT", "limit": MAX_ORDER_AMOUNT}

    page = browser_context.new_page()
    captured = []
    ts = int(time.time())
    screenshot_base = DEBUG_DIR / f"order_{slug}_{direction}_{ts}"
    
    def on_response(response):
        if "clob.polymarket.com/order" in response.url:
            try:
                data = response.json()
            except Exception:
                data = {"status": response.status, "body": str(response.body())[:500]}
            captured.append(data)
    
    page.on("response", on_response)
    
    try:
        url = f"https://polymarket.com/zh/event/{slug}"
        log(f"Navigating {url}", "ORDER")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # Login check
        if page.query_selector("text=登录") or page.query_selector("text=Log in") or page.query_selector("text=Sign in"):
            page.screenshot(path=str(screenshot_base) + "_login.png")
            return {"success": False, "error": "LOGIN_REQUIRED"}
        
        # Market mode
        for btn in page.query_selector_all("text=Market"):
            if btn.is_visible() and btn.get_attribute("data-state") != "checked":
                btn.click(force=True)
                page.wait_for_timeout(500)
                break
        
        page.wait_for_timeout(500)
        
        # Click direction
        dir_btn = page.query_selector(f"text={direction}")
        if not dir_btn or not dir_btn.is_visible():
            return {"success": False, "error": f"DIRECTION_{direction.upper()}_NOT_FOUND"}
        dir_btn.click(force=True)
        page.wait_for_timeout(800)
        
        # Fill amount. The visible page also has a search input, so prefer the
        # order ticket's quick amount button for the $1 market minimum.
        amount_set = False
        for btn in page.query_selector_all('button:has-text("+$1")'):
            if btn.is_visible():
                try:
                    btn.scroll_into_view_if_needed(timeout=2000)
                    btn.click(timeout=5000, force=True)
                    amount_set = True
                    break
                except:
                    continue
        if not amount_set:
            for inp in page.query_selector_all("input"):
                try:
                    ph = (inp.get_attribute("placeholder") or "").lower()
                    aria = (inp.get_attribute("aria-label") or "").lower()
                    typ = (inp.get_attribute("type") or "").lower()
                    if not inp.is_visible():
                        continue
                    if "search" in ph or "search" in aria or typ == "search":
                        continue
                    inp.fill(f"{amount:g}")
                    amount_set = True
                    break
                except:
                    continue
        if not amount_set:
            page.screenshot(path=str(screenshot_base) + "_no_amount.png", full_page=True)
            return {"success": False, "error": "AMOUNT_INPUT_NOT_FOUND"}
        
        page.wait_for_timeout(1200)
        log(f"Amount ${amount:g} {direction}", "ORDER")
        
        # Click the right-side order ticket submit button. Prefer the largest
        # visible buy button on the right half of the viewport, because the page
        # also contains unrelated navigation and market controls.
        buy_clicked = False
        ticket_buttons = page.evaluate(
            """(direction) => [...document.querySelectorAll('button')]
                .map((b, i) => {
                    const r = b.getBoundingClientRect();
                    const text = (b.innerText || '').replace(/\\s+/g, ' ').trim();
                    return {
                        i, text, disabled: !!b.disabled,
                        x: r.x, y: r.y, w: r.width, h: r.height,
                        right: r.x > window.innerWidth * 0.55,
                        area: r.width * r.height,
                    };
                })
                .filter(b => b.right && b.w > 120 && b.h > 30 && !b.disabled
                    && (b.text.includes(direction) || b.text.includes('买入') || b.text.includes('Buy')))
                .sort((a, b) => b.area - a.area)""",
            direction,
        )
        if ticket_buttons:
            b = ticket_buttons[0]
            page.mouse.click(b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)
            buy_clicked = True
            log(f"Clicked ticket submit: {b['text']}", "ORDER")

        buy_words = [
            f"Buy {direction}", "Buy", "buy", "Place order", "Place Order",
            "购买", "买入", "下单", "确认购买", "提交",
        ]
        if not buy_clicked:
            for word in buy_words:
                sel = f'button:has-text("{word}")'
                for btn in page.query_selector_all(sel):
                    if btn.is_visible():
                        try:
                            box = btn.bounding_box() or {}
                            if box.get("x", 0) < 700:
                                continue
                            btn.scroll_into_view_if_needed(timeout=2000)
                            btn.click(timeout=5000, force=True)
                            buy_clicked = True
                            break
                        except:
                            continue
                if buy_clicked:
                    break
        if not buy_clicked:
            diagnostics = page.evaluate(
                """() => [...document.querySelectorAll('button')]
                    .filter(b => !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length))
                    .map(b => ({
                        text: (b.innerText || '').replace(/\\s+/g, ' ').trim(),
                        disabled: !!b.disabled,
                        aria: b.getAttribute('aria-label') || '',
                        role: b.getAttribute('role') || '',
                    })).slice(0, 80)"""
            )
            page.screenshot(path=str(screenshot_base) + "_no_buy.png", full_page=True)
            return {"success": False, "error": "BUY_BUTTON_NOT_FOUND", "ticket_buttons": ticket_buttons, "buttons": diagnostics}
        
        # Wait for confirmation
        for _ in range(60):
            page.wait_for_timeout(500)
            if captured:
                break
            for btn in page.query_selector_all("button"):
                text = btn.inner_text() or ""
                if any(w in text for w in ("确认", "Confirm", "提交", "买入")) and btn.is_visible():
                    try:
                        box = btn.bounding_box() or {}
                        if box.get("x", 0) >= 600:
                            btn.click(force=True)
                            page.wait_for_timeout(500)
                            break
                    except:
                        pass
        
        page.screenshot(path=str(screenshot_base) + "_result.png")
        
        if not captured:
            return {"success": False, "error": "NO_CLOB_RESPONSE"}
        
        data = captured[-1]
        success = data.get("success") or data.get("status") == "matched"
        return {
            "success": bool(success),
            "slug": slug, "direction": direction, "amount": amount,
            "orderID": data.get("orderID", ""),
            "status": data.get("status", ""),
            "errorMsg": data.get("errorMsg", ""),
        }
    except Exception as e:
        log(f"Order error: {e}", "ERROR")
        traceback.print_exc()
        return {"success": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    finally:
        try:
            page.close()
        except:
            pass


def wallet_info():
    """Read non-secret Polymarket wallet identifiers from the logged-in profile."""
    page = None
    try:
        page = browser_context.new_page()
        page.goto("https://polymarket.com", wait_until="domcontentloaded", timeout=30000)
        data = page.evaluate(
            """() => {
                const out = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    if (!k || !k.toLowerCase().includes("polymarket")) continue;
                    const v = localStorage.getItem(k) || "";
                    if (k === "poly_clob_api_key_map") {
                        out[k] = {present: true, length: v.length};
                    } else {
                        out[k] = v;
                    }
                }
                return out;
            }"""
        )
        addresses = {}
        for key, value in data.items():
            text = json.dumps(value) if not isinstance(value, str) else value
            found = sorted(set(re.findall(r"0x[a-fA-F0-9]{40}", text)))
            if found:
                addresses[key] = found
        return {"success": True, "addresses": addresses}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    finally:
        try:
            if page:
                page.close()
        except:
            pass


def export_clob_creds():
    """Export current browser CLOB API credential map to a local runtime file."""
    page = None
    try:
        page = browser_context.new_page()
        page.goto("https://polymarket.com", wait_until="domcontentloaded", timeout=30000)
        raw = page.evaluate('() => localStorage.getItem("poly_clob_api_key_map") || ""')
        if not raw:
            return {"success": False, "error": "poly_clob_api_key_map not found"}
        data = json.loads(raw)
        CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
        CRED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        addresses = sorted(set(re.findall(r"0x[a-fA-F0-9]{40}", raw)))
        return {
            "success": True,
            "file": str(CRED_FILE),
            "entries": len(data) if isinstance(data, dict) else 1,
            "addresses": addresses,
        }
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    finally:
        try:
            if page:
                page.close()
        except:
            pass


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/status", "/heartbeat"):
            self._json(200, {**state, "ok": True, "max_order_amount": MAX_ORDER_AMOUNT})
        elif path == "/wallet-info":
            result = wallet_info()
            self._json(200 if result.get("success") else 500, result)
        elif path == "/export-clob-creds":
            result = export_clob_creds()
            self._json(200 if result.get("success") else 500, result)
        else:
            self._json(404, {"error": "not_found"})
    
    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self._json(400, {"error": "bad_json"})
            return
        
        if path == "/execute":
            result = place_order(
                slug=str(data.get("slug", "")),
                direction=str(data.get("direction", "")),
                amount=float(data.get("amount", 0)),
            )
            state["last_order"] = result
            state["order_count"] += 1 if result.get("success") else 0
            state["last_error"] = None if result.get("success") else result.get("error")
            self._json(200 if result.get("success") else 500, result)
        else:
            self._json(404, {"error": "not_found"})
    
    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def log_message(self, *args):
        pass


def main():
    log("=" * 40, "INIT")
    log(f"Polymarket Executor (single-threaded)", "INIT")
    log(f"Profile: {PROFILE}", "INIT")
    log(f"Order limit: ${MAX_ORDER_AMOUNT:g}", "INIT")
    log("=" * 40, "INIT")
    init_browser()
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    log(f"Server http://localhost:{PORT}", "SERV")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Stopping...")
        server.server_close()
        if browser_context:
            browser_context.close()
        if playwright:
            playwright.stop()


if __name__ == "__main__":
    main()
