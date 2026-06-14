"""
商品筛选与排序逻辑
"""
import json
import os
import random

HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "history.json")


def load_history():
    """加载历史推送记录"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"sku_ids": [], "dates": {}}


def save_history(history):
    """保存历史推送记录"""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except:
        pass


def filter_products(items, config):
    """
    筛选商品
    规则：
    1. 价格在 min_price ~ max_price 区间（优先10-100元）
    2. 排除已推过的商品（去重）
    3. 排除无优惠的（原价与现价差不多的）
    4. 优先好评率高的
    """
    min_price = config.get("min_price", 10)
    max_price = config.get("max_price", 100)
    price_upper = config.get("price_upper_limit", 500)

    history = load_history()
    pushed_ids = set(history.get("sku_ids", []))

    filtered = []
    for item in items:
        if not item:
            continue

        price = item.get("price", 0)
        sku_id = item.get("sku_id", "")

        # 价格过滤
        if price < min_price:
            continue
        if price > price_upper:
            continue

        # 去重
        if sku_id in pushed_ids:
            continue

        # 必须有原价且折扣>10%
        orig = item.get("orig_price", 0)
        if orig > 0 and price > 0:
            discount = (orig - price) / orig
            if discount < 0.05:  # 折扣小于5%的不收录
                continue

        # 好评率过滤（宽松处理，因为API不一定都返回）
        good_rate = item.get("good_rate", 0)
        if good_rate > 0 and good_rate < 80:  # 有评价但低于80%的排除
            continue

        # 销量过滤
        sales = item.get("sales_30d", 0)
        if sales > 0 and sales < 10:
            continue

        filtered.append(item)

    # 去重（按sku_id）
    seen = set()
    unique = []
    for item in filtered:
        sid = item.get("sku_id", "")
        if sid not in seen:
            seen.add(sid)
            unique.append(item)

    return unique


def score_product(item):
    """
    综合评分
    高分 = 折扣大 + 佣金高 + 好评好 + 销量高
    """
    score = 0

    # 折扣力度（40%权重）
    orig = item.get("orig_price", 0)
    price = item.get("price", 0)
    if orig > 0 and price > 0:
        discount = (orig - price) / orig
        score += discount * 40

    # 佣金比例（20%权重）
    ratio = item.get("commission_ratio", 0)
    if ratio > 0:
        score += min(ratio / 30, 1) * 20  # 佣金比例通常1-30%

    # 好评率（20%权重）
    good_rate = item.get("good_rate", 90)
    score += (good_rate / 100) * 20

    # 销量（20%权重）
    sales = item.get("sales_30d", 0)
    if sales > 0:
        # 销量分级：100+ = 10分, 1000+ = 15分, 10000+ = 20分
        if sales >= 10000:
            score += 20
        elif sales >= 1000:
            score += 15
        elif sales >= 100:
            score += 10
        else:
            score += (sales / 100) * 10
    else:
        score += 5  # 无销量数据给基础分

    # 优惠券加分
    if item.get("coupon_amount", 0) > 0:
        score += 5

    # 品类偏好：食品、日用品加一点分
    cat = item.get("category", "")
    if cat in ("食品", "水果/生鲜", "日用品"):
        score += 3

    return score


def rank_and_select(items, max_items=10):
    """
    排序并选取前N条
    保证品类多样性：至少包含食品、日用品等不同品类
    """
    if not items:
        return []

    # 计算评分
    for item in items:
        item["_score"] = score_product(item)

    # 按评分降序
    items.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # Filter: only items with real discount (coupon_amount > 0 or price < orig_price)
    real_deals = []
    for item in items:
        has_coupon = item.get("coupon_amount", 0) > 0
        has_discount = item.get("orig_price", 0) > item.get("price", 0)
        if has_coupon or has_discount:
            real_deals.append(item)

    # 品类多样性：同一品类最多3条
    cat_count = {}
    selected = []

    # First pass: pick 3 food, 3 home items
    for cat in ["食品", "日用品"]:
        cnt = 0
        for item in real_deals:
            if item.get("category") == cat and item not in selected:
                selected.append(item)
                cnt += 1
                if cnt >= 3:
                    break
        cat_count[cat] = cnt

    # Second pass: fill remaining slots from all categories
    for item in real_deals:
        if len(selected) >= max_items:
            break
        if item in selected:
            continue
        cat = item.get("category", "其他")
        if cat_count.get(cat, 0) >= 3:
            continue
        selected.append(item)
        cat_count[cat] = cat_count.get(cat, 0) + 1

    # 移除评分字段
    for item in selected:
        item.pop("_score", None)

    return selected


def get_category_emoji(category):
    """根据品类返回对应emoji"""
    mapping = {
        "食品": "🍖",
        "水果/生鲜": "🍊",
        "日用品": "🧴",
        "饮料": "🥤",
        "零食": "🍪",
        "粮油": "🍚",
        "其他": "📦",
    }
    return mapping.get(category, "📦")
