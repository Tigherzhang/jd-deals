# JD CPS 京东优惠精选 - 项目文档

## 项目概述

京东联盟 CPS 推广项目：每日自动采集京东京粉精选优惠商品，生成静态网页发布到 GitHub Pages，支持微信群一键分享。

- **GitHub Pages**: https://tigherzhang.github.io/jd-deals/
- **仓库**: https://github.com/Tigherzhang/jd-deals
- **数据来源**: 京粉API（京东联盟开放平台）

## 架构

```
京粉API → jd_api.py(convert_to_item) → product_filter.py(筛选+去重)
  → jd_fetcher.py(浏览器验价) → page_generator.py(格式化)
  → data.json + index.html → GitHub Pages
```

## 核心模块

### scripts/jd_api.py - 京东联盟 API
- `JdUnionAPI`: API 封装，签名、请求
- `fetch_jingfen_goods()`: 获取京粉精选商品（5个频道）
- `convert_to_item()`: 将 API 原始数据转为统一商品格式
- `resolve_real_sku()`: 从 jingfen 链接302跳转解析真实京东SKU
- `get_promotion_link()`: 生成推广短链接

### scripts/product_filter.py - 筛选与去重
- `filter_products()`: 价格/销量/好评率/品类过滤
- `rank_and_select()`: 评分排序 + 品类多样性选取（max_items=10）
- 7天去重：SKU去重 + 标题相似度去重（>0.90视为重复）
- 评分权重：折扣30% + 好评15% + 销量15% + 品类30% + 佣金10% + 优惠券10%
- 品类权重：食品30分 > 水果28分 > 日用品25分 > 化妆品5分 > 母婴5分 > 保健品3分 > 计生2分
- 品牌去重：同品牌最多保留2个，同款商品保留销量高/价格低者

### scripts/jd_fetcher.py - 浏览器验价
- `verify_prices()`: Playwright 打开京东移动端商品页验证价格
- 宽松策略：页面需登录/暂无定价时保留商品
- 仅价格格式不一致时淘汰

### scripts/page_generator.py - 数据生成
- `format_item()`: 格式化单个商品
- `generate_text_promo()`: 生成微信群分享文字版
- `generate_data()`: 生成 data.json
- 券链接只显示 `coupon_available=True` 的有效链接

### docs/index.html - 前端展示
- 网页卡片展示 + 一键复制全部优惠

### scripts/daily_job.py - 每日主脚本
- 获取商品 → 筛选 → 解析SKU → 验价 → 转链 → 生成数据 → git push
- 转链失败时清除过期券链接，保留原商品链接
- 完成后自动关机（后台60秒无交互，终端可 cancel）

## 价格体系

### 核心原则
**三个界面价格必须统一：网页展示 = 一键复制文字 = 京东下单页**

### 价格计算逻辑
```
price = priceInfo.price（京东页面售价，唯一可信数据源）
coupon_amt = couponList[].discount（券面额，取可用券中最大的）
coupon_price = price - coupon_amt（券后价，仅当券可用时）
  券可用条件：couponList[].quota <= price
_final_price = coupon_price（有可用券）或 price（无可用券）
orig_price = price（仅当有券时显示划线价，无券时不显示）
```

### 关键字段说明
- `priceInfo.price`: 京东页面售价 ✅ 唯一可信，作为基准价格
- `priceInfo.lowestCouponPrice`: API最低券后价 ❌ 可能含多件叠加
- `purchasePriceInfo.purchasePrice`: 含平台补贴/限时折扣/满减 ❌ 不可控，不一定需要领券，**不再作为最终价**
- `purchasePriceInfo.thresholdPrice`: 购买数量总价（=price×purchaseNum）❌ 不是券门槛
- `couponList[].quota`: 券门槛 ✅ 唯一可信
- `couponList[].discount`: 券面额 ✅ 唯一可信
- `couponList[].link`: 领券链接 ✅ 可信（但有有效期，转链失败时需清除）
- `purchaseNum`: 总是1（API不提供多件价格）

### 三界面价格
| 界面 | 展示内容 |
|------|---------|
| 网页 | 💰 ¥XX.XX（_final_price）+ ~~原价~~ |
| 一键复制 | 💰 ¥XX.XX + 🎫 券链接（仅有效时）+ 🛒 商品链接 |
| 京东页面 | 用户领券后 = _final_price |

## 去重策略

### 核心原则
**每个商品必须有可靠的 sku_id，否则去重体系完全失效。京粉API的 spuid 可能为空，必须通过多级fallback保证。**

### sku_id 获取优先级（daily_job.py 步骤3）
```
1. jingfen链接 → 302跳转解析真实SKU
2. item.jd.com链接 → 正则提取数字SKU
3. spuid字段 → 京粉API返回的spuid（有时为空）
4. convert_to_item返回的sku_id → pure_sku or item_id
```
任何一步失败都会打印警告日志，便于排查。

### 双重去重
1. **SKU去重**: 从 `history.json` 读取最近140个SKU（约7天×20条），不在池中才保留
2. **标题相似度去重**: 清理标题（去掉括号内容、空格）后 SequenceMatcher 相似度 >0.80 视为重复

### 去重历史
- `history.json`: 存 `sku_ids` 和 `titles` 各最近350条
- 注意：`spuid`（京粉ID）≠ 京东真实SKU，两者格式不同，不能直接比对

## 自动化

### macOS launchd（本机定时任务）
- 配置文件: `~/Library/LaunchAgents/com.jd-pcs.daily.plist`
- 时间: 每天 08:30
- 脚本: `scripts/daily_job.py`
- 日志: `logs/daily-job.log` / `logs/daily-job.err`

### GitHub Actions（备用）
- 配置: `.github/workflows/daily-sync.yml`
- 时间: UTC 00:30 = 北京时间 08:30
- cron: `'30 0 * * *'`

## 频道配置

| elite_id | 名称 | 页数 |
|----------|------|------|
| 27 | 食品 | 8页 |
| 29 | 家居生活 | 6页 |
| 10 | 9.9包邮 | 2页 |
| 1 | 好券商品 | 2页 |
| 22 | 实时热销榜 | 2页 |

## 筛选规则

| 条件 | 食品 | 其他 |
|------|------|------|
| 价格区间 | 10-100元 | 10-100元 |
| 月销量 | 300+ | 500+ |
| 评价数 | 100+ | 200+ |
| 好评率 | 90%+ | 90%+ |
| 折扣 | 至少5% | 至少5% |
| 价格上限 | 500元 | 500元 |

## 品类分类

优先级：特定日用品 → 食品 → 计生用品 → 化妆品 → 母婴 → 保健品 → 通用日用品

排除品类：小众/工业/药品/医疗器械/专业工具/宠物用品/数码配件等

## 配置

优先读 `config.json`，fallback 到环境变量（GitHub Actions 使用）

环境变量: `JD_APP_KEY`, `JD_SECRET_KEY`, `JD_SITE_ID`, `JD_UNION_ID`

## 已知限制

1. **京东页面频繁需登录**: headless Chromium 触发京东CFE风控，验价保留商品但不验证
2. **API超时**: 部分请求超时（15秒），脚本继续执行不中断
3. **转链失败**: `JD_SITE_ID` 未配置时无法转链（链接不含佣金）
4. **无多件价格**: API `purchaseNum` 总是1，不提供多件优惠价
5. **p.3.cn 不通**: 实时价格查询不可达，使用京粉API `priceInfo.price`

## 近期修复记录

- 2026-06-27: 修复价格不一致（用 price-coupon 替代 lowestCouponPrice）
- 2026-06-27: 修复券链接全为空（page_generator 硬编码为空字符串）
- 2026-06-27: 修复券门槛判断错误（用 couponList[].quota 替代 thresholdPrice）
- 2026-06-27: 修复7天去重失效（spuid ≠ 真实SKU，新增标题相似度去重）
- 2026-06-27: 一键复制增加券链接🎫（前后端同步）
- 2026-07-02: 评分权重重构：品类权重15%→30%，食品30分/日用品25分/化妆品5分
- 2026-07-02: 总条数15→10，食品日用品目标占比70%
- 2026-07-02: 转链失败时清除过期券链接，避免用户点击报错"优惠券已过期"
- 2026-07-02: 文字推送仅显示 coupon_available=True 的有效券链接
- 2026-07-03: 修复虚假划线价：弃用 purchasePrice（含平台补贴/限时折扣不可控），仅用 priceInfo.price + 明确优惠券计算最终价
- 2026-07-03: 无优惠券商品不再显示"券后¥XX"标签和划线价
- 2026-07-03: 修复浮点数精度问题（round 到2位小数）
- 2026-07-03: 修复杰士邦连续推送：resolve_real_sku加spuid fallback，保留spuid字段，标题相似度阈值0.90→0.80
- 2026-07-03: 修复重复推送根因：确保每个商品必须有sku_id（3级fallback: 链接提取→spuid→已有值），否则去重完全失效
