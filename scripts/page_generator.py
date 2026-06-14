"""
网页生成模块 - 生成 docs/data.json
"""
import json
import os
import time
from product_filter import get_category_emoji


def format_item(item):
    """将商品格式化为网页显示的条目"""
    # 计算折扣
    orig = item.get("orig_price", 0)
    price = item.get("price", 0)
    discount_pct = 0
    if orig > 0 and price > 0:
        discount_pct = round((orig - price) / orig * 100)

    # 构建标签列表
    tags = []

    # 优惠券
    coupon_amt = item.get("coupon_amount", 0)
    if coupon_amt > 0:
        tags.append(f"🏷 满减{coupon_amt:.0f}元")

    # 折扣标签
    if discount_pct >= 10:
        tags.append(f"🔥 {discount_pct}折")
    if discount_pct >= 50:
        tags.append("⚡超值")

    # 9.9包邮
    if price <= 9.9:
        tags.append("✨9.9包邮")
    elif price <= 19.9:
        tags.append("💎好价")

    # 好评率
    good_rate = item.get("good_rate", 0)
    if good_rate >= 95:
        tags.append(f"👍好评{good_rate:.0f}%")
    elif good_rate >= 90:
        tags.append(f"好评{good_rate:.0f}%")

    # 销量
    sales = item.get("sales_30d", 0)
    if sales >= 10000:
        tags.append(f"📈{int(sales/10000)}万+")
    elif sales >= 1000:
        tags.append(f"销量{int(sales/100)}+")
    elif sales >= 100:
        tags.append("销量100+")

    # 元信息
    meta = ""
    meta_parts = []
    if good_rate > 0:
        meta_parts.append(f"好评率 {good_rate:.0f}%")
    if sales > 0:
        if sales >= 10000:
            meta_parts.append(f"月销 {sales/10000:.1f}万件")
        else:
            meta_parts.append(f"月销 {int(sales)}件")
    if item.get("commission_ratio", 0) > 0:
        meta_parts.append(f"佣金 {item['commission_ratio']:.1f}%")
    meta = " · ".join(meta_parts)

    emoji = get_category_emoji(item.get("category", "其他"))

    # 价格显示：原价如果是0就不显示
    orig_price_str = f"{orig:.1f}" if orig > 0 and orig > price else None

    return {
        "emoji": emoji,
        "title": item.get("title", "未知商品"),
        "price": f"{price:.1f}",
        "orig_price": orig_price_str,
        "tags": tags,
        "meta": meta,
        "link": item.get("link", ""),
        "coupon_link": item.get("coupon_link", "") if item.get("coupon_amount", 0) > 0 else "",
        "category": item.get("category", "其他"),
        "discount_pct": discount_pct,
    }


def generate_data(items):
    """生成 data.json 内容"""
    formatted = [format_item(item) for item in items]

    # 按折扣降序排列
    formatted.sort(key=lambda x: x.get("discount_pct", 0), reverse=True)

    data = {
        "update_time": time.strftime("%Y年%m月%d日 %H:%M", time.localtime()),
        "total": len(formatted),
        "items": formatted,
    }
    return data


def save_data(data, output_dir):
    """保存 data.json 到 docs/ 目录"""
    path = os.path.join(output_dir, "data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[✓] 数据已保存: {path}")
