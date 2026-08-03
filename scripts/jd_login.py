"""
京东登录脚本 — 用可视化浏览器登录一次，cookie 自动持久化。

使用方法：
  python3 scripts/jd_login.py

打开浏览器 → 手动登录京东 → 按 Enter 确认 → 完成。
后续 daily_job.py 的 headless 模式会自动读取此 profile 中的 cookie。

不需要手动导出 jd_cookies.json，不需要反复登录。
"""

import sys
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
BROWSER_PROFILE_DIR = PROJECT_DIR / ".browser_profile"
COOKIE_FILE = PROJECT_DIR / "data" / "jd_cookies.json"

# 确保目录存在
BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

# UA
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

from playwright.sync_api import sync_playwright

def main():
    print("=" * 60)
    print("🔑 京东登录 — 一次登录，持久有效")
    print("=" * 60)
    print()
    print("即将打开浏览器窗口...")
    print("请在浏览器中手动登录京东 (https://plogin.m.jd.com/login/login)")
    print("登录成功后回到终端按 Enter 即可完成。")
    print()

    print("正在启动浏览器...")
    p = sync_playwright().start()
    browser = p.chromium

    # 用持久化 context，cookie 自动存入 .browser_profile/
    context = browser.launch_persistent_context(
        user_data_dir=str(BROWSER_PROFILE_DIR),
        headless=False,  # 可视化，让你手动登录
        user_agent=MOBILE_UA,
        viewport={"width": 375, "height": 812},
        locale="zh-CN",
        args=["--no-sandbox"],
    )

    page = context.pages[0] if context.pages else context.new_page()

    # 直接打开京东移动端首页
    page.goto("https://plogin.m.jd.com/login/login", wait_until="domcontentloaded")
    print()
    print("📱 浏览器已打开京东登录页（移动端）")
    print("   请手动输入账号密码完成登录")
    print("   脚本将自动检测登录状态，登录成功后会继续...")
    print()

    # 自动检测登录状态，不再依赖 input()
    import time
    max_wait = 300  # 最多等 5 分钟
    check_interval = 3  # 每 3 秒检查一次
    waited = 0
    logged_in = False
    while waited < max_wait:
        time.sleep(check_interval)
        waited += check_interval

        # 检查 URL 是否已从登录页跳转
        current_url = page.url
        if 'login' not in current_url and 'passport' not in current_url:
            logged_in = True
            break

        # 也检查 cookie 中是否有 sd token 或 pin
        try:
            has_sd = page.evaluate("() => document.cookie.includes('sdtoken')")
            if has_sd:
                logged_in = True
                break
        except:
            pass

        if waited % 15 == 0:
            print(f"   等待登录中... (已等 {waited} 秒)")

    if not logged_in:
        print()
        print("⏰ 等待超时（5分钟），请确认是否已完成登录")
        print("   浏览器保持打开，登录完成后手动关闭窗口即可")
        print("   下次可重新运行 python3 scripts/jd_login.py")
        context.close()
        p.stop()
        return

    print(f"\n   ✓ 检测到登录完成 (等待了 {waited} 秒)")

    # 登录后导航到一个需要登录的页面验证
    page.goto("https://home.m.jd.com/myJd/newhome.action", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 保存 cookie
    cookies = context.cookies()
    print(f"\n🍪 获取到 {len(cookies)} 条 cookie")

    # 检查关键 cookie（移动端京东用 sdtoken + pin，不是 pt_key）
    has_sdtoken = any(c['name'] == 'sdtoken' for c in cookies)
    has_pin = any(c['name'] == 'pin' for c in cookies)
    has_unick = any(c['name'] == 'unick' for c in cookies)
    pin_val = next((c['value'] for c in cookies if c['name'] == 'pin'), '')
    print(f"   sdtoken: {'✓' if has_sdtoken else '✗ 缺失'}")
    print(f"   pin: {'✓' if has_pin else '✗ 缺失'} ({pin_val})")
    print(f"   unick: {'✓' if has_unick else '✗ 缺失'}")

    # 同时保存一份 JSON 备份（双保险）
    import json
    cookie_data = []
    for c in cookies:
        cookie_data.append({
            "domain": c.get("domain", ".jd.com"),
            "expirationDate": c.get("expires", -1),
            "hostOnly": False,
            "httpOnly": c.get("httpOnly", False),
            "name": c["name"],
            "path": c.get("path", "/"),
            "sameSite": c.get("sameSite", "Lax"),
            "secure": c.get("secure", False),
            "session": c.get("expires", -1) == -1,
            "storeId": None,
            "value": c["value"],
        })
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookie_data, f, ensure_ascii=False, indent=2)
    print(f"   JSON 备份: {COOKIE_FILE}")

    context.close()
    p.stop()

    print()
    if has_sdtoken and has_pin:
        print("✅ 登录成功！cookie 已持久化到浏览器 profile")
        print(f"   用户 pin: {pin_val}")
        print("   以后 daily_job.py headless 模式会自动使用这个登录状态")
        print("   （不需要再手动导出 cookie）")
    else:
        print("⚠️ sdtoken/pin 不完整，下次验价可能无法登录")
        print("   请重新运行 python3 scripts/jd_login.py")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
