"""
商品筛选与排序逻辑
"""
import json
import os
import random
import re
from difflib import SequenceMatcher

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
    5. 仅排除最近 7 天内出现过的商品（而非永久去重）
    """
    min_price = config.get("min_price", 10)
    max_price = config.get("max_price", 100)
    price_upper = config.get("price_upper_limit", 500)

    history = load_history()
    all_skus = history.get("sku_ids", [])
    # 只取最近140条（约7天×20条），确保7天内不重复
    recent_skus = all_skus[-140:]
    pushed_ids = set(recent_skus)
    print(f"    历史 SKU: {len(all_skus)} 个，最近去重池: {len(pushed_ids)} 个")

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
        # 标题相似度去重（防止ID格式不一致导致漏判）
        # 清理标题：去掉方括号/括号内容、空格
        title_clean = re.sub(r'[【\[（\(\<].*?([】\)\)>]|$)', '', item.get("title", "")).strip()
        title_clean = re.sub(r'\s+', '', title_clean)
        hist_titles = history.get("titles", [])
        is_dup = False
        for hist_title in hist_titles:
            hist_clean = re.sub(r'[【\[（\(\<].*?([】\)\)>]|$)', '', hist_title).strip()
            hist_clean = re.sub(r'\s+', '', hist_clean)
            sim = SequenceMatcher(None, title_clean, hist_clean).ratio()
            if sim > 0.90:
                is_dup = True
                break
        if is_dup:
            continue

        # 折扣检查仅在 origin > price 时才做（现在 orig_price = price 默认无折扣）
        orig = item.get("orig_price", 0)
        if orig > 0 and price > 0 and orig > price:
            discount = (orig - price) / orig
            if discount < 0.05:
                continue

        # 好评率90%+
        good_rate = item.get("good_rate", 0)
        if good_rate > 0 and good_rate < 90:
            continue
        if good_rate == 0:
            continue  # 无好评数据的跳过

        # 月销量（食品放宽到100+，其他300+）
        sales = item.get("sales_30d", 0)
        min_sales = 100 if item.get("category") == "食品" else 300
        if sales < min_sales:
            continue

        # 评价数（食品放宽到50+，其他100+）
        good_count = item.get("good_count", 0)
        min_comments = 50 if item.get("category") == "食品" else 100
        if good_count < min_comments:
            continue

        filtered.append(item)

    # 去重（按 SKU ID，跳过空 SKU）
    seen_skus = set()
    unique = []
    for item in filtered:
        sid = item.get("sku_id", "")
        if not sid or sid in seen_skus:
            continue
        seen_skus.add(sid)
        unique.append(item)

    # 去重（按 jingfen materialUrl 链接，同一链接只取一个）
    seen_links = set()
    unique2 = []
    for item in unique:
        link = item.get("link", "")
        if not link:
            unique2.append(item)
            continue
        # 标准化链接：去掉协议和尾参数
        normalized = link.replace("https://", "").replace("http://", "").split("?")[0].split("#")[0]
        if normalized not in seen_links:
            seen_links.add(normalized)
            unique2.append(item)
    unique = unique2

    # ====== 去重第1步：按"品牌+核心品类"分组 ======
    def _extract_brand_core(title):
        """从标题中提取品牌名+核心品类词，用于同款去重"""
        # 1. 去掉【】方括号内容（如【山姆同款】、【最强组合】）
        base = re.sub(r'【[^】]*】', '', title)
        # 2. 去掉（）括号内容
        base = re.sub(r'[（(][^）)]*[）)]', '', base)
        # 3. 去掉空格
        base = re.sub(r'\s+', '', base)
        # 4. 提取"品牌词+核心品类词"
        #    匹配：英文品牌 + 任意中间内容 + 品类词，非贪婪
        kw_match = re.match(
            r'([A-Za-z\'\-]+).*?'
            r'(牙刷|牙膏|沐浴|洗发|洗衣|毛巾|浴巾|纸巾|抽纸|手套|衣架|'
            r'拖把|扫把|垃圾袋|保鲜|香皂|肥皂|洗手|洗脸|面巾|湿巾|'
            r'驱蚊|灭蚊|消毒|马桶|下水|挂钩|收纳|遮阳|雨伞|保温杯|'
            r'水杯|锅|刀|砧板|碗|筷|饭盒|口罩)',
            base, re.IGNORECASE
        )
        if kw_match:
            return f"{kw_match.group(1).lower()}{kw_match.group(2)}"
        # 纯中文品牌：取前25字
        return base.strip()[:25]

    brand_groups = {}
    for item in unique:
        core = _extract_brand_core(item.get("title", ""))
        if core not in brand_groups:
            brand_groups[core] = item
        else:
            # 保留销量更高或价格更低的
            existing = brand_groups[core]
            existing_sales = existing.get("sales_30d", 0)
            new_sales = item.get("sales_30d", 0)
            if new_sales > existing_sales or (new_sales == existing_sales and item.get("price", 0) < existing.get("price", 0)):
                print(f"  🔄 品牌去重: {item['title'][:25]}... (替换销量{existing_sales}->{new_sales})")
                brand_groups[core] = item

    unique2 = list(brand_groups.values())

    # ====== 品牌词分组兜底：不同分组键但标题相似 + 价格相同 → 同款 ======
    def _clean_title(title):
        base = re.sub(r'[（(【\<].*', '', title)
        base = re.sub(r'\s+', '', base)
        return base.strip()

    if not unique2:
        return []

    deduped3 = [unique2[0]]
    for item in unique2[1:]:
        ct = _clean_title(item.get("title", ""))
        is_dup = False
        for idx, existing in enumerate(deduped3):
            ec = _clean_title(existing.get("title", ""))
            sim = SequenceMatcher(None, ct, ec).ratio()
            # 同款判断：a) 标题相似+价格相同(0.70) 或 b) 标题高度相似(0.75)
            is_same_price = abs(item.get("price", 0) - existing.get("price", 0)) < 0.01
            if (sim > 0.70 and is_same_price) or sim > 0.75:
                existing_sales = existing.get("sales_30d", 0)
                new_sales = item.get("sales_30d", 0)
                if new_sales > existing_sales or (new_sales == existing_sales and item.get("price", 0) < existing.get("price", 0)):
                    deduped3[idx] = item
                    print(f"  🔄 相似去重: {item['title'][:25]}... (替换销量{existing_sales}->{new_sales})")
                is_dup = True
                break
        if not is_dup:
            deduped3.append(item)

    # 按评分排序（有_score的用评分，没有的用标题相似度保留顺序）
    deduped3.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # ====== 品牌重复检测：同一品牌出现超过2次 → 只保留2个 ======
    # 从标题中提取品牌名（支持中英文品牌）
    def _extract_brand(title):
        # 先试英文品牌：开头的大写字母+连字符
        bm = re.match(r'^([A-Z][A-Za-z\-]+)', title)
        if bm:
            return bm.group(1).lower()
        # 再试中文品牌：标题开头的中文词（2-4个字），后面跟空格或非中文字符
        bm2 = re.match(r'^([一-龥]{2,4})(?:\s|·|【|（|\.|$)', title)
        if bm2:
            return bm2.group(1)
        # 兜底：取前3个中文字
        bm3 = re.match(r'([一-龥]{3})', title)
        if bm3:
            return bm3.group(1)
        return title[:5]

    brand_groups = {}
    for d in deduped3:
        brand = _extract_brand(d.get("title", ""))
        if brand not in brand_groups:
            brand_groups[brand] = []
        brand_groups[brand].append(d)

    final = []
    for brand, items in brand_groups.items():
        if len(items) <= 2:
            final.extend(items)
        else:
            # 超过2个，只保留前2个（已在 filter 阶段排过序，取前面的）
            final.extend(items[:2])
            for extra in items[2:]:
                print(f"  🚫 品牌去重: {extra['title'][:25]}... (品牌 '{brand}' 出现过多，保留前2个)")

    return final


def score_product(item):
    """
    综合评分（满分100）
    折扣30% + 好评15% + 销量15% + 品类30% + 佣金10%
    品类权重大幅提升：食品/日用品优先
    """
    score = 0

    # 折扣力度（30%）
    orig = item.get("orig_price", 0)
    price = item.get("price", 0)
    if orig > 0 and price > 0:
        discount = (orig - price) / orig
        score += discount * 30

    # 好评率（15%）
    good_rate = item.get("good_rate", 90)
    score += (good_rate / 100) * 15

    # 销量（15%）
    sales = item.get("sales_30d", 0)
    if sales >= 50000:
        score += 15
    elif sales >= 10000:
        score += 12
    elif sales >= 5000:
        score += 9
    elif sales >= 1000:
        score += 6

    # 品类偏好（30%）：食品/日用品大幅加权，其他品类降低
    cat = item.get("category", "")
    if cat == "食品":
        score += 30
    elif cat == "日用品":
        score += 25
    elif cat == "水果":
        score += 28
    elif cat == "化妆品":
        score += 5
    elif cat == "母婴":
        score += 5
    elif cat == "保健品":
        score += 3
    elif cat == "计生用品":
        score += 2

    # 佣金比例（10%）
    ratio = item.get("commission_ratio", 0)
    if ratio > 0:
        score += min(ratio / 30, 1) * 10

    # 有优惠券优先（10%）：一键领券 → 领完跳转商品页，转化最好
    if item.get("coupon_amount", 0) > 0 and item.get("coupon_available", False):
        score += 10
    elif item.get("coupon_amount", 0) > 0:
        score += 5

    return score


def rank_and_select(items, max_items=10, min_items=8):
    """
    排序并选取前N条，优先食品和日用品
    食品和日用品目标占比≥50%，总条数10条
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

    # 如果真有优惠的商品不足 min_items，从所有 score 高的 items 中取
    if len(real_deals) < min_items:
        print(f"  ⚠️ 真正有优惠的仅 {len(real_deals)} 条，降级从所有商品中取")
        real_deals = items.copy()

    selected = []

    # === 第一轮：优先填充食品/水果/日用品（目标70%） ===
    primary_cats = ["食品", "水果", "日用品"]
    primary_target = int(max_items * 0.7)

    for item in real_deals:
        if len(selected) >= primary_target:
            break
        if item.get("category") in primary_cats and item not in selected:
            selected.append(item)

    # 食品和日用品各至少占一定比例
    food_count = sum(1 for i in selected if i.get("category") == "食品")
    home_count = sum(1 for i in selected if i.get("category") == "日用品")

    # === 第二轮：补充辅助品类（化妆品/母婴/保健品/计生），最多30% ===
    secondary_cats = ["化妆品", "母婴", "保健品", "计生用品"]
    secondary_limit = max(int(max_items * 0.3), 1)  # 辅助品类最多30%

    secondary_count = 0
    for item in real_deals:
        if len(selected) >= max_items:
            break
        if item.get("category") in secondary_cats and item not in selected:
            if secondary_count < secondary_limit:
                selected.append(item)
                secondary_count += 1

    # === 第三轮：如果还不够 max_items，用高分商品补齐 ===
    for item in real_deals:
        if len(selected) >= max_items:
            break
        if item not in selected:
            selected.append(item)

    # 如果连 min_items 都凑不满，接受更少
    if len(selected) < min_items:
        print(f"  ⚠️ 最终仅选出 {len(selected)} 条商品（不足 {max_items} 条）")

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
