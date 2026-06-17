"""
京东商品抓取模块 - Scrapling 封装
提供通过 Scrapling CLI 请求京东页面的能力

当前状态：预留接口，尚未启用
原因：京东 CFE 风控不可绕过（stealth-fetch 和 urllib 均被拦截）
未来：当 Scrapling 支持自定义 UA/headers/cookie 时启用
"""
import subprocess
import os
import re
import time


def get_scrapling_path():
    """获取 Scrapling CLI 路径"""
    # 优先使用 pipx 安装的 scrapling
    path = os.path.expanduser("~/.local/bin/scrapling")
    if os.path.exists(path):
        return path
    # fallback: PATH 中查找
    return "scrapling"


def fetch_page(url: str, use_stealth: bool = False) -> str | None:
    """
    抓取页面 HTML 内容

    Args:
        url: 目标 URL
        use_stealth: 是否使用 stealth-fetch（绕过反爬）

    Returns:
        HTML 字符串，失败返回 None
    """
    scraper = get_scrapling_path()
    cmd = [
        scraper, "extract",
        "stealth-fetch" if use_stealth else "fetch" if not use_stealth else "stealth-fetch",
        url, "/tmp/jd-fetch-temp.html",
        "--disable-resources",
        "--timeout", "30000",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode == 0 and os.path.exists("/tmp/jd-fetch-temp.html"):
            with open("/tmp/jd-fetch-temp.html", "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def verify_with_scrapling(sku: str, use_stealth: bool = True) -> bool | None:
    """
    用 Scrapling 验证商品是否在售

    Args:
        sku: 商品 SKU ID
        use_stealth: 是否使用 stealth 模式

    Returns:
        True=在售, False=已下架, None=不确定(风控/网络异常)
    """
    url = f"https://item.m.jd.com/product/{sku}.html"
    html = fetch_page(url, use_stealth=use_stealth)

    if html is None:
        return None

    # 京东风控页面
    if "京东验证" in html[:2000] or "risk_handler" in html:
        return None

    # 已下架信号
    if "该商品已下架" in html or 'errCode:"20160304"' in html:
        return False

    # 在售信号
    if "warestatus" in html:
        return True

    return True


def fetch_prices_with_scrapling(sku_ids: list[str]) -> dict[str, float]:
    """
    用 Scrapling 抓取商品页提取实时价格（替代 p.3.cn）

    Args:
        sku_ids: SKU ID 列表

    Returns:
        {sku_id: price} 字典，失败返回空
    """
    result = {}
    for sku in sku_ids[:5]:  # 每次最多查5个
        url = f"https://item.m.jd.com/product/{sku}.html"
        html = fetch_page(url, use_stealth=True)
        if html is None:
            continue

        # 从京东商品页的 JS 数据中提取 price
        price_match = re.search(r'"price"\s*:\s*"([^"]+)"', html)
        if price_match:
            try:
                result[sku] = float(price_match.group(1))
            except ValueError:
                pass

        time.sleep(0.5)

    return result
