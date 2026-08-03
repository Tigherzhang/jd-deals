"""
商品筛选与排序逻辑
"""
import json
import os
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


def _extract_brand(title):
    """从标题中提取品牌名"""
    bm = re.match(r'^([A-Z][A-Za-z\-]+)', title)
    if bm:
        return bm.group(1).lower()
    bm2 = re.match(r'^([一-鿿]{2,3})(?:\s|·|【|（|\.|-|\/|$)', title)
    if bm2:
        return bm2.group(1)
    bm3 = re.match(r'([一-鿿]{2})', title)
    if bm3:
        return bm3.group(1)
    return title[:5]


# ============================================================
# 去重核心：按品类分组，只在该品类的关键词中匹配商品类型
# ============================================================
# 规则：每个品类独立维护自己的关键词列表，只在该品类范围内匹配
# 去掉单字关键词（"鱼"、"虾"、"蟹"太宽泛），保留双字及以上
# 去除了重复项

_PRODUCT_KEYWORDS_BY_CAT = {
    # --- 日用品 ---
    "日用品": [
        "沐浴露", "沐浴液", "洗发水", "洗发露", "护发素", "洗衣液", "洗衣粉",
        "洗手液", "洗洁精", "牙刷", "牙膏", "牙线", "漱口水", "毛巾", "浴巾",
        "面巾纸", "抽纸", "卷纸", "湿巾", "垃圾袋", "保鲜膜", "保鲜袋",
        "拖把", "扫把", "簸箕", "衣架", "晾衣架", "挂钩", "收纳箱", "收纳盒",
        "棉签", "棉棒", "香皂", "肥皂", "洗面奶", "洁面乳", "保温杯", "水杯",
        "饭盒", "雨伞", "雨衣", "拖鞋", "口罩", "马桶刷", "抹布", "洗碗布",
        "地垫", "脚垫", "地毯", "窗帘", "花盆", "镜子", "锁具", "插座",
        "排插", "插线板", "垃圾桶", "垃圾篓", "密封罐", "置物架", "鞋架",
        "袜子", "内裤", "文胸", "背心", "打底裤", "丝袜", "围巾", "手套",
        "帽子", "领带", "蜡烛", "香薰", "相框", "画框", "摆件", "钟表",
        "挂钟", "闹钟", "日历", "台历", "穿衣镜", "门锁", "吸管杯",
        "儿童水杯", "婴儿湿巾", "宝宝湿巾", "驱蚊手环", "驱蚊贴", "苦甲水",
        "指甲刀", "剃须刀", "剃须泡", "暖手宝", "热水袋", "泡澡桶", "浴缸",
        "沐浴桶", "蚊香", "电蚊拍", "灭蚊灯", "拖把桶", "扫帚", "吸油纸",
        "硅油纸", "烘焙纸", "锡纸", "烤盘", "空气炸锅", "封口机", "真空机",
        "绞肉机", "榨汁机", "破壁机", "电磁炉", "燃气灶", "煤气灶", "灶具",
        "油烟机", "抽油烟机", "水龙头", "水槽", "地漏", "角阀", "软管",
        "身体乳", "护手霜", "洗脸巾", "擦脸巾", "棉柔巾", "眼罩", "蒸汽眼罩",
        "热敷眼罩", "矫姿带", "背背佳", "暖宝宝", "米桶", "储米", "面桶",
        "揉面垫", "擀面垫", "打蛋器", "烘焙工具", "菜刀", "刀具", "切菜",
        "切片刀", "水果刀", "剪刀", "砧板", "案板", "炒锅", "平底锅",
        "煎锅", "不粘锅", "蒸锅", "蒸笼", "叉子", "勺子", "汤匙", "餐具",
        "餐叉", "餐勺", "筷子", "刀叉", "奶油风", "奶油色", "莫兰迪色",
        "ins风", "冰箱", "车载冰箱", "冰柜", "抽水器", "上水器", "饮水机",
        "电动抽水泵", "桶装水", "泡面锅", "辅食锅", "奶锅", "小奶锅", "汤锅",
        "炖锅", "砂锅", "高压锅", "电压力锅", "卫生湿巾", "消毒湿巾",
        "驱蚊扣", "湿巾婴儿", "卫生巾", "安心裤", "安全裤", "护垫",
    ],
    # --- 食品 ---
    "食品": [
        "板栗仁", "火腿肠", "海苔", "甜皮鸭", "卤鸭", "烤鸭", "酱鸭", "牛肉干",
        "牛肉脯", "肉松", "肉脯", "培根", "香肠", "腊肠", "腊肉", "午餐肉",
        "皮蛋", "咸鸭蛋", "卤蛋", "蛋挞", "速冻", "水饺", "饺子", "馄饨",
        "云吞", "汤圆", "元宵", "手抓饼", "火锅丸", "丸子", "鱼丸", "虾丸",
        "牛肉丸", "方便面", "泡面", "自热锅", "自热火锅", "自热米饭",
        "海鲜", "水产", "贝类", "海参", "鲍鱼", "扇贝",
        "牡蛎", "生蚝", "蛏子", "花甲", "蛤蜊", "田螺", "海螺", "章鱼",
        "墨鱼", "鱿鱼", "乌贼", "海马", "海星", "海胆", "海蜇", "海带结",
        "海带丝", "裙带菜", "紫菜", "鱼露", "鱼豆腐", "蟹棒",
        "即食海鲜", "海鲜干货", "海产品", "淡水鱼", "海水鱼", "三文鱼",
        "金枪鱼", "带鱼", "黄花鱼", "鲈鱼", "鲫鱼", "鲤鱼", "罗非鱼",
        "巴沙鱼", "龙利鱼", "鳕鱼", "鲷鱼", "秋刀鱼", "鲭鱼", "沙丁鱼",
        "银鱼", "小鱼干", "虾米", "虾仁", "虾皮", "干贝", "瑶柱",
        "酱油", "生抽", "老抽", "蚝油", "陈醋", "米醋", "白醋", "香醋",
        "豆瓣酱", "黄豆酱", "甜面酱", "辣椒酱", "蒜蓉酱", "沙拉酱",
        "番茄酱", "芝麻酱", "花生酱", "芥末", "黑胡椒", "花椒", "八角",
        "桂皮", "香叶", "孜然", "咖喱", "五香粉", "鸡精", "味精", "冰糖",
        "红糖", "海盐", "岩盐", "芝麻油", "香油", "菜籽油", "稻米油",
        "亚麻籽油", "核桃油", "耗油", "干货", "干菇", "干木耳", "干海带", "干香菇",
        "腐竹", "豆腐皮", "千张", "豆皮", "豆泡", "油豆腐", "素鸡", "豆干",
        "辣条", "魔芋", "蒟蒻", "面筋", "烤麸", "纳豆", "豆豉", "臭豆腐",
        "泡菜", "酸菜", "榨菜", "雪菜", "梅菜", "萝卜干", "橄榄菜", "下饭菜",
        "酱菜", "咸菜", "腌菜", "酸豆角", "藠头", "子姜", "泡椒", "野山椒",
        "酸辣粉", "螺蛳粉", "鲜虾片",
        "茶叶", "绿茶", "红茶", "乌龙茶", "普洱茶", "铁观音", "龙井",
        "白茶", "黄茶", "黑茶", "花茶", "茉莉花茶", "陈皮", "柠檬茶", "果茶",
        "奶茶", "麦片", "燕麦片", "藕粉", "芝麻糊", "核桃糊", "杏仁糊",
        "豆浆粉", "代餐粉", "酵素", "益生菌", "发酵乳", "乳酸菌", "老酸奶",
        "气泡水", "苏打水", "矿泉水", "纯净水", "凉茶", "豆奶", "豆乳", "杏仁奶",
        "椰奶", "燕麦奶", "植物奶", "无糖茶", "玄米茶", "大麦茶", "荞麦茶",
        "八宝粥", "罐头", "松花蛋", "卤味", "鸭货", "猪蹄", "猪耳朵",
        "猪尾巴", "牛杂", "羊杂", "毛肚", "鸭血", "鸭肠", "猪血", "猪脑",
        "面粉", "淀粉", "糯米粉", "红豆沙", "绿豆沙", "莲蓉", "豆沙",
        "淡奶油", "稀奶油", "黄油", "奶酪", "芝士", "马苏里拉", "炼乳",
        "吉利丁", "琼脂", "酵母", "泡打粉", "小苏打", "可可粉", "巧克力豆",
        "果脯", "蜜饯", "披萨", "蛋挞皮", "蛋糕", "饼干", "糕点", "面包",
        "坚果", "炒货", "瓜子", "花生", "糖果", "巧克力", "薯片", "果冻",
        "苹果干", "苹果脆", "鲜花饼", "玫瑰饼",
        "冲饮", "咖啡", "牛奶", "酸奶", "冰淇淋", "五谷", "杂粮", "大米",
        "食用油", "橄榄油", "葵花籽油", "玉米油", "蜂蜜", "燕窝", "蜂胶",
        "杏干", "无花果干", "椰蓉", "椰汁", "椰浆",
    ],
    # --- 水果 ---
    "水果": [
        "苹果", "香蕉", "橙子", "橘子", "砂糖橘", "蜜橘", "柚子", "葡萄",
        "提子", "猕猴桃", "芒果", "火龙果", "草莓", "蓝莓", "樱桃", "车厘子",
        "桃子", "油桃", "黄桃", "李子", "枇杷", "杨梅", "荔枝",
        "桂圆", "龙眼", "红枣", "灰枣", "骏枣", "哈密瓜", "西瓜", "甜瓜",
        "香瓜", "柠檬", "菠萝", "凤梨", "椰子", "牛油果", "百香果", "番石榴",
        "释迦", "榴莲", "山竹", "无花果", "桑葚", "树莓", "覆盆子", "黑莓",
        "木瓜", "杨桃", "莲雾", "南瓜",
    ],
    # --- 化妆品 ---
    "化妆品": [
        "面膜", "面霜", "眼霜", "乳液", "精华", "防晒", "口红", "粉底",
        "卸妆", "爽肤水", "隔离", "BB霜", "CC霜", "气垫", "散粉", "腮红",
        "眉笔", "眼线", "唇膏", "唇彩", "精油", "芦荟胶",
        "化妆水", "抗皱", "紧致", "美白", "玻尿酸", "修复液",
        "透明质酸钠", "次抛", "敷尔佳", "香水", "古龙水",
        "香水礼盒", "女士香水", "男士香水", "滚珠香水",
    ],
    # --- 母婴 ---
    "母婴": [
        "奶粉", "尿不湿", "纸尿裤", "拉拉裤", "奶瓶", "奶嘴", "辅食",
        "磨牙棒", "婴儿车", "推车", "安全座椅", "围兜", "睡袋", "童装",
        "童鞋", "孕妇装", "月子服", "防溢乳垫", "束腹带", "妊娠纹",
        "米粉", "婴儿洗澡盆", "儿童浴盆", "宝宝浴盆", "婴儿浴盆",
        "精油贴", "植物精油贴", "婴儿玩具", "婴儿服装", "婴儿鞋",
        "孕产妇", "孕妇奶粉", "哺乳", "吸奶器", "待产",
    ],
    # --- 保健品 ---
    "保健品": [
        "钙片", "维生素", "鱼油", "蛋白粉", "胶原蛋白", "阿胶",
        "葡萄籽", "叶酸", "褪黑素", "辅酶", "氨糖", "软骨素", "奶蓟",
        "蔓越莓", "消食片", "健胃消食片", "钙D", "钙+D", "液体钙",
        "钙镁", "钙镁锌", "锌钙", "锌镁", "深海鱼油", "磷脂", "褪黑",
        "VC", "VD", "VB", "VE", "增肌蛋白", "CoQ10", "铁剂", "胶原",
    ],
    # --- 计生用品 ---
    "计生用品": [
        "避孕套", "安全套", "验孕", "排卵", "早孕", "验孕棒", "测排卵",
        "杜蕾斯", "杰士邦", "冈本", "名流", "情趣", "润滑", "润滑液",
        "润滑剂",
    ],
}


# ============================================================
# 商品类型归一化：同义词 → 统一用第一个（作为去重键）
# ============================================================
_NORMALIZE_MAP = {
    # 沐浴露/沐浴液 → 统一为"沐浴露"
    "沐浴液": "沐浴露",
    # 火腿肠/香肠 → 统一为"火腿肠"
    "香肠": "火腿肠",
    "腊肠": "火腿肠",
    "培根": "火腿肠",
    # 洗脸巾/擦脸巾 → 统一为"洗脸巾"
    "擦脸巾": "洗脸巾",
    # 洗发露/洗发水 → 统一为"洗发水"
    "洗发露": "洗发水",
    # 沐浴液/沐浴露 → 统一为"沐浴露"（已处理）
    "沐浴露": "沐浴露",
    # 洗面奶/洁面乳 → 统一为"洗面奶"
    "洁面乳": "洗面奶",
    # 护发素 → 不变
    # 浴巾 → 不变
    # 一次性浴巾 → 归一化为"浴巾"
    "一次性浴巾": "浴巾",
    # 一次性洗脸巾 → 归一化为"洗脸巾"
    "一次性洗脸巾": "洗脸巾",
}


def _normalize_product_type(product_type):
    """归一化商品类型词"""
    if not product_type:
        return product_type
    return _NORMALIZE_MAP.get(product_type, product_type)


def _extract_product_type(title, category=None):
    """
    从标题中提取商品类型（品类限定）

    策略：清理标题 → 在指定品类的关键词中找最靠右的匹配 → 归一化

    例："HERM'S...牙刷...牙刷+宽头护龈牙刷 11支" + 日用品 → "牙刷"
    例："圣美伦...香水...女士香水淡香...爱情海 50ml" + 化妆品 → "香水"
    例："鲜七星贝贝南瓜...精选贝贝南瓜【净重7.3斤】" + 水果 → "南瓜"

    参数：
        title: 商品标题
        category: 商品所属品类（从 jd_api.py convert_to_item 分类而来）
                  如果不传，则搜索所有品类关键词

    返回：
        归一化后的商品类型词，或 None
    """
    if not title:
        return None

    t = title

    # 1. 去掉【】括号内容
    t = re.sub(r'【[^】]*】', '', t)
    # 2. 去掉（）括号内容
    t = re.sub(r'[（(][^）)]*[）)]', '', t)
    # 3. 去掉开头英文品牌
    t = re.sub(r'^[A-Z][A-Za-z\-]+\s*', '', t)
    # 4. 去掉开头中文品牌（2-3汉字 + 分隔符）
    t = re.sub(r'^([一-鿿]{2,3})(?:\s|·|【|（|\.|-|\/|$)', '', t)
    # 5. 去掉数字和规格单位
    t = re.sub(r'\d+[kgml斤包袋个支条盒罐瓶件份]*', '', t)
    # 6. 去掉连接符号和多余空格
    t = re.sub(r'\s+', '', t)
    t = re.sub(r'[+&*×xX]', '', t)

    # 选择关键词范围：如果传了品类，只搜该品类的词
    kws = _PRODUCT_KEYWORDS_BY_CAT.get(category, [])
    if not kws:
        # 没有匹配的品类，搜全部关键词
        kws = []
        for cat_kws in _PRODUCT_KEYWORDS_BY_CAT.values():
            kws.extend(cat_kws)

    # 在所有关键词中找位置最靠右的匹配
    best_pos = -1
    best_kw = None
    for kw in kws:
        pos = t.rfind(kw)
        if pos > best_pos:
            best_pos = pos
            best_kw = kw

    return _normalize_product_type(best_kw)


def filter_products(items, config):
    """
    筛选商品
    规则：
    1. 排除小众/工业品类 / 药品 / 医疗器械
    2. 销量、好评率、价格过滤
    3. **7天内同品类+同商品类型不重复**
    4. **同品牌每天最多1个商品**
    """
    # 初始化品牌去重集合
    filter_products._used_brands = getattr(filter_products, '_used_brands', set())
    filter_products._used_brands.clear()
    min_price = config.get("min_price", 5)
    max_price = config.get("max_price", 100)
    price_upper = config.get("price_upper_limit", 500)

    history = load_history()
    # 品类去重池：最近140条 ≈ 7天 × 20条
    pushed_types = set(history.get("product_types", [])[-140:])
    print(f"    品类去重池: {len(pushed_types)} 个商品类型")

    filtered = []
    for item in items:
        if not item:
            continue

        # 排除小众品类/药品/医疗器械
        if item.get("excluded", False):
            continue

        # 排除无法归类到品类的商品
        if item.get("category", "") == "其他":
            continue

        price = item.get("price", 0)

        # 价格过滤
        if price < min_price or price > price_upper:
            continue

        # ====== 核心去重：提取商品类型 ======
        title = item.get("title", "")
        category = item.get("category", "")
        product_type = _extract_product_type(title, category)

        # 品牌去重：同品牌每天最多1个商品
        brand = _extract_brand(title)
        if brand:
            used_brands = getattr(filter_products, '_used_brands', set())
            if brand in used_brands:
                print(f"  🚫 品牌去重: {title[:35]}... (品牌 '{brand}' 已使用)")
                continue
            used_brands.add(brand)

        if product_type:
            dedup_key = f"{category}|{product_type}"
            if dedup_key in pushed_types:
                print(f"  🚫 品类去重: {title[:35]}... ({dedup_key})")
                continue
        else:
            # 提取失败，fallback 到 SKU 去重
            sku_id = item.get("sku_id", "")
            all_skus = history.get("sku_ids", [])[-140:]
            if sku_id and sku_id in all_skus:
                print(f"  🚫 SKU 去重: {title[:35]}... (sku={sku_id})")
                continue

        # 折扣检查
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
            continue

        # 月销量
        sales = item.get("sales_30d", 0)
        min_sales = 100 if item.get("category") == "食品" else 300
        if sales < min_sales:
            continue

        # 评价数
        good_count = item.get("good_count", 0)
        min_comments = 50 if item.get("category") == "食品" else 100
        if good_count < min_comments:
            continue

        filtered.append(item)

    return filtered


def score_product(item):
    """
    综合评分（满分约120，含加分项）
    折扣30% + 好评15% + 销量15% + 品类30% + 佣金10% + 优惠券10%
    + 品牌5分 + 大包装3分 + 价格带3分 - 低折扣惩罚5分
    """
    score = 0

    # === 折扣力度（30分）===
    orig = item.get("orig_price", 0)
    price = item.get("price", 0)
    discount_pct = 0
    if orig > 0 and price > 0:
        discount_pct = (orig - price) / orig
        score += discount_pct * 30
        # 折扣门槛：<10% 扣分（避免星鲨AD(2%)这种）
        if discount_pct < 0.10:
            score -= 5
        # 20-50% 最优折扣区间
        elif 0.20 <= discount_pct <= 0.50:
            score += 3

    # === 好评率（15分）===
    good_rate = item.get("good_rate", 90)
    score += (good_rate / 100) * 15

    # === 销量（15分）===
    sales = item.get("sales_30d", 0)
    if sales >= 50000:
        score += 15
    elif sales >= 10000:
        score += 12
    elif sales >= 5000:
        score += 9
    elif sales >= 1000:
        score += 6
    elif sales >= 300:
        score += 3

    # === 品类偏好（30分）===
    cat = item.get("category", "")
    title = item.get("title", "")
    cat_scores = {
        "水果": 35,      # 当季水果转化率最高（7/27用户选品24%是水果）
        "食品": 30,
        "日用品": 28,    # 高频刚需（清洁/纸品/驱蚊）
        "其他": 15,       # 服装、家纺等基础分
        "母婴": 8,
        "化妆品": 5,
        "保健品": 5,      # 提高：Swisse/诺特兰德高单价高佣金
        "计生用品": 2,
    }
    score += cat_scores.get(cat, 0)

    # === 饮料/速食子品类加分 ===
    drink_kw = ["椰子汁", "椰汁", "电解质", "气泡水", "苏打水", "矿泉水", "纯净水",
                "凉茶", "豆奶", "豆乳", "杏仁奶", "燕麦奶", "植物奶", "无糖茶",
                "柠檬茶", "果茶", "奶茶", "咖啡", "牛奶", "酸奶", "椰奶"]
    instant_kw = ["拌面", "拌粉", "自热", "螺蛳粉", "酸辣粉", "方便面", "泡面", "速食",
                  "意面", "意大利面", "午餐肉", "罐头"]
    for kw in drink_kw:
        if kw in title:
            score += 2.5  # 饮料加分（28分 ≈ 食品档位）
            break
    for kw in instant_kw:
        if kw in title:
            score += 2.5  # 速食/罐头加分
            break

    # === 卫生巾/女性刚需品类加分（2分）===
    feminine_kw = ["卫生巾", "安睡裤", "安心裤", "护垫", "日夜组合"]
    for kw in feminine_kw:
        if kw in title:
            score += 2
            break

    # === 小家电/夏季应季加分（2分）===
    appliance_kw = ["风扇", "循环扇", "桌面风扇", "静音风扇", "空气循环扇",
                    "加湿器", "电蚊拍", "灭蚊灯", "除湿机"]
    for kw in appliance_kw:
        if kw in title:
            score += 2
            break

    # === 服装/家纺加分（2分）===
    textile_kw = ["T恤", "t恤", "短袖", "亲子装", "新疆棉", "凉席", "冰丝",
                  "床单", "被套", "枕套", "夏凉被", "空调被"]
    for kw in textile_kw:
        if kw in title:
            score += 2
            break

    # === 乳品/蛋奶加分（2分）===
    dairy_kw = ["鲜牛奶", "纯牛奶", "鲜奶", "高钙牛奶", "蛋白牛奶", "鸡蛋",
                "鲜鸡蛋", "无抗鸡蛋", "无菌蛋", "谷物蛋", "鲜蛋"]
    for kw in dairy_kw:
        if kw in title:
            score += 2
            break

    # === 粗粮/健康食品加分（1.5分）===
    grain_kw = ["粗粮", "杂粮", "南瓜", "红薯", "烟薯", "紫薯", "白薯", "蜜薯"]
    for kw in grain_kw:
        if kw in title:
            score += 1.5
            break

    # === 罐头加分（1.5分）===
    can_kw = ["罐头", "午餐肉", "黄桃罐头", "带鱼罐头", "鱼罐头"]
    for kw in can_kw:
        if kw in title:
            score += 1.5
            break

    # === 童装/童鞋加分（2分）===
    kids_wear_kw = ["童鞋", "童装", "儿童鞋", "宝宝鞋", "学步鞋", "跑步鞋"]
    for kw in kids_wear_kw:
        if kw in title:
            score += 2
            break

    # === 冷冻肉品加分（2分）===
    meat_kw = ["肥牛", "肥羊", "牛排", "牛腩", "羊排", "虾仁", "虾滑",
               "鸡胸", "鸡腿", "鸡翅", "牛腱", "牛筋"]
    for kw in meat_kw:
        if kw in title:
            score += 2
            break

    # === 佣金比例（10分）===
    ratio = item.get("commission_ratio", 0)
    if ratio > 0:
        score += min(ratio / 30, 1) * 10

    # === 优惠券（10分）===
    if item.get("coupon_amount", 0) > 0 and item.get("coupon_available", False):
        score += 10
    elif item.get("coupon_amount", 0) > 0:
        score += 5

    # === 品牌分（5分）===
    # 京东自有品牌/知名品牌的商品转化率更高
    JD_OWN_BRANDS = ["京觅", "京鲜生", "京造", "惠寻", "佳佰", "LATIT", "鲜京采"]
    TOP_BRANDS = ["白象", "东鹏", "欢乐家", "超威", "洁成", "妙洁", "美丽雅",
                  "佳帮手", "苏泊尔", "九阳", "炊大皇", "立白", "蓝月亮", "奥妙",
                  "润本", "百草味", "良品铺子", "三只松鼠", "士力架", "乐事",
                  "农夫山泉", "康师傅", "统一", "蒙牛", "伊利", "光明", "君乐宝",
                  "维达", "洁柔", "清风", "心相印", "舒洁", "杜蕾斯", "杰士邦",
                  "冈本", "小皮",
                  "梅林", "臭宝", "小熊驾到", "高洁丝", "自由点", "艾美特",
                  "三全", "思念", "湾仔码头",
                  "紫林", "活力28", "威王", "盐津铺子", "科尔沁", "富安娜",
                  "Swisse", "swisse",
                  "洽洽", "千禾", "超能", "舒肤佳", "榴莲西施", "溜溜梅",
                  "澳宝", "真维斯", "螺霸王", "诺特兰德", "银鹭", "金典",
                  "泸溪河", "喜之郎", "海狸先生", "必胜客", "农夫好牛",
                  "宛禾", "都乐", "鸿星尔克", "贝因美",
                  "王家渡", "1号会员店", "每日鲜语", "咪咪", "康新牧场",
                  "辛味道", "乌江", "食族人", "鄱湖", "e洁",
                  "牧果人", "上好佳", "水塔", "加加", "吉果叔", "小黄象", "吉香居"]
    brand_matched = False
    for b in JD_OWN_BRANDS:
        if b in title:
            score += 5
            brand_matched = True
            break
    if not brand_matched:
        for b in TOP_BRANDS:
            if b in title:
                score += 4
                break

    # === 大包装/组合装加分（3分）===
    import re
    bulk_patterns = [
        r'\d+斤', r'\d+kg', r'\d+KG', r'\d+瓶', r'\d+盒', r'\d+袋',
        r'\d+包', r'\d+只', r'\d+件', r'\d+支', r'\d+升',
        r'买\d', r'送\d', r'赠\d', r'任选\d',
    ]
    for pat in bulk_patterns:
        if re.search(pat, title):
            score += 3
            break

    # === 19.9元黄金价格带加分（3分）===
    final_price = item.get("_final_price", price)
    if final_price and 17.9 <= final_price <= 21.9:
        score += 3

    return score


def rank_and_select(items, max_items=10, min_items=8):
    """
    排序并选取前N条，优先食品/水果和日用品
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

    # === 第一轮：优先填充食品+水果（目标6条），再日用品（目标2条）===
    primary_target = int(max_items * 0.8)  # 8条
    food_fruit_target = int(max_items * 0.6)  # 6条食品+水果

    for item in real_deals:
        if len([s for s in selected if s.get("category") in ("食品", "水果")]) >= food_fruit_target:
            break
        if item.get("category") in ("食品", "水果") and item not in selected:
            selected.append(item)

    for item in real_deals:
        if len(selected) >= primary_target:
            break
        if item.get("category") == "日用品" and item not in selected:
            selected.append(item)

    # === 第二轮：补充辅助品类（化妆品/母婴/保健品/计生），最多30% ===
    secondary_cats = ["化妆品", "母婴", "保健品", "计生用品"]
    secondary_limit = max(int(max_items * 0.3), 1)

    secondary_count = 0
    for item in real_deals:
        if len(selected) >= max_items:
            break
        if item.get("category") in secondary_cats and item not in selected:
            if secondary_count < secondary_limit:
                selected.append(item)
                secondary_count += 1

    # === 第三轮：补齐 ===
    for item in real_deals:
        if len(selected) >= max_items:
            break
        if item not in selected:
            selected.append(item)

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
        "水果": "🍎",
        "日用品": "🧴",
        "化妆品": "💄",
        "保健品": "💊",
        "母婴": "👶",
        "计生用品": "🔞",
    }
    return mapping.get(category, "📦")
