import json, urllib.request, base64, sys, os

repos = [
    ("themesberg/flowbite-admin-dashboard", "Tailwind CSS 管理面板 - 现代化设计"),
    ("coreui/coreui-free-bootstrap-admin-template", "Bootstrap 管理面板 - 专业版"),
    ("thetalha-dev/Futuristic-Trading-Dashboard", "赛博朋克交易面板 - 已适配"),
    ("dev4traders/prop-dashboard", "Vue3 交易面板"),
]

for name, label in repos:
    print("=" * 60)
    print("【" + label + "】")
    print("https://github.com/" + name)
    try:
        url = "https://api.github.com/repos/" + name + "/readme"
        req = urllib.request.Request(url, headers={"User-Agent": "codex"})
        data = json.loads(urllib.request.urlopen(req).read())
        readme = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        for line in readme.split("\n"):
            line = line.strip()
            if line and not line.startswith("[") and not line.startswith("!") and not line.startswith("<") and len(line) > 20:
                print("  " + line[:150])
                break
    except Exception as e:
        print("  (readme unavailable)")
    print()
