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
    1. 排除小众/工业品类（甲醛检测仪、活性炭等）
    2. 销量1000+，好评90%+，评价数500+
    3. 价格在 min_price ~ max_price 区间
    4. 折扣至少5%
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

        # 排除小众品类/药品/医疗器械
        if item.get("excluded", False):
            continue

        # 排除无法归类到六大品类的商品
        if item.get("category", "") == "其他":
            continue

        price = item.get("price", 0)
        sku_id = item.get("sku_id", "")

        # 价格过滤：不低于min_price，不高于上限
        if price < min_price:
            continue
        if price > price_upper:
            continue

        # 去重：不推已推过的商品
        if sku_id in pushed_ids:
            continue

        # 折扣至少5%
        orig = item.get("orig_price", 0)
        if orig > 0 and price > 0:
            discount = (orig - price) / orig
            if discount < 0.05:
                continue

        # 好评率90%+
        good_rate = item.get("good_rate", 0)
        if good_rate > 0 and good_rate < 90:
            continue
        if good_rate == 0:
            continue  # 无好评数据的跳过

        # 月销量1000+
        sales = item.get("sales_30d", 0)
        if sales < 1000:
            continue

        # 评价数500+
        good_count = item.get("good_count", 0)
        if good_count < 500:
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
    综合评分（满分100）
    折扣40% + 好评20% + 销量20% + 品类10% + 佣金10%
    """
    score = 0

    # 折扣力度（40%）
    orig = item.get("orig_price", 0)
    price = item.get("price", 0)
    if orig > 0 and price > 0:
        discount = (orig - price) / orig
        score += discount * 40

    # 好评率（20%）
    good_rate = item.get("good_rate", 90)
    score += (good_rate / 100) * 20

    # 销量（20%）
    sales = item.get("sales_30d", 0)
    if sales >= 50000:
        score += 20
    elif sales >= 10000:
        score += 16
    elif sales >= 5000:
        score += 12
    elif sales >= 1000:
        score += 8

    # 品类偏好（10%）：食品/日用品 > 化妆品/母婴/保健品 > 计生
    cat = item.get("category", "")
    if cat in ("食品", "日用品"):
        score += 10
    elif cat in ("化妆品", "母婴", "保健品"):
        score += 7
    elif cat == "计生用品":
        score += 4

    # 佣金比例（10%）
    ratio = item.get("commission_ratio", 0)
    if ratio > 0:
        score += min(ratio / 30, 1) * 10

    return score


def rank_and_select(items, max_items=20):
    """
    排序并选取前N条，保证品类多样性
    食品占40%、日用品占30%、其他品类占30%
    """
    if not items:
        return []

    # 计算评分
    for item in items:
        item["_score"] = score_product(item)

    # 按评分降序
    items.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # 必须真的有优惠
    real_deals = [i for i in items if i.get("orig_price", 0) > i.get("price", 0)]

    selected = []
    cat_quota = {
        "食品": int(max_items * 0.40),      # 8条
        "日用品": int(max_items * 0.30),    # 6条
        "化妆品": int(max_items * 0.10),    # 2条
        "母婴": int(max_items * 0.08),      # 2条
        "保健品": int(max_items * 0.07),    # 1条
        "计生用品": int(max_items * 0.05),  # 1条
    }

    # 按配额选取
    for cat, quota in cat_quota.items():
        cnt = 0
        for item in real_deals:
            if item.get("category") == cat and item not in selected:
                selected.append(item)
                cnt += 1
                if cnt >= quota:
                    break

    # 如果某些品类不足，用高分商品补齐
    remaining = max_items - len(selected)
    for item in real_deals:
        if len(selected) >= max_items:
            break
        if item not in selected:
            selected.append(item)

    # 移除评分字段
    for item in selected:
        item.pop("_score", None)

    return selected


def get_category_emoji(category):
    """根据品类返回对应emoji"""
    mapping = {
        "食品": "🍖",
        "日用品": "🧴",
        "化妆品": "💄",
        "保健品": "💊",
        "母婴": "👶",
        "计生用品": "🔞",
    }
    return mapping.get(category, "📦")
