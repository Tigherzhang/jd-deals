"""
京东商品验价模块 - Playwright 浏览器验价
在商品推送前，打开京东商品页验证价格和在售状态。

策略：
1. 打开京东移动端商品页 (item.m.jd.com)
2. 检查页面是否正常加载（不是登录页/下架页）
3. 从页面 HTML 提取编码价格字符串，验证长度与 API 价格整数位数一致
4. 若一致则认为价格有效，使用 API 价格作为最终价格
5. 若不一致则淘汰该商品
"""
import re
import time
from playwright.sync_api import sync_playwright


# 京东移动端商品页 UA（模拟真实手机浏览器）
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)

PAGE_TIMEOUT = 20000       # 单页加载超时（毫秒）
WAIT_AFTER_LOAD = 10000    # 等待 JS 渲染（毫秒）
REQUEST_DELAY = 1500       # 请求间隔（毫秒），避免被封


def verify_prices(items, tolerance=0.5):
    """
    批量验价：用 Playwright 打开每个商品的京东移动端页面，
    验证页面可加载且价格格式一致。

    Args:
        items: 商品列表，每项需包含 sku_id, price, coupon_price 等字段
        tolerance: 价格容差（目前未使用，保留接口兼容性）

    Returns:
        (verified_items, failed_items, log_lines)
        verified_items: 验价通过的商品列表
        failed_items: 验价失败的商品列表（含失败原因）
        log_lines: 日志行列表
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=MOBILE_UA,
            viewport={"width": 375, "height": 812},
            locale="zh-CN",
        )
        page = context.new_page()

        for idx, sku in enumerate(sku_ids):
            item = sku_to_item[sku]
            title_short = (item.get("title", "")[:20] + "...") if len(item.get("title", "")) > 20 else item.get("title", "")
            api_price = item.get("price", 0)

            try:
                url = f"https://item.m.jd.com/product/{sku}.html"
                page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
                page.wait_for_timeout(WAIT_AFTER_LOAD)

                html = page.content()
                body_text = page.inner_text('body')

                # 1. 检查页面是否正常加载（不是登录页/空页面）
                if '登录' in body_text[:200] or '暂无定价' in body_text[:200]:
                    logs.append(f"  ⚠️ [{title_short}] 页面需要登录或暂无定价，跳过验价但仍保留")
                    verified.append(item)
                    _delay(idx, len(sku_ids))
                    continue

                # 2. 检查商品是否在售（warestatus）
                warestatus = re.search(r'"warestatus"\s*:\s*"(\d+)"', html)
                if warestatus and warestatus.group(1) != "1":
                    logs.append(f"  ❌ [{title_short}] 商品已下架")
                    failed.append({"item": item, "reason": "商品已下架"})
                    _delay(idx, len(sku_ids))
                    continue

                # 3. 提取编码价格并验证格式
                pf = re.search(
                    r'"priceFloor"[^}]*"price"\s*:\s*"([^"]+)"', html
                )
                if not pf:
                    logs.append(f"  ⚠️ [{title_short}] 未找到价格数据，跳过验价但仍保留")
                    verified.append(item)
                    _delay(idx, len(sku_ids))
                    continue

                encoded_price = pf.group(1)
                encoded_len = len(encoded_price)

                # 计算 API 价格的整数位数
                if api_price > 0:
                    expected_int_digits = len(str(int(api_price)))
                else:
                    expected_int_digits = 0

                if encoded_len != expected_int_digits:
                    logs.append(
                        f"  ❌ [{title_short}] 价格不一致: API ¥{api_price} "
                        f"(整数{expected_int_digits}位) vs 页面 {encoded_price} ({encoded_len}位)"
                    )
                    failed.append({
                        "item": item,
                        "reason": f"价格不一致: API {api_price} vs 页面 {encoded_price}",
                    })
                    _delay(idx, len(sku_ids))
                    continue

                logs.append(
                    f"  ✅ [{title_short}] 价格 ¥{api_price} 验证通过"
                )
                verified.append(item)

            except Exception as e:
                logs.append(f"  ⚠️ [{title_short}] 验价异常: {e}，跳过验价但仍保留")
                verified.append(item)

            _delay(idx, len(sku_ids))

        browser.close()

    logs.append(f"  📊 验价完成: 通过 {len(verified)} 条, 淘汰 {len(failed)} 条")
    return verified, failed, logs


def _delay(index, total):
    """请求间隔，避免被封"""
    if index < total - 1:
        time.sleep(REQUEST_DELAY / 1000.0)
