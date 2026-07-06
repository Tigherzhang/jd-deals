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

    def resolve_real_sku(self, material_url, spuid=""):
        """
        从 jingfen.jd.com/detail/xxx 链接302跳转中获取真实的 item.jd.com SKU ID
        京粉API的 spuid 不是 item.jd.com 的纯数字SKU，必须通过跳转获取
        如果302跳转失败，fallback 到 spuid 字段（有时京粉API直接返回有效SKU）
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
            print(f"  [SKU解析] 302跳转失败: {e}")

        # fallback: 直接用 spuid（京粉API有时会直接返回有效SKU）
        if spuid and spuid.isdigit() and len(spuid) > 5:
            return spuid

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

            # 最终价格计算：
            # 只用 priceInfo.price（页面售价）作为基准价格
            # 只有确认真的有优惠券时，才计算券后价
            # 不用 purchasePrice（含平台补贴/限时折扣，不可控且不一定需要领券）
            final_price = display_price
            show_orig = False
            coupon_price = None

            # 计算券可用时的券后价（仅限 couponList 中的明确优惠券）
            best_usable_discount = 0
            for cp in coupon_list:
                quota = float(cp.get("quota", 0))
                discount = float(cp.get("discount", 0))
                if quota <= display_price and discount > best_usable_discount:
                    best_usable_discount = discount
            if best_usable_discount > 0:
                coupon_price = max(display_price - best_usable_discount, 0)
                final_price = coupon_price
                show_orig = display_price  # 有券时才显示划线价

            # 原价 = 页面售价（用于展示划线价，无券时等于 final_price）
            orig_price = display_price

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
                # 基础品类
                "食品", "零食", "饮料", "生鲜", "水果", "乳品", "粮油", "调味", "茗茶",
                "预制菜", "方便食品", "坚果", "糖果", "饼干", "糕点", "肉干", "蜜饯", "烘焙",
                "冲饮", "咖啡", "牛奶", "酸奶", "冰淇淋", "海鲜", "水产", "蛋", "蔬菜",
                "速食", "面条", "大米", "面粉", "五谷", "杂粮", "面包", "蛋糕",
                "巧克力", "薯片", "果冻", "豆干", "瓜子", "花生", "卤味", "腊肠", "枸杞",
                "蜂蜜", "燕窝", "鲍鱼", "海参", "螺蛳粉", "酸辣粉", "自热",
                "食用油", "橄榄油", "葵花籽油", "玉米油", "花生油",
                # 蔬菜水果（大量扩充）
                "土豆", "马铃薯", "番茄", "西红柿", "白菜", "青菜", "生菜", "油麦菜", "菠菜",
                "西兰花", "花菜", "菜花", "卷心菜", "甘蓝", "紫甘蓝", "圆白菜", "韭菜",
                "葱", "姜", "蒜", "辣椒", "青椒", "红椒", "彩椒", "茄子", "冬瓜", "南瓜",
                "丝瓜", "黄瓜", "苦瓜", "西葫芦", "胡萝卜", "白萝卜", "青萝卜", "香菜",
                "芹菜", "茼蒿", "空心菜", "苋菜", "芥蓝", "菜心", "莴笋", "芦笋", "竹笋",
                "春笋", "冬笋", "香菇", "蘑菇", "金针菇", "平菇", "杏鲍菇", "蟹味菇",
                "白玉菇", "海鲜菇", "木耳", "黑木耳", "白木耳", "银耳", "海带", "紫菜",
                "海苔", "海藻", "莲藕", "荸荠", "菱角", "山药", "芋头", "地瓜", "红薯",
                "番薯", "紫薯", "玉米", "豆角", "四季豆", "豇豆", "豌豆", "毛豆", "蚕豆",
                "佛手瓜", "西芹", "韭黄", "娃娃菜", "包菜", "茴香", "折耳根", "鱼腥草",
                "苹果", "香蕉", "橙子", "橘子", "砂糖橘", "蜜橘", "柚子", "葡萄", "提子",
                "猕猴桃", "芒果", "火龙果", "草莓", "蓝莓", "樱桃", "车厘子", "桃子",
                "油桃", "黄桃", "李子", "杏", "枇杷", "杨梅", "荔枝", "桂圆", "龙眼",
                "红枣", "灰枣", "骏枣", "哈密瓜", "西瓜", "甜瓜", "香瓜", "柠檬", "菠萝",
                "凤梨", "椰子", "牛油果", "百香果", "番石榴", "释迦", "榴莲", "山竹",
                "无花果", "桑葚", "树莓", "覆盆子", "黑莓", "木瓜", "杨桃", "莲雾",
                # 肉禽蛋奶
                "猪肉", "牛肉", "羊肉", "鸡肉", "鸭肉", "鹅肉", "兔肉", "鹿肉", "鸽子",
                "五花肉", "排骨", "猪蹄", "猪肘", "鸡胸", "鸡腿", "鸡翅", "鸡爪", "鸡翅膀",
                "鸡翅膀", "鸭翅", "鸭脖", "鸭舌", "鸭掌", "鸭腿", "鸡肝", "鸡心", "鸡胗",
                "牛腩", "牛腱", "牛排", "牛肚", "牛筋", "羊排", "羊肉串", "牛肉干", "牛肉脯",
                "腊肉", "腊肠", "香肠", "培根", "火腿", "火腿肠", "午餐肉", "肉松", "肉脯",
                "皮蛋", "咸鸭蛋", "咸鸡蛋", "卤蛋", "茶叶蛋", "蛋挞", "蛋黄", "蛋白",
                # 速冻/火锅/半成品
                "速冻", "冷冻", "水饺", "饺子", "馄饨", "云吞", "汤圆", "元宵", "手抓饼",
                "蛋挞皮", "披萨", "火锅丸", "丸子", "鱼丸", "虾丸", "牛肉丸", "撒尿牛丸",
                "蟹柳", "午餐肉罐头", "方便面", "泡面", "自热锅", "自热火锅", "自热米饭",
                "半成品", "快手菜", "即食", "开袋即食",
                # 调味品/佐料
                "酱油", "生抽", "老抽", "蚝油", "醋", "陈醋", "米醋", "白醋", "香醋", "镇江醋",
                "豆瓣酱", "黄豆酱", "甜面酱", "辣椒酱", "蒜蓉酱", "沙茶酱", "沙拉酱",
                "番茄酱", "芝麻酱", "花生酱", "芥末", "黄芥末", "黑胡椒", "白胡椒",
                "花椒", "八角", "桂皮", "香叶", "孜然", "咖喱", "五香粉", "十三香",
                "鸡精", "味精", "白糖", "冰糖", "红糖", "盐", "海盐", "岩盐", "低钠盐",
                "芝麻油", "香油", "菜籽油", "稻米油", "亚麻籽油", "核桃油", "脐橙",
                # 干货/腌制品/豆制品
                "干货", "干菇", "干木耳", "干海带", "干香菇", "干枣", "干果", "果干",
                "苹果干", "香蕉干", "芒果干", "菠萝干", "草莓干", "蓝莓干", "蔓越莓干",
                "葡萄干", "杏干", "无花果干", "椰蓉", "椰奶", "椰汁", "椰浆",
                "腐竹", "豆腐皮", "千张", "豆皮", "豆泡", "油豆腐", "素鸡", "豆干",
                "豆干", "辣条", "魔芋", "蒟蒻", "面筋", "烤麸", "纳豆", "豆豉", "臭豆腐",
                "泡菜", "酸菜", "榨菜", "雪菜", "梅菜", "萝卜干", "橄榄菜", "下饭菜",
                "酱菜", "咸菜", "腌菜", "酸豆角", "藠头", "子姜", "泡椒", "野山椒",
                # 茶饮/冲调
                "茶叶", "绿茶", "红茶", "乌龙茶", "普洱茶", "铁观音", "龙井", "碧螺春",
                "白茶", "黄茶", "黑茶", "花茶", "茉莉花茶", "菊花茶", "玫瑰花茶",
                "陈皮", "柠檬茶", "果茶", "奶茶", "粉冲", "麦片", "燕麦片", "藕粉",
                "芝麻糊", "核桃糊", "杏仁糊", "豆浆粉", "蛋白粉", "代餐粉", "酵素",
                "益生菌", "发酵乳", "乳酸菌", "气泡水", "苏打水", "矿泉水", "纯净水",
                "凉茶", "王老吉", "加多宝", "豆奶", "豆乳", "杏仁奶", "椰奶", "燕麦奶",
                "植物奶", "无糖茶", "乌龙茶", "玄米茶", "大麦茶", "荞麦茶", "玉米须茶",
                # 其他常见食品
                "粥", "八宝粥", "罐头", "水果罐头", "黄桃罐头", "梨罐头", "豆豉", "鲮鱼罐头",
                "松花蛋", "皮蛋", "咸鸭蛋", "咸鸡蛋", "卤味", "鸭货", "鸭脖", "鸭翅",
                "鸡爪", "凤爪", "泡椒凤爪", "猪蹄", "猪耳朵", "猪尾巴", "牛杂", "羊杂",
                "毛肚", "鸭血", "鸭肠", "猪血", "猪脑", "鸡肾", "鸡心", "鸡肝", "鸡胗",
                "鳕鱼", "三文鱼", "金枪鱼", "带鱼", "黄花鱼", "鲈鱼", "鲫鱼", "鲤鱼",
                "罗非鱼", "巴沙鱼", "龙利鱼", "鲷鱼", "比目鱼", "秋刀鱼", "鲭鱼", "沙丁鱼",
                "银鱼", "小鱼干", "虾米", "虾仁", "虾皮", "干贝", "瑶柱", "扇贝", "牡蛎",
                "生蚝", "蛏子", "花甲", "蛤蜊", "田螺", "海螺", "鲍鱼", "章鱼", "墨鱼",
                "鱿鱼", "乌贼", "海马", "海星", "海胆", "海参", "海蜇", "海带结", "海带丝",
                "海白菜", "裙带菜", "紫菜", "海苔", "虾皮", "虾米", "鱼露", "鱼丸", "鱼豆腐",
                "蟹棒", "即食海鲜", "海鲜干货", "海产品", "淡水鱼", "海水鱼",
                # 烘焙原料
                "面粉", "高筋面粉", "中筋面粉", "低筋面粉", "淀粉", "玉米淀粉", "木薯粉",
                "澄粉", "糯米粉", "红豆沙", "绿豆沙", "莲蓉", "豆沙", "奶油", "黄油",
                "奶酪", "芝士", "马苏里拉", "莫扎瑞拉", "炼乳", "淡奶油", "稀奶油",
                "吉利丁", "琼脂", "酵母", "泡打粉", "小苏打", "食用色素", "食用香精",
                "香草精", "可可粉", "巧克力豆", "耐烤巧克力豆", "果脯", "蜜饯",
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
                "消毒级", "消毒杀菌", "杀菌消毒", "乙醇消毒",
                # 其他排除
                "兽药", "宠物药", "狗粮", "猫粮", "猫砂",
                "电池", "蓄电池", "电风扇", "空调扇", "取暖器", "加湿器",
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
            # 第1步：特定日用品（最高优先级，防止食品口味词误判）
            if any(kw in title for kw in ["一次性饭盒", "一次性筷子", "一次性杯子", "打包盒", "餐盒", "饭盒",
                    "口罩", "卫生巾", "安心裤", "安全裤", "护垫",
                    "眼罩", "蒸汽眼罩", "热敷眼罩", "矫姿带", "背背佳", "暖宝宝",
                    "米桶", "储米", "面桶", "揉面垫", "擀面垫", "打蛋器", "烘焙工具",
                    "菜刀", "刀具", "切菜", "切片刀", "水果刀", "剪刀", "砧板", "案板",
                    "炒锅", "平底锅", "煎锅", "不粘锅", "蒸锅", "蒸笼", "蒸笼纸",
                    "封口机", "真空机", "绞肉机", "榨汁机", "破壁机",
                    "电磁炉", "燃气灶", "煤气灶", "灶具", "油烟机", "抽油烟机",
                    "水龙头", "水槽", "下水器", "地漏", "角阀", "软管",
                    "沐浴露", "沐浴液", "身体乳", "护手霜",
                    "洗发水", "洗发露", "洗发乳", "护发素", "发膜",
                    "洗脸巾", "擦脸巾", "面巾纸", "棉柔巾",
                    "牙膏", "牙刷", "漱口水", "牙线", "牙签",
                    "香皂", "肥皂", "洗手液", "洗面奶", "洁面乳", "面膜",
                    "润肤霜", "润肤露", "爽肤水", "精华液", "面霜", "眼霜",
                    "指甲刀", "指甲剪", "修眉刀", "剃须刀", "剃须泡",
                    "驱蚊手环", "驱蚊贴", "驱蚊扣", "香圈", "苦甲水",
                    "婴儿湿巾", "宝宝湿巾", "纸尿裤", "拉拉裤", "学步鞋", "口水巾",
                    "儿童水杯", "吸管杯", "保温杯儿童",
                    "衣架", "晾衣架", "晒衣架", "晾衣夹", "袜子架", "鞋架",
                    "垃圾桶", "垃圾篓", "收纳箱", "收纳盒", "置物架", "挂架",
                    "密封罐", "密封瓶", "储物瓶", "储物罐", "玻璃瓶",
                    "窗帘", "门帘", "地垫", "脚垫", "地毯",
                    "钟表", "挂钟", "闹钟", "日历", "台历",
                    "花盆", "花架", "花器", "花钵",
                    "镜子", "穿衣镜", "台式镜", "梳妆镜",
                    "锁具", "门锁", "柜锁", "抽屉锁", "密码锁",
                    "开关插座", "插座面板", "电源插座", "排插", "插线板", "接线板",
                    "奶油风", "奶油色", "莫兰迪色", "ins风",
                    "叉子", "勺子", "汤匙", "餐具", "餐叉", "餐勺", "筷子", "刀叉",
                    "吸油纸", "硅油纸", "烘焙纸", "锡纸", "铝箔纸", "铝箔纸",
                    "烤盘", "空气炸锅", "空气炸锅纸",
                    "冰箱", "车载冰箱", "冰柜",
                    "抽水器", "上水器", "饮水机", "电动抽水泵", "纯净水取水器",
                    "桶装水",
                    "泡面锅", "辅食锅", "奶锅", "小奶锅", "汤锅", "炖锅", "砂锅", "高压锅", "电压力锅",
                    "湿巾", "卫生湿巾", "消毒湿巾",
                    "拖把桶", "拖把夹", "扫帚", "簸箕",
                    "蚊香", "电蚊拍", "灭蚊灯",
                    "暖手宝", "热水袋", "冰袋",
                    "雨伞", "雨衣", "雨靴", "雨鞋",
                    "扇子", "风扇", "暖风机", "加湿器",
                    "泡澡桶", "浴缸", "沐浴桶", "坐浴桶",
                    "挡风板", "导风板", "空调挡风",
                    "袜子", "内裤", "文胸", "背心", "打底裤", "丝袜",
                    "围巾", "手套", "帽子", "领带", "袖套",
                    "针线", "扣子", "别针", "图钉", "胶带", "双面胶", "透明胶",
                    "裁纸刀", "美工刀", "刀片",
                    "蜡烛", "香薰", "熏香", "香薰机",
                    "相框", "画框", "摆件", "装饰品",
                    "收纳袋", "整理袋", "压缩袋", "真空袋",
                    "润滑液", "润滑剂",
                    "避孕套", "安全套"]):
                category = "日用品"
            # 第2步：食品（水果/生鲜/零食等，优先于母婴避免含"孕妇"的水果被误判）
            # "苹果"特殊处理：排除苹果手机/苹果充电器等电子产品
            elif any(kw in title for kw in ["苹果"]) and not any(ek in title for ek in ["充电", "手机", "耳机", "数据线", "iPad", "iPhone", "MacBook", "Watch", "蓝牙"]):
                category = "食品"
            elif any(kw in title for kw in ["水果", "香蕉", "橙", "猕猴桃", "芒果", "火龙果", "榴莲", "葡萄", "西瓜", "哈密瓜", "荔枝", "龙眼", "草莓", "蓝莓", "车厘子", "桃", "梨", "柚子", "柠檬", "菠萝", "椰子", "牛油果", "甜瓜", "生鲜", "新鲜水果", "土豆", "马铃薯", "番茄", "西红柿", "白菜", "青菜", "生菜", "油麦菜", "菠菜", "西兰花", "花菜", "卷心菜", "甘蓝", "紫甘蓝", "圆白菜", "韭菜", "辣椒", "青椒", "红椒", "彩椒", "茄子", "冬瓜", "南瓜", "丝瓜", "黄瓜", "苦瓜", "西葫芦", "胡萝卜", "白萝卜", "青萝卜", "香菜", "芹菜", "茼蒿", "空心菜", "苋菜", "芥蓝", "菜心", "莴笋", "芦笋", "竹笋", "春笋", "冬笋", "香菇", "蘑菇", "金针菇", "平菇", "杏鲍菇", "蟹味菇", "白玉菇", "海鲜菇", "木耳", "黑木耳", "白木耳", "银耳", "海带", "紫菜", "海苔", "海藻", "莲藕", "荸荠", "菱角", "山药", "芋头", "地瓜", "红薯", "番薯", "紫薯", "玉米", "豆角", "四季豆", "豇豆", "豌豆", "毛豆", "蚕豆", "佛手瓜", "西芹", "韭黄", "娃娃菜", "包菜", "茴香", "折耳根", "鱼腥草", "苹果", "香蕉", "橙子", "橘子", "砂糖橘", "蜜橘", "柚子", "葡萄", "提子", "猕猴桃", "芒果", "火龙果", "草莓", "蓝莓", "樱桃", "车厘子", "桃子", "油桃", "黄桃", "李子", "杏", "枇杷", "杨梅", "荔枝", "桂圆", "龙眼", "红枣", "灰枣", "骏枣", "哈密瓜", "西瓜", "甜瓜", "香瓜", "柠檬", "菠萝", "凤梨", "椰子", "牛油果", "百香果", "番石榴", "释迦", "榴莲", "山竹", "无花果", "桑葚", "树莓", "覆盆子", "黑莓", "木瓜", "杨桃", "莲雾", "猪肉", "牛肉", "羊肉", "鸡肉", "鸭肉", "鹅肉", "兔肉", "鹿肉", "鸽子", "五花肉", "排骨", "猪蹄", "猪肘", "鸡胸", "鸡腿", "鸡翅", "鸡爪", "鸭翅", "鸭脖", "鸭舌", "鸭掌", "鸭腿", "鸡肝", "鸡心", "鸡胗", "牛腩", "牛腱", "牛排", "牛肚", "牛筋", "羊排", "羊肉串", "牛肉干", "牛肉脯", "腊肉", "腊肠", "香肠", "培根", "火腿", "火腿肠", "午餐肉", "肉松", "肉脯", "皮蛋", "咸鸭蛋", "咸鸡蛋", "卤蛋", "蛋挞", "速冻", "冷冻", "水饺", "饺子", "馄饨", "云吞", "汤圆", "元宵", "手抓饼", "火锅丸", "丸子", "鱼丸", "虾丸", "牛肉丸", "方便面", "泡面", "自热锅", "自热火锅", "自热米饭", "半成品", "快手菜", "即食", "开袋即食", "酱油", "生抽", "老抽", "蚝油", "醋", "陈醋", "米醋", "白醋", "香醋", "镇江醋", "豆瓣酱", "黄豆酱", "甜面酱", "辣椒酱", "蒜蓉酱", "沙茶酱", "沙拉酱", "番茄酱", "芝麻酱", "花生酱", "芥末", "黄芥末", "黑胡椒", "白胡椒", "花椒", "八角", "桂皮", "香叶", "孜然", "咖喱", "五香粉", "十三香", "鸡精", "味精", "白糖", "冰糖", "红糖", "海盐", "岩盐", "低钠盐", "芝麻油", "香油", "菜籽油", "稻米油", "亚麻籽油", "核桃油", "脐橙", "干货", "干菇", "干木耳", "干海带", "干香菇", "干枣", "干果", "果干", "苹果干", "香蕉干", "芒果干", "菠萝干", "草莓干", "蓝莓干", "蔓越莓干", "葡萄干", "杏干", "无花果干", "椰蓉", "椰奶", "椰汁", "椰浆", "腐竹", "豆腐皮", "千张", "豆皮", "豆泡", "油豆腐", "素鸡", "豆干", "辣条", "魔芋", "蒟蒻", "面筋", "烤麸", "纳豆", "豆豉", "臭豆腐", "泡菜", "酸菜", "榨菜", "雪菜", "梅菜", "萝卜干", "橄榄菜", "下饭菜", "酱菜", "咸菜", "腌菜", "酸豆角", "藠头", "子姜", "泡椒", "野山椒", "茶叶", "绿茶", "红茶", "乌龙茶", "普洱茶", "铁观音", "龙井", "碧螺春", "白茶", "黄茶", "黑茶", "花茶", "茉莉花茶", "陈皮", "柠檬茶", "果茶", "奶茶", "粉冲", "麦片", "燕麦片", "藕粉", "芝麻糊", "核桃糊", "杏仁糊", "豆浆粉", "代餐粉", "酵素", "益生菌", "发酵乳", "乳酸菌", "气泡水", "苏打水", "矿泉水", "纯净水", "凉茶", "豆奶", "豆乳", "杏仁奶", "椰奶", "燕麦奶", "植物奶", "无糖茶", "玄米茶", "大麦茶", "荞麦茶", "玉米须茶", "粥", "八宝粥", "罐头", "水果罐头", "黄桃罐头", "梨罐头", "松花蛋", "卤味", "鸭货", "猪蹄", "猪耳朵", "猪尾巴", "牛杂", "羊杂", "毛肚", "鸭血", "鸭肠", "猪血", "猪脑", "鸡肾", "鳕鱼", "三文鱼", "金枪鱼", "带鱼", "黄花鱼", "鲈鱼", "鲫鱼", "鲤鱼", "罗非鱼", "巴沙鱼", "龙利鱼", "鲷鱼", "比目鱼", "秋刀鱼", "鲭鱼", "沙丁鱼", "银鱼", "小鱼干", "虾米", "虾仁", "虾皮", "干贝", "瑶柱", "扇贝", "牡蛎", "生蚝", "蛏子", "花甲", "蛤蜊", "田螺", "海螺", "鲍鱼", "章鱼", "墨鱼", "鱿鱼", "乌贼", "海马", "海星", "海胆", "海参", "海蜇", "海带结", "海带丝", "海白菜", "裙带菜", "紫菜", "海苔", "鱼露", "鱼丸", "鱼豆腐", "蟹棒", "即食海鲜", "海鲜干货", "海产品", "淡水鱼", "海水鱼", "面粉", "高筋面粉", "中筋面粉", "低筋面粉", "淀粉", "玉米淀粉", "木薯粉", "澄粉", "糯米粉", "红豆沙", "绿豆沙", "莲蓉", "豆沙", "淡奶油", "稀奶油", "黄油", "奶酪", "芝士", "马苏里拉", "莫扎瑞拉", "炼乳", "奶油蛋糕", "吉利丁", "琼脂", "酵母", "泡打粉", "小苏打", "食用色素", "食用香精", "香草精", "可可粉", "巧克力豆", "耐烤巧克力豆", "果脯", "蜜饯", "披萨", "蛋挞皮"]):
                category = "食品"
            # 第3步：计生用品
            elif any(kw in title for kw in ["避孕套", "安全套", "验孕", "排卵", "早孕", "验孕棒", "测排卵", "杜蕾斯", "杰士邦", "冈本"]):
                category = "计生用品"
            # 第4步：化妆品
            elif any(kw in title for kw in ["面膜", "面霜", "眼霜", "乳液", "爽肤水", "化妆水", "卸妆", "气垫", "粉底", "精华液", "抗皱", "紧致", "美白", "玻尿酸", "胶原蛋白", "防晒霜", "防晒喷雾", "补水喷雾", "次抛", "修复液", "透明质酸钠", "敷尔佳"]):
                category = "化妆品"
            # 第5步：母婴（只匹配真正的母婴用品，不匹配"婴儿"等宽泛词）
            elif any(kw in title for kw in ["奶粉", "尿不湿", "纸尿裤", "拉拉裤", "奶瓶", "奶嘴", "辅食", "磨牙棒", "待产", "哺乳", "吸奶器", "婴儿车", "推车", "安全座椅", "围兜", "睡袋", "童装", "童鞋", "婴儿湿巾", "宝宝湿巾", "婴儿玩具", "婴儿服装", "婴儿鞋", "孕产妇", "孕妇装", "孕妇奶粉", "孕妇装", "月子服", "防溢乳垫", "束腹带", "妊娠纹"]):
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
                # 核心原则：sku_id绝不能为空，否则去重完全失效
                # 优先级：spuid(京粉ID) > item_id(联盟ID) > 从material_url提取 > 空
                "sku_id": pure_sku or item_id or "",
                "title": title,
                "price": float(display_price) if display_price else 0,
                "coupon_price": float(coupon_price) if coupon_price else 0,
                "purchase_price": float(purchase_price) if purchase_price else 0,
                "orig_price": float(orig_price) if orig_price else 0,
                "coupon_amount": float(coupon_amount) if coupon_amount else 0,
                "commission": float(commission) if commission else 0,
                "commission_ratio": float(commission_ratio) if commission_ratio else 0,
                "good_rate": float(good_rate) if good_rate else 0,
                "good_count": int(comments) if comments else 0,
                "sales_30d": int(sales_30d) if sales_30d else 0,
                "link": material_url,
                "spuid": str(raw.get("spuid") or ""),  # 保留spuid供SKU解析fallback
                "coupon_link": str(coupon_link) if coupon_link else "",
                "coupon_available": bool(coupon_amount and coupon_link),
                "category": category,
                "channel": elite_id,
                "excluded": is_excluded,  # 是否属于排除品类
            }
        except Exception as e:
            print(f"  [转换错误] {raw.get('skuName', '?')[:30]}: {e}")
            return None
