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
    1. 排除小众/工业品类（甲醛检测仪、活性炭等）/药品/医疗器械
    2. 销量：食品300+，其他500+ | 好评90%+ | 评价数：食品100+，其他200+
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

        # 月销量（食品放宽到300+，其他500+）
        sales = item.get("sales_30d", 0)
        min_sales = 300 if item.get("category") == "食品" else 500
        if sales < min_sales:
            continue

        # 评价数（食品放宽到100+，其他200+）
        good_count = item.get("good_count", 0)
        min_comments = 100 if item.get("category") == "食品" else 200
        if good_count < min_comments:
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

    # 去重（按标题相似度，避免同款变体）
    import re
    title_groups = {}
    for item in unique:
        # 提取核心标题：去掉括号内的变体描述
        base = re.sub(r'[（(【\<].*', '', item.get("title", ""))
        base = base.strip()[:30]  # 前30字作为分组键
        if base not in title_groups:
            title_groups[base] = item
        else:
            # 保留销量更高或价格更低的
            existing = title_groups[base]
            if item.get("sales_30d", 0) > existing.get("sales_30d", 0):
                title_groups[base] = item
            elif item.get("price", 0) < existing.get("price", 0):
                title_groups[base] = item

    return list(title_groups.values())


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

    # 品类偏好（10%）：食品/日用品 >> 化妆品/母婴/保健品 > 计生
    cat = item.get("category", "")
    if cat in ("食品", "日用品"):
        score += 10
    elif cat in ("化妆品", "母婴", "保健品"):
        score += 5
    elif cat == "计生用品":
        score += 2

    # 佣金比例（10%）
    ratio = item.get("commission_ratio", 0)
    if ratio > 0:
        score += min(ratio / 30, 1) * 10

    return score


def rank_and_select(items, max_items=20):
    """
    排序并选取前N条，保证品类多样性
    食品+日用品优先（75%），化妆品/保健品/母婴/计生作为补充
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

    # === 第一轮：优先填充食品和日用品 ===
    primary_cats = ["食品", "日用品"]
    primary_target = int(max_items * 0.8)  # 目标80%给食品+日用品

    for item in real_deals:
        if len(selected) >= primary_target:
            break
        if item.get("category") in primary_cats and item not in selected:
            selected.append(item)

    # 食品和日用品各至少占一定比例
    food_count = sum(1 for i in selected if i.get("category") == "食品")
    home_count = sum(1 for i in selected if i.get("category") == "日用品")

    # === 第二轮：补充辅助品类（化妆品/母婴/保健品/计生）===
    secondary_cats = ["化妆品", "母婴", "保健品", "计生用品"]
    secondary_limit = int(max_items * 0.25)  # 辅助品类最多25%
    secondary_count = 0

    for item in real_deals:
        if len(selected) >= max_items:
            break
        if item.get("category") in secondary_cats and item not in selected:
            if secondary_count < secondary_limit or len(selected) < max_items:
                selected.append(item)
                secondary_count += 1

    # === 第三轮：如果还不够，用高分商品补齐 ===
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
