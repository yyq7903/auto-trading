# -*- coding: utf-8 -*-
"""策略交易 — 修复版，处理方向流动性"""
import sys,json,time,urllib.request
sys.path.insert(0,'/mnt/c/Users/yyq/Desktop/自动交易/btc5m-trader')
from shared.btc_price import get_btc_fresh,fetch_ptb

EXECUTOR="http://172.18.16.1:8789"
GAP_MIN=10
SAVE="/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据"

def log(m):print(f"[{time.strftime('%H:%M:%S')}] {m}",flush=True)

log("启动")

while True:
    try:
        n=int(time.time())
        c=(n//300)*300
        slug=f"btc-updown-5m-{c}"
        rem=c+300-n
        
        # 入场窗口T-28~T-5
        if rem>28 or rem<5:
            time.sleep(3); continue
        
        btc=get_btc_fresh()
        if btc<=0: time.sleep(2);continue
        ptb=fetch_ptb(slug)
        if ptb<=0: time.sleep(2);continue
        gap=btc-ptb
        d="Up"if gap>=0 else"Down"
        log(f"{slug} gap=${gap:+,.2f} {d} r={rem}s")
        
        if abs(gap)<GAP_MIN:
            time.sleep(3);continue
        
        log(f"信号! gap=${abs(gap):.0f}≥${GAP_MIN} {d}")
        
        body=json.dumps({"slug":slug,"direction":d,"amount":1}).encode()
        req=urllib.request.Request(f"{EXECUTOR}/execute",data=body,headers={"Content-Type":"application/json"})
        try:
            resp=urllib.request.urlopen(req,timeout=90)
            r=json.loads(resp.read())
            
            if r.get("error")=="NO_LIQUIDITY":
                log(f"⏭ {d}方向无流动性，跳过这窗口")
                time.sleep(60);continue
            
            log(f"结果: {json.dumps(r,ensure_ascii=False)}")
            
            if r.get("success"):
                log(f"成交! id={r['orderID'][:30]} s={r['status']}")
            else:
                log(f"失败: {r.get('error')}")
            
            # 记录
            rec={
                "time":time.strftime("%Y-%m-%dT%H:%M:%S"),
                "slug":slug,"direction":d,"gap":round(gap,2),
                "btc_entry":round(btc,2),"ptb":round(ptb,2),"amount":1,
                "orderID":r.get("orderID"),"status":r.get("status"),
                "txHashes":r.get("transactionsHashes"),
                "mode":"live"
            }
            with open(f"{SAVE}/trades.jsonl","a")as f:
                f.write(json.dumps(rec,ensure_ascii=False)+"\n")
        except Exception as e:
            log(f"请求异常:{e}")
        
        time.sleep(60)
    except KeyboardInterrupt:log("停止");break
    except Exception as e:log(f"err:{e}");time.sleep(3)
