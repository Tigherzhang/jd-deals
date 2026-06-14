"""
网页生成模块 - 生成 docs/data.json 和纯文字推送内容
"""
import json
import os
import time
from product_filter import get_category_emoji


def format_item(item):
    """将商品格式化为网页显示的条目"""
    orig = item.get("orig_price", 0)
    price = item.get("price", 0)
    coupon_price = item.get("coupon_price", 0)
    # 实际显示价
    display_price = coupon_price if coupon_price > 0 else price

    discount_pct = 0
    if orig > 0 and display_price > 0:
        discount_pct = round((orig - display_price) / orig * 100)

    tags = []
    coupon_amt = item.get("coupon_amount", 0)
    if coupon_amt > 0:
        tags.append(f"🏷 满减{coupon_amt:.0f}元")
    if coupon_price > 0 and coupon_price < price:
        tags.append(f"券后¥{coupon_price:.0f}")
    if discount_pct >= 20:
        tags.append(f"🔥 {discount_pct}折")
    if discount_pct >= 50:
        tags.append("⚡超值")
    if display_price <= 19.9:
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
    orig_price_str = f"{orig:.1f}" if orig > 0 and orig > display_price else None

    return {
        "emoji": emoji,
        "title": item.get("title", "未知商品"),
        "price": f"{display_price:.1f}",
        "orig_price": orig_price_str,
        "tags": tags,
        "meta": meta,
        "link": item.get("link", ""),
        "coupon_link": item.get("coupon_link", "") if item.get("coupon_amount", 0) > 0 else "",
        "category": item.get("category", "其他"),
        "discount_pct": discount_pct,
        # 原始字段用于纯文字格式
        "_raw_price": price,
        "_raw_coupon_price": coupon_price,
        "_raw_coupon_amount": coupon_amt,
    }


def generate_text_promo(items):
    """
    生成微信群分享用的纯文字格式
    🍖 良品铺子 原味肉脯 500g 💰 ¥24.9
    🛒 https://item.jd.com/xxx.html
    """
    lines = []
    lines.append(f"📅 {time.strftime('%Y年%m月%d日')} 京东优惠精选\n")
    for i, item in enumerate(items, 1):
        emoji = item.get("emoji", "📦")
        title = item.get("title", "")
        price = item.get("price", "0")
        link = item.get("link", "")
        coupon_link = item.get("coupon_link", "")

        # 价格标签
        price_tag = f"💰 ¥{price}"
        if item.get("_raw_coupon_amount", 0) > 0:
            price_tag += f"（券后价）"

        line = f"{emoji} {title} {price_tag}"
        lines.append(line)

        if coupon_link:
            lines.append(f"🎫 领券：{coupon_link}")
        lines.append(f"🛒 {link}")
        lines.append("")

    lines.append("━━━━━━━━━━━━")
    lines.append("🔔 价格以京东实际为准 · 每日更新")
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
