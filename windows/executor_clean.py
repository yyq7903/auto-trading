#!/usr/bin/env python3
"""Single-threaded Polymarket Browser Executor"""
import json, time, sys, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

PORT = 8789
MAX_ORDER_AMOUNT = 1.0
PROFILE = Path(r"C:\temp\chrome-profile-bot")
DEBUG_DIR = Path(r"C:\temp")
DEBUG_DIR.mkdir(exist_ok=True)

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
        if page.query_selector("text=登录"):
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
        
        # Fill amount
        for inp in page.query_selector_all("input"):
            if inp.is_visible():
                inp.fill(f"{amount:g}")
                break
        
        page.wait_for_timeout(1200)
        log(f"Amount ${amount:g} {direction}", "ORDER")
        
        # Click Buy - try multiple approaches
        buy_clicked = False
        for sel in ['button:has-text("Buy")', 'button:has-text("buy")', 'button']:
            for btn in page.query_selector_all(sel):
                if btn.is_visible():
                    try:
                        btn.click(timeout=5000, force=True)
                        buy_clicked = True
                        break
                    except:
                        continue
            if buy_clicked:
                break
        if not buy_clicked:
            return {"success": False, "error": "BUY_BUTTON_NOT_FOUND"}
        
        # Wait for confirmation
        for _ in range(40):
            page.wait_for_timeout(500)
            if captured:
                break
            for btn in page.query_selector_all("button"):
                if "确认" in (btn.inner_text() or ""):
                    btn.click(force=True)
                    break
        
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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/status", "/heartbeat"):
            self._json(200, {**state, "ok": True, "max_order_amount": MAX_ORDER_AMOUNT})
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
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
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
