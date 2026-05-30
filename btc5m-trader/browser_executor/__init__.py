"""
浏览器执行器客户端 — WSL → Windows HTTP API
"""
import json, os, subprocess, time, requests, logging

logger = logging.getLogger("browser-executor")


def get_windows_host() -> str:
    """自动检测WSL宿主机IP"""
    try:
        ip = os.popen("ip route 2>/dev/null | grep default | awk '{print $3}'").read().strip()
        if ip:
            return ip
    except:
        pass
    return "172.18.16.1"


def _candidate_urls() -> list[str]:
    urls = []
    env_url = os.getenv("POLYMARKET_EXECUTOR_URL", "").strip().rstrip("/")
    if env_url:
        urls.append(env_url)
    urls.extend([
        f"http://{get_windows_host()}:8789",
        "http://172.18.16.1:8789",
        "http://localhost:8789",
        "http://127.0.0.1:8789",
    ])
    deduped = []
    for url in urls:
        if url and url not in deduped:
            deduped.append(url)
    return deduped


EXECUTOR_URL = _candidate_urls()[0]
_last_probe_at = 0.0


def resolve_executor_url(force: bool = False) -> str:
    """Find a reachable Windows executor URL from WSL."""
    global EXECUTOR_URL, _last_probe_at
    now = time.time()
    if not force and EXECUTOR_URL and now - _last_probe_at < 10:
        return EXECUTOR_URL

    _last_probe_at = now
    for url in _candidate_urls():
        try:
            r = requests.get(f"{url}/heartbeat", timeout=1.5)
            if r.status_code == 200 and r.json().get("ready", False):
                EXECUTOR_URL = url
                return EXECUTOR_URL
        except Exception:
            continue
    return EXECUTOR_URL


def check_ready() -> bool:
    """检查浏览器执行器是否就绪"""
    try:
        url = resolve_executor_url(force=True)
        r = requests.get(f"{url}/heartbeat", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return data.get("ready", False)
        return False
    except requests.exceptions.ConnectionError:
        return False
    except Exception as e:
        logger.warning(f"executor check failed: {e}")
        return False


def place_order(direction: str, amount: float, slug: str) -> dict:
    """
    通过浏览器执行器下单
    返回: {success: bool, error?: str, ...}
    """
    payload = {"direction": direction, "amount": amount, "slug": slug}
    last_error = ""
    for _ in range(6):
        try:
            url = resolve_executor_url(force=True)
            r = requests.post(
                f"{url}/execute",
                json=payload,
                timeout=30,
            )
            return r.json()
        except requests.exceptions.ConnectionError:
            last_error = "CONNECTION_REFUSED"
            time.sleep(0.5)
        except Exception as e:
            last_error = str(e)
            break

    ps_result = place_order_via_windows(payload)
    if ps_result:
        return ps_result
    return {"success": False, "error": last_error or "CONNECTION_REFUSED", "executor_url": EXECUTOR_URL}


def place_order_via_windows(payload: dict) -> dict:
    """Fallback: call the Windows-side executor through Windows localhost."""
    try:
        body = json.dumps(payload, ensure_ascii=False)
        r = subprocess.run(
            [
                "curl",
                "-s",
                "-X",
                "POST",
                "http://172.18.16.1:8789/execute",
                "-H",
                "Content-Type: application/json",
                "-d",
                body,
            ],
            capture_output=True,
            timeout=45,
        )
        out = _decode_process_bytes(r.stdout).strip()
        if out:
            if "{" in out:
                out = out[out.find("{"):]
            data = json.loads(out)
            data.setdefault("transport", "windows_curl")
            return data
        if r.stderr:
            return {"success": False, "error": _decode_process_bytes(r.stderr).strip()[:500], "transport": "windows_curl"}
    except Exception as e:
        return {"success": False, "error": str(e), "transport": "windows_curl"}
    return {}


def _decode_process_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "utf-16le", "gbk", "cp936", "latin1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def get_status() -> dict:
    """获取执行器状态"""
    try:
        url = resolve_executor_url(force=True)
        r = requests.get(f"{url}/status", timeout=3)
        if r.status_code == 200:
            data = r.json()
            data["executor_url"] = url
            return data
        return {}
    except:
        return {}


def update_balance(balance: float):
    """更新执行器中的余额信息"""
    try:
        url = resolve_executor_url()
        requests.post(f"{url}/balance", json={"balance": balance}, timeout=3)
    except:
        pass
