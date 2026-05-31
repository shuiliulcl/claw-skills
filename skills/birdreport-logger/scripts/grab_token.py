#!/usr/bin/env python3
"""一键抓取 birdreport token —— 自动开浏览器、检查登录态、读真实 X-Auth-Token。

用你已装的 Chrome（channel="chrome"，不下载 chromium）+ 专属配置目录
（~/.birdwatch/browser_profile，登录态长期保留，cookie 能存好几天）。
做法：打开会员页 → 拦截页面发往 api.birdreport.cn 的请求 → 读其 X-Auth-Token 头
（最可靠，不靠猜存储键名）。

- 已登录（多数情况）→ 秒抓 token，全自动。
- 登录过期 → 浏览器停在登录页，你填一次验证码登录，脚本自动抓到后继续。

默认抓到后写入 ~/.birdwatch/config.json 的 birdreport.token。脚本运行时即读取该文件，
所以 token 更新后 cc-connect 无需重建（不再依赖环境变量）。加 --print-only 只打印不写入。

依赖：pip install playwright（用系统 Chrome，无需 playwright install）。
"""
import os
import sys
import time

import birdwatch_config as cfg

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(os.path.expanduser("~"), ".birdwatch", "browser_profile")
MEMBER_URL = "https://www.birdreport.cn/member/index.html"
WAIT_LOGIN_SEC = 240


# 扫 localStorage/sessionStorage/cookie 里的 32 位大写十六进制（token 特征）
_SCAN_JS = r"""() => {
  const p=/[0-9A-F]{32}/g, s=new Set();
  const scan=(st)=>{try{for(let i=0;i<st.length;i++){((st.getItem(st.key(i))||'').match(p)||[]).forEach(x=>s.add(x));}}catch(e){}};
  scan(localStorage); scan(sessionStorage);
  (document.cookie.match(p)||[]).forEach(x=>s.add(x));
  return Array.from(s);
}"""


def grab():
    from playwright.sync_api import sync_playwright
    os.makedirs(PROFILE, exist_ok=True)
    captured = {}

    def on_request(req):
        if "api.birdreport.cn" in req.url:
            t = req.headers.get("x-auth-token")
            if t and len(t) >= 20:
                captured["token"] = t

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                PROFILE, channel="chrome", headless=False,
                args=["--no-first-run", "--no-default-browser-check"])
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"无法用系统 Chrome 启动：{e}\n"
                             "（确认已装 Google Chrome）\n")
            return None

        # 请求监听挂到所有页面（含登录后新开的）
        ctx.on("page", lambda pg: pg.on("request", on_request))
        for pg in ctx.pages:
            pg.on("request", on_request)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(MEMBER_URL, timeout=30000)
        except Exception:  # noqa: BLE001
            pass

        deadline = time.time() + WAIT_LOGIN_SEC
        start = time.time()
        prompted = False
        last_nav = time.time()
        while time.time() < deadline:
            # 1) 请求头捕获（最准）
            if captured.get("token"):
                break
            # 2) localStorage/cookie 扫描（登录后 token 必在其中）
            try:
                cands = page.evaluate(_SCAN_JS)
                if len(cands) == 1:
                    captured["token"] = cands[0]
                    break
                elif len(cands) > 1:
                    captured.setdefault("cands", cands)  # 多候选，等请求头定夺
            except Exception:  # noqa: BLE001
                pass
            # 已登录但没抓到请求：每 ~8s 导航会员页一次，逼它发 api 请求
            if time.time() - start > 4 and time.time() - last_nav > 8:
                try:
                    page.goto(MEMBER_URL, timeout=20000)
                except Exception:  # noqa: BLE001
                    pass
                last_nav = time.time()
            if not prompted and time.time() - start > 6 and not captured.get("cands"):
                print("未检测到登录态：请在弹出的 Chrome 里登录 birdreport.cn（填验证码），"
                      "登录后自动抓取，无需其它操作…")
                prompted = True
            time.sleep(1.5)

        tok = captured.get("token")
        if not tok and captured.get("cands"):
            tok = captured["cands"][0]  # 兜底：取首个候选
        try:
            ctx.close()
        except Exception:  # noqa: BLE001
            pass
        return tok


def main():
    tok = grab()
    if not tok:
        sys.stderr.write("未抓到 token（超时或登录失败）。\n")
        sys.exit(1)
    print(f"抓到 token: {tok[:8]}…")
    if "--print-only" in sys.argv:
        print(tok)
        return
    cfg.set_value("birdreport.token", tok)
    print("✓ 已写入 ~/.birdwatch/config.json。脚本运行时即读取，cc-connect 无需重建。")


if __name__ == "__main__":
    main()
