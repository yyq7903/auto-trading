# -*- coding: utf-8 -*-
"""
executor_launcher.py — Browser Executor 自动启动/保活/热重启器
功能：
  1. 检测端口 8789 占用，杀掉旧进程
  2. 启动 browser_executor_server.py
  3. 监听文件变化，自动重启
  4. 崩溃自动重启
  5. 日志记录
"""
import io, sys, time, os, subprocess, threading, hashlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

EXECUTOR_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_executor_server.py")
WATCH_INTERVAL = 3  # 秒
HEALTH_CHECK_TIMEOUT = 15  # 15秒无响应视为卡死

def log(msg):
    print(f"[LAUNCHER] {time.strftime('%H:%M:%S')} {msg}", flush=True)

def kill_port(port=8789):
    """杀掉占用端口的进程"""
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port}"',
            shell=True, capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split()
            if len(parts) >= 5 and 'LISTENING' in line:
                pid = parts[-1]
                log(f"杀掉旧进程 PID={pid} (端口 {port})")
                subprocess.run(f'taskkill /f /pid {pid}', shell=True, timeout=5)
                return True
    except:
        pass
    return False

def file_hash(path):
    """计算文件 MD5 用于检测变更"""
    try:
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return ""

def start_executor():
    """启动 executor 子进程"""
    log(f"启动: {EXECUTOR_SCRIPT}")
    # 用 CREATE_NEW_CONSOLE 创建新窗口，或用 DETACHED_PROCESS 不创建窗口
    # 这里用 subprocess.Popen 直接用当前窗口
    proc = subprocess.Popen(
        [sys.executable, EXECUTOR_SCRIPT],
        cwd=os.path.dirname(EXECUTOR_SCRIPT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    return proc

def monitor_output(proc):
    """读取子进程输出并转发到日志"""
    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                print(line, end='', flush=True)
    except:
        pass

if __name__ == "__main__":
    log("=" * 50)
    log("Executor Launcher 启动")
    log(f"监控脚本: {EXECUTOR_SCRIPT}")
    log("=" * 50)

    last_hash = file_hash(EXECUTOR_SCRIPT)
    proc = None
    restart_count = 0

    while True:
        try:
            # 检查当前进程是否存活
            if proc is None or proc.poll() is not None:
                if proc and proc.poll() is not None:
                    log(f"进程已退出 (code={proc.poll()})，重启...")
                    restart_count += 1

                # 杀掉旧端口占用
                kill_port(8789)
                time.sleep(1)

                # 启动新进程
                proc = start_executor()
                threading.Thread(target=monitor_output, args=(proc,), daemon=True).start()
                log(f"已启动 (PID={proc.pid}, 重启#{restart_count})")

                # 等待就绪
                for i in range(20):
                    time.sleep(1)
                    try:
                        import urllib.request
                        resp = urllib.request.urlopen("http://127.0.0.1:8789/heartbeat", timeout=2)
                        if resp.status == 200:
                            log("✅ Executor 就绪")
                            break
                    except:
                        pass

            # 检测文件变更
            current_hash = file_hash(EXECUTOR_SCRIPT)
            if current_hash != last_hash:
                log(f"🔄 检测到文件变更，热重启...")
                last_hash = current_hash
                if proc:
                    proc.kill()
                    proc.wait(timeout=5)
                proc = None
                continue

            # 健康检查：检测卡死
            import urllib.request
            healthy = False
            try:
                resp = urllib.request.urlopen("http://127.0.0.1:8789/heartbeat", timeout=5)
                healthy = resp.status == 200
            except:
                pass
            
            if proc and proc.poll() is None and not healthy:
                log("⚠️ Executor 无响应（健康检查失败），可能卡死")
                # 再等 HEALTH_CHECK_TIMEOUT 秒确认
                time.sleep(HEALTH_CHECK_TIMEOUT)
                try:
                    resp = urllib.request.urlopen("http://127.0.0.1:8789/heartbeat", timeout=5)
                    if resp.status != 200:
                        raise Exception("still unhealthy")
                except:
                    log("❌ Executor 卡死，强制重启")
                    try:
                        proc.kill()
                        proc.wait(timeout=5)
                    except:
                        pass
                    kill_port(8789)
                    proc = None

            time.sleep(WATCH_INTERVAL)

        except KeyboardInterrupt:
            log("🛑 收到 Ctrl+C，退出")
            if proc:
                proc.kill()
            sys.exit(0)
        except Exception as e:
            log(f"⚠️ 异常: {e}")
            time.sleep(5)
