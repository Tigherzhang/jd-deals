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
            with urllib.request.urlopen(req, timeout=15) as resp:
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

    def get_real_price(self, sku_ids):
        """
        通过 p.3.cn 接口获取京东实时页面价
        返回 {sku_id: real_price}
        """
        if not sku_ids:
            return {}
        try:
            ids_str = ",".join([f"J_{s}" for s in sku_ids])
            url = f"https://p.3.cn/prices/mgets?skuIds={ids_str}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://item.jd.com/",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                result = {}
                for d in data:
                    sid = d.get("id", "").replace("J_", "")
                    price_str = d.get("p", "0")
                    result[sid] = float(price_str)
                return result
        except Exception as e:
            print(f"  [价格查询] p.3.cn 失败: {e}")
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

            # 券后到手价
            coupon_price = None
            if coupon_amount > 0:
                coupon_price = max(display_price - coupon_amount, 0)
                if lowest_coupon_price > 0 and lowest_coupon_price < coupon_price:
                    coupon_price = lowest_coupon_price
                if purchase_price > 0 and purchase_price < coupon_price:
                    coupon_price = purchase_price

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

            # 链接 - 用纯数字SKU构建 item.jd.com 格式
            if pure_sku:
                material_url = f"https://item.jd.com/{pure_sku}.html"
            else:
                material_url = raw.get("materialUrl") or ""
                if material_url and not material_url.startswith("http"):
                    material_url = f"https://{material_url}"

            # 分类
            cat_info = raw.get("categoryInfo") or {}
            all_cats = (cat_info.get("cid1Name", "") + cat_info.get("cid2Name", "") + cat_info.get("cid3Name", ""))

            food_kw = ["食品", "零食", "饮料", "生鲜", "水果", "乳品", "粮油", "调味", "茗茶", "酒", "预制菜", "方便食品", "坚果", "糖果", "饼干", "糕点", "肉干", "蜜饯", "烘焙", "冲饮", "咖啡", "牛奶", "酸奶", "冰淇淋", "海鲜", "水产", "蛋", "蔬菜", "速食", "面条", "米", "油", "酱", "醋", "鸡", "鸭", "鱼", "虾", "牛肉", "猪肉", "粽子", "火腿", "腊肉", "罐头"]
            home_kw = ["家居", "日用", "清洁", "家纺", "收纳", "洗衣", "纸巾", "拖把", "扫把", "洗浴", "沐浴", "洗发", "牙刷", "牙膏", "毛巾", "浴巾", "拖鞋", "衣架", "垃圾袋", "保鲜袋", "密封袋", "挂钩", "置物架", "抹布", "洗衣液", "洗洁精", "消毒液", "驱蚊", "灭蚊", "洗手液", "家清", "个护"]

            category = "其他"
            if any(kw in all_cats for kw in food_kw) or any(kw in title for kw in ["零食", "牛肉干", "猪肉脯", "卤味", "花生", "瓜子"]):
                category = "食品"
            elif any(kw in title for kw in ["水果", "苹果", "香蕉", "橙", "猕猴桃", "芒果", "火龙果"]):
                category = "水果/生鲜"
            elif any(kw in all_cats for kw in home_kw) or any(kw in title for kw in ["洗衣", "纸巾", "牙刷", "牙膏", "沐浴", "洗发", "驱蚊"]):
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
            }
        except Exception as e:
            print(f"  [转换错误] {raw.get('skuName', '?')[:30]}: {e}")
            return None
