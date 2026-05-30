import json, urllib.request, base64, re, sys

all_repos = set()
searches = [
    "polymarket+dashboard+vercel",
    "polymarket+frontend+dashboard+react",
    "prediction+market+frontend+dashboard",
    "polymarket+clob+frontend+ui",
    "polymarket+paper+trading+dashboard",
]

for q in searches:
    url = "https://api.github.com/search/repositories?q=" + q.replace(" ", "%20") + "&sort=stars&order=desc&per_page=5"
    req = urllib.request.Request(url, headers={"User-Agent": "codex"})
    try:
        data = json.loads(urllib.request.urlopen(req).read())
        for item in data.get("items", []):
            all_repos.add(item["full_name"])
    except:
        pass

more = [
    "AllAboutAI-YT/polymarket_bot_beginner",
    "trading-2028/polymarket-ai-trading",
    "emmanuelwestra/Polymarket-Trading-Bot",
    "suislanchez/polymarket-kalshi-weather-bot",
    "ventry089/weatherbot",
    "kapelame/kalshi-crypto-bot",
    "Razzleberryss/AstroTick",
    "declansx/sports-prediction-market-aggregator",
]
for r in more:
    all_repos.add(r)

for repo in sorted(all_repos):
    print("=" * 65)
    print(repo)
    try:
        url = "https://api.github.com/repos/" + repo + "/readme"
        req = urllib.request.Request(url, headers={"User-Agent": "codex"})
        data = json.loads(urllib.request.urlopen(req).read())
        readme = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

        demos = []
        for m in re.finditer(r"https?://[^\s\)\]<>\"']+", readme):
            link = m.group()
            if any(x in link.lower() for x in ["vercel", "demo", "polymarket", "app."]):
                demos.append(link)

        url2 = "https://api.github.com/repos/" + repo
        req2 = urllib.request.Request(url2, headers={"User-Agent": "codex"})
        info = json.loads(urllib.request.urlopen(req2).read())

        desc = (info.get("description") or "N/A")[:130]
        stars = info["stargazers_count"]
        lang = info.get("language") or "N/A"
        topics = info.get("topics", [])
        homepage = info.get("homepage") or ""

        print("  Stars: " + str(stars) + "  Lang: " + lang)
        print("  " + desc)
        if topics:
            print("  Topics: " + ", ".join(topics[:6]))
        if homepage:
            print("  Homepage: " + homepage)
        for d in demos[:3]:
            print("  Demo: " + d)

        lines = readme.split("\n")
        shown = 0
        for line in lines:
            clean = line.strip()
            if clean and not clean.startswith("[") and not clean.startswith("!") and not clean.startswith("<") and len(clean) > 20 and not clean.startswith("#"):
                print("  > " + clean[:160])
                shown += 1
                if shown >= 3:
                    break
        print()
    except Exception as e:
        print("  Error: " + str(e)[:50])
        print()
