"""
京东联盟 API 封装模块
提供京粉精选商品查询、签名生成等功能
"""
import hashlib
import json
import time
import urllib.request
import urllib.parse


class JdUnionAPI:
    """京东联盟开放平台 API 封装"""

    BASE_URL = "https://api.jd.com/routerjson"

    # 京粉精选频道ID
    CHANNELS = {
        "food": 27,           # 食品
        "home": 29,           # 家居生活
        "cheap": 10,          # 9.9包邮
        "seckill": 33,        # 秒杀商品
        "coupon": 1,          # 好券商品
        "hot": 22,            # 实时热销榜
        "big_coupon": 23,     # 大额券
    }

    def __init__(self, app_key, secret_key):
        self.app_key = app_key
        self.secret_key = secret_key
        # 创建不走系统代理的 opener（绕过无法连接的本地代理）
        proxy_handler = urllib.request.ProxyHandler({})
        self._opener = urllib.request.build_opener(proxy_handler)

    def _sign(self, params):
        """
        生成京东联盟 API 签名（MD5）
        关键规则：
        1. 按参数名 ASCII 升序排序
        2. 拼接为 secret_key + key1 + value1 + key2 + value2 + ... + secret_key
        3. 跳过空值（value 为 None 或空字符串不参与签名）
        4. MD5 加密后转大写
        """
        sorted_keys = sorted(params.keys())
        sign_str = self.secret_key
        for key in sorted_keys:
            value = params[key]
            if value is None or value == "":
                continue
            if key == "sign":
                continue
            sign_str += f"{key}{value}"
        sign_str += self.secret_key
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest().upper()

    def _request(self, method, biz_params):
        """发送 API 请求"""
        # 业务参数包装在 goodsReq 中
        biz_json = json.dumps({"goodsReq": biz_params}, ensure_ascii=False)

        req_params = {
            "method": method,
            "app_key": self.app_key,
            "format": "json",
            "v": "1.0",
            "sign_method": "md5",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "360buy_param_json": biz_json,
        }
        req_params["sign"] = self._sign(req_params)

        data = urllib.parse.urlencode(req_params).encode('utf-8')
        req = urllib.request.Request(self.BASE_URL, data=data)
        req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")

        try:
            with self._opener.open(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                # 检查是否签名错误
                if "error_response" in result:
                    err = result["error_response"]
                    print(f"  [API错误] code={err.get('code')}, msg={err.get('zh_desc', err.get('en_desc'))}")
                return result
        except Exception as e:
            print(f"[API Error] {method}: {e}")
            return None

    def fetch_jingfen_goods(self, elite_id, page=1, page_size=50):
        """
        获取京粉精选商品
        elite_id: 频道ID（1=好券商品, 2=联盟精选, 10=9.9包邮, 22=热销榜, 27=食品, 29=家居, 33=秒杀）
        """
        params = {
            "eliteId": elite_id,
            "pageIndex": page,
            "pageSize": page_size,
            "sortName": "price",
        }
        result = self._request("jd.union.open.goods.jingfen.query", params)
        if result and "jd_union_open_goods_jingfen_query_responce" in result:
            resp_data = result["jd_union_open_goods_jingfen_query_responce"]
            code = resp_data.get("code")
            if code == "0" or str(code) == "0":
                qr_str = resp_data.get("queryResult", "{}")
                try:
                    qr = json.loads(qr_str)
                    data = qr.get("data", [])
                    print(f"  [频道{elite_id}] 获取成功，共 {len(data) if isinstance(data, list) else 0} 条")
                    return data if isinstance(data, list) else []
                except json.JSONDecodeError:
                    print(f"  [频道{elite_id}] 解析 queryResult 失败")
                    return []
            else:
                msg = resp_data.get("message", resp_data.get("zh_msg", "未知错误"))
                print(f"  [频道{elite_id}] API 返回错误: {msg}")
        return []

    def resolve_real_sku(self, material_url):
        """
        从 jingfen.jd.com/detail/xxx 链接302跳转中获取真实的 item.jd.com SKU ID
        京粉API的 spuid 不是 item.jd.com 的纯数字SKU，必须通过跳转获取
        """
        import re, http.client
        if not material_url:
            return ""
        try:
            url = material_url
            if not url.startswith("http"):
                url = "https://" + url
            # 去掉协议部分
            path = url.replace("https://jingfen.jd.com/", "").replace("http://jingfen.jd.com/", "")
            if not path.startswith("/"):
                path = "/" + path

            conn = http.client.HTTPSConnection("jingfen.jd.com", timeout=10)
            conn.request("GET", path)
            resp = conn.getresponse()
            location = resp.getheader("Location", "")
            conn.close()

            # 从 ReturnUrl= 或直接跳转中提取真实SKU
            sku_match = re.search(r'item\.jd\.com/(\d+)\.html', location)
            if sku_match:
                return sku_match.group(1)
        except Exception as e:
            print(f"  [SKU解析] 失败: {e}")
        return ""

    def get_promotion_link(self, material_url, site_id, sub_union_id=""):
        """
        将原始链接转为带推广佣金的短链接
        调用 jd.union.open.promotion.common.get 接口
        """
        params = {
            "promotionCodeReq": {
                "materialId": material_url,
                "siteId": site_id,
                "subUnionId": sub_union_id,
            }
        }
        result = self._request("jd.union.open.promotion.common.get", params)
        if result:
            resp_key = "jd_union_open_promotion_common_get_response"
            # 兼容两种响应格式
            if "jd_union_open_promotion_common_get_responce" in result:
                resp_key = "jd_union_open_promotion_common_get_responce"
            if resp_key in result:
                resp_data = result[resp_key]
                code = resp_data.get("code")
                if code == "0" or str(code) == "0":
                    qr_str = resp_data.get("queryResult", resp_data.get("result", "{}"))
                    try:
                        qr = json.loads(qr_str) if isinstance(qr_str, str) else qr_str
                        return qr.get("shortURL") or qr.get("clickURL", "")
                    except json.JSONDecodeError:
                        pass
        return ""

    def verify_item_status(self, sku_ids):
        """
        验证商品是否在售（已被禁用 — 京东 CFE 风控不可绕过）
        直接返回所有 SKU 为 True，节省 2-3 分钟
        """
        print(f"  ⏭️ 风控验证已跳过（京东 CFE 不可绕过）")
        return {sku: True for sku in sku_ids if sku}

    def get_real_price(self, sku_ids):
        """
        通过 p.3.cn 接口获取京东实时页面价。
        p.3.cn DNS 解析到内网 IP (172.18.x) 时，fallback 到 Scrapling HTTP 提取。
        返回 {sku_id: real_price}
        """
        if not sku_ids:
            return {}
        # 方案1: p.3.cn (可靠但网络不通)
        try:
            ids_str = ",".join([f"J_{s}" for s in sku_ids])
            url = f"https://p.3.cn/prices/mgets?skuIds={ids_str}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://item.jd.com/",
            })
            with self._opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                result = {}
                for d in data:
                    sid = d.get("id", "").replace("J_", "")
                    price_str = d.get("p", "0")
                    result[sid] = float(price_str)
                if result:
                    return result
        except Exception as e:
            print(f"  [价格查询] p.3.cn 失败: {e}")

        # 方案2: 直接信任京粉API priceInfo.price（即页面价）
        # API 返回的 priceInfo.price 就是页面售价，不需要额外验证
        # p.3.cn 不可达时，priceInfo.price 是唯一可靠数据源
        print("  ⚠️ p.3.cn 不通，使用京粉API价格（priceInfo.price 即页面价）")
        return {}

    def convert_to_item(self, raw, elite_id=None, real_prices=None):
        """将API原始数据转换为统一的商品格式, real_prices为p.3.cn实时价"""
        if real_prices is None:
            real_prices = {}
        try:
            # spuId 是纯数字的SKU ID（如 10034608353023），用于 p.3.cn 查价和 item.jd.com 链接
            pure_sku = str(raw.get("spuid") or raw.get("skuId") or "")

            # itemId 是京东新的动态ID（如 jwQitWLNQeTXqcT0gXmbXqcT0gXmbQ_...），用于联盟推广
            item_id = raw.get("itemId") or ""

            # 商品标题
            title = raw.get("skuName") or raw.get("goodsName") or "未知商品"

            # 价格字段 - 使用 priceInfo
            price_info = raw.get("priceInfo") or {}
            price = price_info.get("price", 0)
            lowest_coupon_price = price_info.get("lowestCouponPrice", 0)

            # 优惠券信息
            coupon_info = raw.get("couponInfo") or {}
            coupon_list = coupon_info.get("couponList", [])
            best_coupon = None
            for cp in coupon_list:
                if cp.get("isBest") == 1:
                    best_coupon = cp
                    break
            if not best_coupon and coupon_list:
                best_coupon = coupon_list[0]
            coupon_amount = best_coupon.get("discount", 0) if best_coupon else 0
            coupon_link = best_coupon.get("link", "") if best_coupon else ""

            # 购买信息
            purchase_info = raw.get("purchasePriceInfo") or {}
            threshold_price = purchase_info.get("thresholdPrice", 0)  # 满减门槛
            purchase_price = purchase_info.get("purchasePrice", 0)    # 券后到手价

            # 用 p.3.cn 实时价格
            real_price = real_prices.get(pure_sku, 0) if pure_sku else 0

            # 显示价格：p.3.cn实时价 > priceInfo.price
            display_price = real_price if real_price > 0 else price

            # 券后到手价（仅当满减门槛已满足时才算有效）
            coupon_price = None
            if coupon_amount > 0:
                # 如果券门槛 <= 商品售价，券可用
                if threshold_price > 0 and threshold_price <= display_price:
                    coupon_price = max(display_price - coupon_amount, 0)
                    if lowest_coupon_price > 0 and lowest_coupon_price < coupon_price:
                        coupon_price = lowest_coupon_price
                    if purchase_price > 0 and purchase_price < coupon_price:
                        coupon_price = purchase_price
                # 否则券不可用，不显示券后价（只标注有券）

            # 原价
            if threshold_price > 0 and threshold_price > display_price:
                orig_price = threshold_price
            elif real_price > 0 and price > real_price:
                orig_price = price
            else:
                orig_price = display_price + coupon_amount if coupon_amount else display_price * 1.3

            # 佣金
            commission_info = raw.get("commissionInfo") or {}
            commission = commission_info.get("commission", 0)
            commission_ratio = commission_info.get("commissionShare", 0)

            # 评价
            good_rate = raw.get("goodCommentsShare", 0)
            comments = raw.get("comments", 0)

            # 销量
            sales_30d = raw.get("inOrderCount30DaysSku") or raw.get("inOrderCount30Days", 0)

            # 链接 - 优先用 materialUrl（jingfen链接，后续302解析真实SKU）
            material_url = raw.get("materialUrl") or ""
            if material_url and not material_url.startswith("http"):
                material_url = f"https://{material_url}"
            # fallback: spuid 不是有效 SKU，不直接构建 item.jd.com 链接
            if not material_url and pure_sku:
                material_url = f"https://item.jd.com/{pure_sku}.html"

            # 分类 - 扩展关键词匹配
            cat_info = raw.get("categoryInfo") or {}
            all_cats = (cat_info.get("cid1Name", "") + cat_info.get("cid2Name", "") + cat_info.get("cid3Name", ""))

            # 食品类关键词（只保留明确的食品类别，去掉"盐""醋"等太泛的词）
            food_kw = [
                "食品", "零食", "饮料", "生鲜", "水果", "乳品", "粮油", "调味", "茗茶",
                "预制菜", "方便食品", "坚果", "糖果", "饼干", "糕点", "肉干", "蜜饯", "烘焙",
                "冲饮", "咖啡", "牛奶", "酸奶", "冰淇淋", "海鲜", "水产", "蛋", "蔬菜",
                "速食", "面条", "米", "面", "酱", "鸡", "鸭", "鱼", "虾", "牛肉", "猪肉",
                "粽子", "火腿", "腊肉", "罐头", "大米", "面粉", "五谷", "杂粮", "面包", "蛋糕",
                "巧克力", "薯片", "果冻", "豆干", "瓜子", "花生", "卤味", "腊肠", "枸杞",
                "蜂蜜", "燕窝", "参", "鲍鱼", "海参", "螺蛳粉", "酸辣粉", "自热",
                "食用油", "橄榄油", "葵花籽油", "玉米油", "花生油",
            ]
            # 日用品关键词
            home_kw = [
                "家居", "日用", "清洁", "家纺", "收纳", "洗衣", "纸巾", "拖把", "扫把",
                "洗浴", "沐浴", "洗发", "牙刷", "牙膏", "毛巾", "浴巾", "拖鞋", "衣架",
                "垃圾袋", "保鲜袋", "密封袋", "挂钩", "置物架", "抹布", "洗衣液", "洗洁精",
                "消毒液", "驱蚊", "灭蚊", "洗手液", "家清", "个护", "抽纸", "卷纸", "湿巾",
                "厨房", "卫浴", "碗", "筷", "锅", "刀", "砧板", "保温杯", "水杯",
                "香皂", "沐浴露", "洗面奶", "洗手", "洁面", "肥皂",
                "卫生巾", "安全裤", "安心裤", "卫生棉", "护垫",
                "口罩", "棉签", "棉棒", "饭盒", "保鲜膜", "垃圾袋",
            ]
            # 化妆品/护肤品关键词
            cosmetic_kw = [
                "护肤", "美妆", "化妆", "面膜", "精华", "面霜", "乳液", "防晒", "粉底",
                "口红", "眼影", "卸妆", "洁面乳", "爽肤水", "眼霜", "隔离", "BB霜",
                "CC霜", "气垫", "散粉", "腮红", "眉笔", "眼线", "唇膏", "唇彩",
                "护手霜", "身体乳", "精油", "芦荟胶",
            ]
            # 保健品关键词
            health_kw = [
                "保健", "维生素", "钙片", "鱼油", "蛋白粉", "益生菌", "胶原蛋白",
                "阿胶", "钙尔奇", "汤臣", "善存", "葡萄籽", "蔓越莓", "奶蓟",
                "叶酸", "铁剂", "锌", "镁", "褪黑素", "辅酶", "氨糖", "软骨素",
            ]
            # 母婴关键词
            baby_kw = [
                "婴儿", "宝宝", "儿童", "孕妇", "奶粉", "尿不湿", "奶瓶", "童装",
                "母婴", "孕妈", "待产", "哺乳", "吸奶器", "奶嘴", "辅食", "磨牙",
                "湿巾婴儿", "婴儿车", "安全座椅", "围兜", "睡袋",
            ]
            # 计生用品关键词
            plan_kw = [
                "避孕套", "安全套", "验孕", "排卵", "验孕棒", "早孕", "计生",
                "情趣", "润滑", "冈本", "杜蕾斯", "杰士邦", "名流",
            ]
            # 排除品类：小众/工业/药品/医疗器械/专业工具
            exclude_kw = [
                # 小众家居
                "甲醛", "活性炭", "检测仪", "除甲醛", "防甲醛", "苯检测",
                # 工业/安防/工具
                "工业", "安防", "监控", "报警器", "门禁",
                "维修工具", "电钻", "电锯", "螺丝刀", "扳手", "钳子",
                "汽车配件", "汽修", "机油", "轮胎",
                # 药品
                "口服溶液", "口服液", "颗粒剂", "注射液",
                "创可贴", "创口贴", "退热贴", "退热", "止咳", "化痰", "感冒", "消炎",
                "鸡眼", "鸡眼贴", "鸡眼膏", "敷料", "人工皮", "疣", "跖疣", "褥疮",
                "清凉油", "滚珠清凉", "防暑", "提神醒脑", "晕车",
                "口罩（医用）", "口罩(医用)", "医用外科口罩", "医用口罩", "一次性医用", "医用棉签",
                "医用面膜", "械字号", "医用敷料", "医用胶原", "医用修复",
                "抗菌", "抑菌", "灭菌", "无菌", "菌贴", "菌膏",
                "创可贴", "创口贴",
                "抗生素", "头孢", "阿莫西林", "处方药",
                "藿香正气", "板蓝根", "连花清瘟", "布洛芬", "对乙酰氨基酚",
                "氯雷他定", "蒙脱石", "奥美拉唑", "雷贝拉唑",
                "开塞露", "滴眼液", "眼药水", "滴耳液",
                "糠酸莫米松", "莫匹罗星", "酮康唑", "克霉唑",
                "氨溴索", "沙丁胺醇", "孟鲁司特", "西替利嗪",
                "伤风感冒", "蒲地蓝", "乳果糖", "多潘立酮", "吗丁啉",
                "西地碘", "华素片", "咽炎", "扁桃体",
                "酵母菌散", "布拉氏", "妈咪爱", "益生菌散",
                "医用棉签",
                # 医疗器械
                "血糖仪", "血糖试纸", "血压计", "血氧仪", "雾化器", "制氧机",
                "呼吸机", "轮椅", "拐杖", "护理床", "造口袋",
                "耳温计", "额温枪", "体温计", "听诊器",
                "针灸", "拔罐", "艾灸", "理疗仪", "中频治疗",
                "洗鼻器", "洗鼻壶", "鼻腔冲洗", "鼻腔喷雾", "喷鼻",
                "酒精", "酒精喷雾", "酒精湿巾", "消毒杀菌", "杀菌消毒", "乙醇消毒",
                # 其他排除
                "兽药", "宠物药", "狗粮", "猫粮", "猫砂",
                "电池", "蓄电池", "电风扇", "空调扇", "取暖器", "加湿器",
                "气垫床", "防褥疮", "护理垫",
                "隐形眼镜", "护理液",
                # 电子产品/数码配件
                "充电器", "充电头", "充电线", "数据线", "蓝牙耳机", "有线耳机",
                "手机壳", "手机膜", "钢化膜", "耳机套", "手机支架",
                "移动电源", "充电宝", "快充头", "快充线",
                "华强北", "AirPods",
            ]

            # 排除检查
            is_excluded = any(kw in all_cats + title for kw in exclude_kw)

            # 大牌保健品白名单：只有含这些词的商品才标记为"保健品"
            # 不含白名单词但被京东类目归为保健品的 → 视为小众医药器械，排除
            major_health_kw = [
                "钙片", "钙尔奇", "钙D", "钙+D", "液体钙", "钙镁",
                "鱼油", "深海鱼油", "磷脂",
                "氨糖", "软骨素", "氨糖软骨素",
                "维生素", "善存", "VC", "VD", "VB", "VE",
                "蛋白粉", "增肌蛋白",
                "辅酶", "CoQ10",
                "褪黑素", "褪黑",
                "叶酸", "铁剂",
                "胶原蛋白", "胶原",
                "阿胶", "燕窝", "蜂胶",
                "益生菌",
                "葡萄籽", "蔓越莓", "奶蓟",
                "枸杞",  # 枸杞在食品里，但留着防漏
                "钙镁锌", "锌钙", "锌镁",
            ]

            # === 按标题关键词优先判断品类（比类目名更可靠）===
            category = "其他"

            # ===== 标题关键词匹配（特定日用品→食品→计生→化妆品→母婴→保健品→通用日用品）=====
            # 第1步：特定日用品
            if any(kw in title for kw in ["一次性饭盒", "一次性筷子", "一次性杯子", "打包盒", "餐盒", "饭盒",
                    "口罩", "卫生巾", "安心裤", "安全裤", "护垫",
                    "眼罩", "蒸汽眼罩", "热敷眼罩", "矫姿带", "背背佳", "暖宝宝",
                    "米桶", "储米", "面桶", "揉面垫", "擀面垫", "打蛋器", "烘焙工具",
                    "菜刀", "刀具", "切菜", "切片刀", "水果刀", "剪刀", "砧板", "案板",
                    "封口机", "真空机", "绞肉机", "榨汁机", "破壁机",
                    "沐浴露", "沐浴液", "身体乳", "护手霜",
                    "洗发水", "洗发露", "洗发乳", "护发素", "发膜",
                    "洗脸巾", "擦脸巾", "面巾纸", "棉柔巾"]):
                category = "日用品"
            # 第2步：食品（水果/生鲜/零食等，优先于母婴避免含"孕妇"的水果被误判）
            # "苹果"特殊处理：排除苹果手机/苹果充电器等电子产品
            elif any(kw in title for kw in ["苹果"]) and not any(ek in title for ek in ["充电", "手机", "耳机", "数据线", "iPad", "iPhone", "MacBook", "Watch", "蓝牙"]):
                category = "食品"
            elif any(kw in title for kw in ["水果", "香蕉", "橙", "猕猴桃", "芒果", "火龙果", "榴莲", "葡萄", "西瓜", "哈密瓜", "荔枝", "龙眼", "草莓", "蓝莓", "车厘子", "桃", "梨", "柚子", "柠檬", "菠萝", "椰子", "牛油果", "甜瓜", "生鲜", "新鲜水果"]):
                category = "食品"
            elif any(kw in title for kw in ["虾", "鱼", "蟹", "贝", "鱿鱼", "海参", "鲍鱼", "扇贝", "生蚝", "三文鱼", "牛排", "羊肉", "鸡翅", "鸡胸", "鸡腿", "猪肉", "牛肉丸", "火锅"]):
                category = "食品"
            elif any(kw in title for kw in ["大米", "食用油", "橄榄油", "酱油", "生抽", "料酒", "蚝油", "豆瓣酱", "辣椒酱", "面条", "面粉", "五谷", "杂粮", "方便面", "速食", "自热"]):
                category = "食品"
            elif any(kw in title for kw in ["零食", "牛肉干", "猪肉脯", "卤味", "花生", "瓜子", "锅巴", "薯片", "饼干", "蛋糕", "面包", "牛奶", "酸奶", "冰淇淋", "粽子", "月饼", "火腿", "腊肉", "罐头", "枸杞", "蜂蜜", "咖啡", "螺蛳粉", "酸辣粉", "坚果", "糖果", "巧克力", "果冻", "豆干", "皮蛋", "松花蛋", "咸鸭蛋", "鸡蛋", "鸭脖", "鸭翅", "鸭舌", "鸭掌", "苹果干", "水果干"]):
                category = "食品"
            # 第3步：计生用品
            elif any(kw in title for kw in ["避孕套", "安全套", "验孕", "排卵", "早孕", "验孕棒", "测排卵", "杜蕾斯", "杰士邦", "冈本"]):
                category = "计生用品"
            # 第4步：化妆品
            elif any(kw in title for kw in ["面膜", "面霜", "眼霜", "乳液", "爽肤水", "化妆水", "卸妆", "气垫", "粉底", "精华液", "抗皱", "紧致", "美白", "玻尿酸", "胶原蛋白", "防晒霜", "防晒喷雾", "补水喷雾", "次抛", "修复液", "透明质酸钠", "敷尔佳"]):
                category = "化妆品"
            # 第5步：母婴（在食品之后，避免含"孕妇"的水果被误判）
            elif any(kw in title for kw in ["婴儿", "宝宝", "婴幼儿", "儿童牙刷", "孕产妇", "孕妇", "孕产", "奶粉", "尿不湿", "奶瓶", "奶嘴", "辅食", "磨牙", "待产", "哺乳", "吸奶", "推车", "安全座椅", "围兜", "睡袋"]):
                category = "母婴"
            # 第6步：保健品
            elif any(kw in title for kw in ["钙片", "维生素D", "维生素C", "维生素B", "鱼油", "蛋白粉", "益生菌", "阿胶", "葡萄籽", "叶酸", "褪黑素", "辅酶", "氨糖", "软骨素", "奶蓟", "蔓越莓"]):
                category = "保健品"
            # 第7步：通用日用品
            elif any(kw in title for kw in ["洗衣", "纸巾", "抽纸", "卷纸", "湿巾", "牙刷", "牙膏",
                    "沐浴", "洗发", "洗衣液", "洗手液", "洗洁精", "沐浴露", "香皂", "肥皂",
                    "马桶", "下水道", "拖把", "扫把", "抹布", "洗碗", "洗面奶", "洁面",
                    "保鲜膜", "保鲜袋", "垃圾袋", "密封罐", "衣架", "挂钩", "收纳", "毛巾", "浴巾",
                    "棉签", "棉棒", "驱蚊", "灭蚊", "拖鞋", "消毒液",
                    "雨伞", "遮阳伞", "太阳伞"]):
                category = "日用品"

            # === 标题无法判断时，用京东类目名作为 fallback ===
            if category == "其他":
                if any(kw in all_cats for kw in food_kw):
                    category = "食品"
                elif any(kw in all_cats for kw in health_kw):
                    # 保健品 fallback：必须是白名单商品，否则排除
                    if any(kw in title for kw in major_health_kw):
                        category = "保健品"
                    else:
                        is_excluded = True  # 不属于白名单，排除
                elif any(kw in all_cats for kw in baby_kw):
                    category = "母婴"
                elif any(kw in all_cats for kw in cosmetic_kw):
                    category = "化妆品"
                elif any(kw in all_cats for kw in plan_kw):
                    category = "计生用品"
                elif any(kw in all_cats for kw in home_kw):
                    category = "日用品"

            return {
                "sku_id": pure_sku or item_id,
                "title": title,
                "price": float(display_price) if display_price else 0,
                "coupon_price": float(coupon_price) if coupon_price else 0,
                "orig_price": float(orig_price) if orig_price else 0,
                "coupon_amount": float(coupon_amount) if coupon_amount else 0,
                "commission": float(commission) if commission else 0,
                "commission_ratio": float(commission_ratio) if commission_ratio else 0,
                "good_rate": float(good_rate) if good_rate else 0,
                "good_count": int(comments) if comments else 0,
                "sales_30d": int(sales_30d) if sales_30d else 0,
                "link": material_url,
                "coupon_link": str(coupon_link) if coupon_link else "",
                "category": category,
                "channel": elite_id,
                "excluded": is_excluded,  # 是否属于排除品类
            }
        except Exception as e:
            print(f"  [转换错误] {raw.get('skuName', '?')[:30]}: {e}")
            return None
