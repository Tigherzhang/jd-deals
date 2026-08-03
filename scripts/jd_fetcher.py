"""
京东商品验价模块 - Playwright 浏览器验价
在商品推送前，打开京东商品页验证价格和在售状态。

策略：
1. 使用持久化浏览器配置（保留 cookie）
2. 打开京东移动端商品页 (item.m.jd.com)
3. 检查是否已登录（未登录则页面价格被隐藏为 "¥1?"）
4. 从 window._itemInfo.priceFloor.ext.jdPrice 提取页面实际价格
5. 与 API 返回价格做数值比对（允许 ±0.15 容差）
6. 检查 warestatus 确认商品在售
7. 价格不一致或已下架则淘汰该商品
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


# 京东移动端商品页 UA（模拟真实手机浏览器）
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

PAGE_TIMEOUT = 20000       # 单页加载超时（毫秒）
WAIT_AFTER_LOAD = 8000     # 等待 JS 渲染（毫秒）
REQUEST_DELAY = 1200       # 请求间隔（毫秒），避免被封
PRICE_TOLERANCE = 0.15     # 价格容差（元）

# Cookie 文件路径
COOKIE_FILE = Path(__file__).resolve().parent.parent / "data" / "jd_cookies.json"

# 持久化浏览器配置目录
BROWSER_PROFILE_DIR = Path(__file__).resolve().parent.parent / ".browser_profile"

# Cookie 有效性检查（pin 是长期登录凭证，有效期可达数年到 2027）
# sdtoken 有效期仅约 30 分钟，过期后 JD 会基于 pin 自动签发新的，所以只检查 pin 即可
def _profile_has_valid_cookies():
    """检查持久化浏览器 profile 中是否有有效的京东登录 cookie（pin 未过期即可）"""
    import sqlite3
    from datetime import datetime, timedelta
    cookies_db = BROWSER_PROFILE_DIR / "Default" / "Cookies"
    if not cookies_db.exists():
        return False
    try:
        conn = sqlite3.connect(str(cookies_db))
        now = datetime.now()
        chrominum_epoch = datetime(1601, 1, 1)
        # 只检查 pin（长期有效，~2年），不检查 sdtoken（仅约 30 分钟，过期内正常现象）
        row = conn.execute(
            "SELECT name, expires_utc, has_expires FROM cookies WHERE host_key LIKE '%jd.com' AND name = 'pin'"
        ).fetchall()
        conn.close()
        if len(row) < 1:
            return False
        for name, exp_utc, has_exp in row:
            if has_exp and exp_utc:
                exp_time = chrominum_epoch + timedelta(microseconds=exp_utc)
                if exp_time < now:
                    return False
        return True
    except Exception:
        return False


def _load_cookies() -> list:
    """从 jd_cookies.json 加载京东登录 cookie"""
    if not COOKIE_FILE.exists():
        return []
    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        cookies = []
        for c in raw:
            expires = c.get("expirationDate") or c.get("expires") or -1
            same_site = c.get("sameSite", "Lax")
            # Convert Chrome extension format to Playwright format
            if same_site == "no_restriction":
                same_site = "None"

            cookies.append({
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".jd.com"),
                "path": c.get("path", "/"),
                "expires": expires,
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "sameSite": same_site,
            })
        return cookies
    except Exception:
        return []


def _save_cookies(cookies: list):
    """保存 cookie 到文件"""
    if not cookies:
        return
    try:
        data = []
        for c in cookies:
            data.append({
                "domain": c.get("domain", ".jd.com"),
                "expirationDate": c.get("expires", -1),
                "hostOnly": True,
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
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  🍪 已保存 {len(data)} 条 cookie 到 {COOKIE_FILE}")
    except Exception as e:
        print(f"  ⚠️ 保存 cookie 失败：{e}")


def _check_login_status(page) -> tuple:
    """
    通过 JS 读取 window._itemInfo 判断页面是否已登录、价格是否可见。
    Returns: (is_logged_in, page_info_dict_or_None)
    """
    result = page.evaluate("""() => {
        const info = window._itemInfo;
        if (!info) return null;

        const pf = info.priceFloor || {};
        const ext = pf.ext || {};
        const commonInfo = info.commonInfo || {};

        // 价格被隐藏的标志：包含 "?"（如 "1?"、"3?"）或 "登录"
        const priceHidden = ext.jdPrice?.includes("?") || commonInfo.priceLoginText === "登录查看价格";
        const urgeLogin = !!commonInfo.urgeLogin;

        return {
            isLogged: !priceHidden && !urgeLogin,
            priceHidden: priceHidden,
            jdPrice: priceHidden ? null : (parseFloat(ext.jdPrice) || null),
            warestatus: info.item?.warestatus || null,
            skuId: info.item?.skuId || info.product?.skuId || null,
        };
    }""")

    if not result:
        return False, None
    return result.get("isLogged", False), result


def _init_browser(browser_type, headless=True):
    """初始化持久化浏览器配置"""
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    context = browser_type.launch_persistent_context(
        user_data_dir=str(BROWSER_PROFILE_DIR),
        headless=headless,
        user_agent=MOBILE_UA,
        viewport={"width": 375, "height": 812},
        locale="zh-CN",
        args=["--no-sandbox"],
    )
    return context


def verify_prices(items, tolerance=0.15):
    """
    批量验价：用 Playwright 打开每个商品的京东移动端页面，
    验证登录状态、商品价格、在售状态。

    Args:
        items: 商品列表，每项需包含 sku_id, price, coupon_price 等字段
        tolerance: 价格容差（元），默认 0.15

    Returns:
        (verified_items, failed_items, log_lines)
    """
    if not items:
        return [], [], []

    verified = []
    failed = []
    logs = []

    sku_to_item = {item["sku_id"]: item for item in items if item.get("sku_id")}
    sku_ids = list(sku_to_item.keys())

    if not sku_ids:
        logs.append("  ⚠️ 无有效 SKU，跳过验价")
        return items, [], logs

    logs.append(f"  🔍 开始验价 {len(sku_ids)} 个商品...")

    # 检查持久化 profile 中是否有有效登录状态
    cookies = []  # 初始化变量，避免 has_login=True 时引用未绑定变量
    has_login = _profile_has_valid_cookies()
    if has_login:
        logs.append(f"  🍪 浏览器 profile 已有登录 cookie，无需重复加载")
    else:
        # fallback: 尝试从 JSON 文件加载
        cookies = _load_cookies()
        if cookies:
            logs.append(f"  🍪 已加载 {len(cookies)} 条京东 cookie（JSON 文件）")
            if any(c['name'] == 'sdtoken' for c in cookies):
                has_login = True
            else:
                logs.append(f"  ⚠️ JSON cookie 缺少 sdtoken，无法登录京东")
                logs.append(f"  💡 运行 python3 scripts/jd_login.py 登录一次，后续自动有效")
        else:
            logs.append(f"  ⚠️ 无 cookie，无法登录京东，跳过验价保留全部")
            logs.append(f"  💡 运行 python3 scripts/jd_login.py 完成首次登录")

    p = sync_playwright().start()
    browser = p.chromium

    try:
        # 使用持久化浏览器配置（cookie 由 Playwright 自动管理）
        context = _init_browser(browser, headless=True)
        page = context.pages[0] if context.pages else context.new_page()

        # 仅在 profile 无 cookie 时从 JSON 加载（作为首次使用的补充）
        if not has_login and cookies:
            # 检查浏览器 profile 中是否已经有 cookie
            existing = context.cookies()
            if len(existing) < len(cookies):
                context.add_cookies(cookies)
                logs.append(f"  📥 已将 JSON cookie 添加到浏览器")

        for idx, sku in enumerate(sku_ids):
            item = sku_to_item[sku]
            title_short = (item.get("title", "")[:20] + "...") if len(item.get("title", "")) > 20 else item.get("title", "")
            api_price = item.get("price", 0)

            try:
                url = f"https://item.m.jd.com/product/{sku}.html"
                page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
                page.wait_for_timeout(WAIT_AFTER_LOAD)

                # 1. 检查登录状态和价格可见性
                is_logged, page_info = _check_login_status(page)

                if not is_logged:
                    reason = "未登录（cookie 缺失 sdtoken/pin）" if not cookies else "页面价格被隐藏（未登录）"
                    logs.append(f"  ⚠️ [{title_short}] {reason}，跳过验价但仍保留")
                    # 标记未真正验价，daily_job.py 用此字段决定 price_verified
                    item["_page_price_checked"] = False
                    verified.append(item)
                    _delay(idx, len(sku_ids))
                    continue

                # 2. 检查商品是否在售（warestatus）
                if page_info.get("warestatus") and page_info["warestatus"] != "1":
                    logs.append(f"  ❌ [{title_short}] 商品已下架")
                    failed.append({"item": item, "reason": "商品已下架"})
                    _delay(idx, len(sku_ids))
                    continue

                # 3. 提取页面价格并与 API 价格比对
                page_price = page_info.get("jdPrice")
                if not page_price:
                    logs.append(f"  ⚠️ [{title_short}] 未获取到页面价格，跳过验价但仍保留")
                    item["_page_price_checked"] = False
                    verified.append(item)
                    _delay(idx, len(sku_ids))
                    continue

                price_diff = abs(page_price - api_price)
                if price_diff > tolerance:
                    logs.append(
                        f"  ❌ [{title_short}] 价格不一致：API ¥{api_price:.2f} "
                        f"(整数{len(str(int(api_price)))}位) vs 页面 ¥{page_price:.2f} "
                        f"(整数{len(str(int(page_price)))}位), 差值 ¥{price_diff:.2f}"
                    )
                    failed.append({
                        "item": item,
                        "reason": f"价格不一致：API ¥{api_price:.2f} vs 页面 ¥{page_price:.2f}",
                    })
                    _delay(idx, len(sku_ids))
                    continue

                logs.append(
                    f"  ✅ [{title_short}] 价格 ¥{api_price:.2f} 验证通过 (页面 ¥{page_price:.2f})"
                )
                item["_page_price_checked"] = True
                verified.append(item)

            except Exception as e:
                logs.append(f"  ⚠️ [{title_short}] 验价异常：{e}，跳过验价但仍保留")
                item["_page_price_checked"] = False
                verified.append(item)

            _delay(idx, len(sku_ids))

        # 保存当前浏览器中的 cookie
        context_cookies = context.cookies()
        if context_cookies:
            _save_cookies(context_cookies)

    finally:
        context.close()
        p.stop()

    logs.append(f"  📊 验价完成：通过 {len(verified)} 条，淘汰 {len(failed)} 条")
    return verified, failed, logs


def _delay(index, total):
    """请求间隔，避免被封"""
    if index < total - 1:
        time.sleep(REQUEST_DELAY / 1000.0)
