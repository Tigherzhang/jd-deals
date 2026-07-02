"""
网页生成模块 - 生成 docs/data.json 和纯文字推送内容
"""
import json
import os
import time
from product_filter import get_category_emoji


def format_item(item):
    """将商品格式化为网页显示的条目

    价格决策逻辑：
    - purchasePrice（京东页面最终到手价）> coupon_price > price
    - 优先用 purchasePrice（含券后价+限时折扣+满减+平台活动）
    - 其次用 coupon_price（券面额抵扣后的价格）
    - 最终统一用 _final_price 字段，确保三界面一致
    """
    price = item.get("price", 0)
    coupon_price = item.get("coupon_price", 0)
    purchase_price = item.get("purchase_price", 0)
    coupon_amt = item.get("coupon_amount", 0)

    # 确定最终展示价格：优先 purchasePrice，其次 coupon_price
    final_price = price
    show_orig = False
    if purchase_price > 0 and purchase_price < price:
        # 有京东页面最终到手价（含所有优惠）
        final_price = purchase_price
        show_orig = price
    elif coupon_price > 0 and coupon_price < price:
        # 有券后价
        final_price = coupon_price
        show_orig = price

    # 折扣百分比（基于页面价 vs 最终价）
    discount_pct = 0
    if show_orig and price > 0:
        discount_pct = round((price - final_price) / price * 100)

    tags = []
    # 券后价标签
    if show_orig and coupon_amt > 0:
        tags.append(f"券后¥{final_price:.0f}")
    # 折扣标签（20% off = 8折）
    if show_orig and discount_pct >= 20:
        actual_discount = round(10 - discount_pct / 10, 1)
        tags.append(f"🔥 {actual_discount}折")
    if show_orig and discount_pct >= 50:
        tags.append("⚡超值")
    if final_price <= 19.9:
        tags.append("💎好价")

    good_rate = item.get("good_rate", 0)
    if good_rate >= 95:
        tags.append(f"👍好评{good_rate:.0f}%")
    elif good_rate >= 90:
        tags.append(f"好评{good_rate:.0f}%")

    sales = item.get("sales_30d", 0)
    if sales >= 10000:
        tags.append(f"📈{int(sales/10000)}万+")
    elif sales >= 1000:
        tags.append(f"销量{int(sales/100)}+")
    elif sales >= 100:
        tags.append("销量100+")

    meta_parts = []
    if good_rate > 0:
        meta_parts.append(f"好评率 {good_rate:.0f}%")
    if sales > 0:
        if sales >= 10000:
            meta_parts.append(f"月销 {sales/10000:.1f}万件")
        else:
            meta_parts.append(f"月销 {int(sales)}件")
    meta = " · ".join(meta_parts)

    emoji = get_category_emoji(item.get("category", "其他"))

    return {
        "emoji": emoji,
        "title": item.get("title", "未知商品"),
        "price": f"{final_price:.2f}",  # 统一2位小数
        "orig_price": f"{show_orig:.1f}" if show_orig else None,
        "tags": tags,
        "meta": meta,
        "link": item.get("link", ""),
        "coupon_link": item.get("coupon_link", ""),
        "category": item.get("category", "其他"),
        "discount_pct": discount_pct,
        "sales_30d": item.get("sales_30d", 0),
        "good_count": item.get("good_count", 0),
        "good_rate": item.get("good_rate", 0),
        # 统一价格字段（前端和后端都用这个）
        "_final_price": final_price,
        # 验价元数据（内部字段，不展示到网页）
        "price_verified": item.get("price_verified", True),
        "verified_at": item.get("verified_at", ""),
    }


def generate_text_promo(items):
    """
    生成微信群分享用的纯文字格式
    🍖 良品铺子 原味肉脯 500g 💰 ¥24.90
    🎫 领券 https://coupon.m.jd.com/xxx
    🛒 商品 https://item.jd.com/xxx.html

    价格统一使用 _final_price（已确定是券后价还是页面价）
    券链接和商品链接都带上，方便手动转链
    """
    lines = []
    lines.append(f"📅 {time.strftime('%Y年%m月%d日')} 京东优惠精选\n")
    for i, item in enumerate(items, 1):
        emoji = item.get("emoji", "📦")
        title = item.get("title", "")
        final_price = item.get("_final_price", item.get("price", 0))
        link = item.get("link", "")
        coupon_link = item.get("coupon_link", "")

        # 统一价格标签
        price_tag = f"💰 ¥{final_price:.2f}"

        line = f"{emoji} {title} {price_tag}"
        lines.append(line)

        # 有券链接就带上
        if coupon_link and item.get("coupon_available", False):
            lines.append(f"🎫 {coupon_link}")
        lines.append(f"🛒 {link}")
        lines.append("")

    lines.append("━━━━━━━━━━━━")
    return "\n".join(lines)


def generate_data(items):
    """生成 data.json 内容"""
    formatted = [format_item(item) for item in items]
    formatted.sort(key=lambda x: x.get("discount_pct", 0), reverse=True)

    # 生成纯文字版
    text_promo = generate_text_promo(formatted)

    data = {
        "update_time": time.strftime("%Y年%m月%d日 %H:%M", time.localtime()),
        "total": len(formatted),
        "items": formatted,
        "text_promo": text_promo,
    }
    return data


def save_data(data, output_dir):
    """保存 data.json 到 docs/ 目录"""
    path = os.path.join(output_dir, "data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[✓] 数据已保存: {path}")
