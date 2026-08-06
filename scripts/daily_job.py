#!/usr/bin/env python3
"""
京东副业 PCS - 每日主脚本
获取优惠商品 → 解析真实SKU → 浏览器验价 → 转链 → 筛选 → 生成网页 → git push
"""
import json
import os
import sys
import subprocess
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from jd_api import JdUnionAPI
from jd_fetcher import verify_prices
from product_filter import filter_products, rank_and_select, load_history, save_history, _extract_product_type
from page_generator import generate_data, save_data


def load_config():
    """加载配置：优先读 config.json，fallback 到环境变量（供 GitHub Actions 使用）"""
    config_path = os.path.join(PROJECT_DIR, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
        if config.get("jd_union", {}).get("app_key"):
            print("[✓] 从 config.json 加载配置")
            return config

    # fallback: 从环境变量读取（GitHub Actions）
    app_key = os.environ.get("JD_APP_KEY", "")
    secret_key = os.environ.get("JD_SECRET_KEY", "")
    site_id = os.environ.get("JD_SITE_ID", "")
    union_id = os.environ.get("JD_UNION_ID", "")

    if not app_key or not secret_key:
        print("[✗] 未找到配置：config.json 不存在且环境变量 JD_APP_KEY/JD_SECRET_KEY 未设置")
        sys.exit(1)

    print("[✓] 从环境变量加载配置")
    return {
        "jd_union": {
            "app_key": app_key,
            "secret_key": secret_key,
            "site_id": site_id,
            "union_id": union_id,
        },
        "github": {
            "username": os.environ.get("GH_USERNAME", "Tigherzhang"),
            "repo": os.environ.get("GH_REPO", "jd-deals"),
            "pages_url": os.environ.get("GH_PAGES_URL", "https://tigherzhang.github.io/jd-deals/"),
        },
        "push": {
            "schedule_time": "08:30",
            "max_items": int(os.environ.get("MAX_ITEMS", "10")),
            "min_price": int(os.environ.get("MIN_PRICE", "10")),
            "max_price": int(os.environ.get("MAX_PRICE", "100")),
            "price_upper_limit": int(os.environ.get("PRICE_UPPER_LIMIT", "500")),
        },
    }


def git_push(repo_dir):
    try:
        subprocess.run(["git", "-C", repo_dir, "add", "docs/data.json"], check=True, timeout=10)
        today = time.strftime("%Y-%m-%d")
        msg = f"更新商品数据 {today}"
        result = subprocess.run(["git", "-C", repo_dir, "commit", "-m", msg],
                                capture_output=True, text=True, timeout=10)
        if "nothing to commit" in result.stdout + result.stderr:
            print("[✓] 数据无变化，跳过推送")
            return
        subprocess.run(["git", "-C", repo_dir, "push"], check=True, timeout=60)
        print("[✓] 已推送到 GitHub")
    except subprocess.TimeoutExpired:
        print("[✗] Git 操作超时")
    except Exception as e:
        print(f"[✗] Git 错误: {e}")


def main():
    # 心跳日志：证明脚本被执行过
    LOG_DIR = os.path.join(PROJECT_DIR, "logs")
    os.makedirs(LOG_DIR, exist_ok=True)
    heartbeat_path = os.path.join(LOG_DIR, "heartbeat.log")
    with open(heartbeat_path, "a") as hf:
        hf.write(f"[START] {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ====== 防重入锁：同一天只允许跑一次 ======
    lock_file = os.path.join(LOG_DIR, ".daily.lock")
    today = time.strftime("%Y-%m-%d")
    if os.path.exists(lock_file):
        with open(lock_file, "r") as lf:
            locked_date = lf.read().strip()
        if locked_date == today:
            print(f"[⚠️] 今天已经跑过了（锁定日期: {locked_date}），跳过")
            with open(heartbeat_path, "a") as hf:
                hf.write(f"[SKIP:already-ran-today] {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            return
        else:
            # 锁是昨天的，过期了，删除
            os.remove(lock_file)

    # 写入锁
    with open(lock_file, "w") as lf:
        lf.write(today)
    print(f"[✓] 锁定: {today}")

    print("=" * 50)
    print(f"🛒 京东优惠精选 - 每日采集")
    print(f"📅 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    config = load_config()
    jd_config = config["jd_union"]
    push_config = config["push"]

    api = JdUnionAPI(
        app_key=jd_config["app_key"],
        secret_key=jd_config["secret_key"],
    )

    site_id = jd_config.get("site_id", "")

    channels = {27: "食品", 29: "家居生活", 10: "9.9包邮", 1: "好券商品", 22: "实时热销榜"}
    all_items = []
    for elite_id, name in channels.items():
        max_page = 8 if elite_id == 27 else 6 if elite_id == 29 else 2
        for page in range(1, max_page + 1):
            print(f"\n🔍 获取频道: {name} (eliteId={elite_id}, 第{page}页)")
            items = api.fetch_jingfen_goods(elite_id, page=page, page_size=50)
            for item in items:
                converted = api.convert_to_item(item, elite_id)
                if converted:
                    all_items.append(converted)
            print(f"  有效商品: {len(items)} 条")
            time.sleep(0.3)

    if not all_items:
        print("\n⚠️ 未获取到任何商品！跳过推送（保持上次数据不变）")
        with open(os.path.join(PROJECT_DIR, "logs", "heartbeat.log"), "a") as hf:
            hf.write(f"[END:0items-skipped] {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        print(f"\n🎉 完成！访问: {config['github']['pages_url']}")
        return

    print(f"\n📊 共获取 {len(all_items)} 条原始商品")

    # ====== 步骤2: 筛选 ======
    filtered = filter_products(all_items, push_config)
    print(f"🔍 筛选后 {len(filtered)} 条")

    max_items = push_config.get("max_items", 15)
    selected = rank_and_select(filtered, max_items)
    print(f"✅ 初步选取 {len(selected)} 条")

    # ====== 步骤3: 解析真实SKU并修正链接 ======
    # 核心原则：每个商品必须有sku_id，否则去重体系完全失效
    print("\n🔗 解析真实商品链接...")
    for item in selected:
        material_url = item.get("link", "")
        spuid = item.get("spuid", "")  # 从原始API数据保留的spuid
        current_sku = item.get("sku_id", "")

        # 尝试三种方式获取sku_id，优先级从高到低
        sku_found = False

        # 1. jingfen链接 → 302跳转解析真实SKU
        if material_url and "jingfen.jd.com" in material_url:
            real_sku = api.resolve_real_sku(material_url, spuid)
            if real_sku:
                item["link"] = f"https://item.jd.com/{real_sku}.html"
                item["sku_id"] = real_sku
                sku_found = True
                print(f"  ✅ {item['title'][:30]}... → {real_sku}")

        # 2. 已有item.jd.com链接 → 从链接提取
        if not sku_found:
            import re
            sku_match = re.search(r'item\.jd\.com/(\d+)\.html', material_url)
            if sku_match:
                item["sku_id"] = sku_match.group(1)
                sku_found = True

        # 3. spuid fallback
        if not sku_found and spuid and spuid.isdigit():
            item["sku_id"] = spuid
            sku_found = True

        # 4. 已有sku_id（来自convert_to_item）
        if not sku_found and current_sku:
            sku_found = True

        if sku_found:
            print(f"  ✓ {item['title'][:30]}... (sku_id={item['sku_id']})")
        else:
            print(f"  ⚠️ 无法获取sku_id: {item['title'][:30]}... (将仅靠标题去重)")
        time.sleep(0.3)

    # ====== 步骤4: 浏览器验价 ======
    print("\n🔍 浏览器验价中...")
    verified, failed, logs = verify_prices(selected, tolerance=0.5)
    verified_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    actually_verified = 0
    for item in verified:
        # 只有真正验到价格才标记 True，跳过/异常的保持原值（None 或 False）
        if item.get("_page_price_checked"):
            item["price_verified"] = True
            actually_verified += 1
        item["verified_at"] = verified_at
    for log in logs:
        print(log)
    selected = verified
    print(f"  ✅ 验价通过 {len(selected)} 条 (其中 {actually_verified} 条真实比对), ❌ 淘汰 {len(failed)} 条")
    if not selected:
        print("  ⚠️ 验价后无商品通过，跳过推送（保持上次数据不变）")
        with open(os.path.join(PROJECT_DIR, "logs", "heartbeat.log"), "a") as hf:
            hf.write(f"[END:0items-verified] {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        print(f"\n🎉 完成！访问: {config['github']['pages_url']}")
        return

    # ====== 步骤4: 生成推广链接... ======
    if site_id:
        print("\n🔗 生成推广链接...")
        for item in selected:
            original_link = item.get("link", "")
            if not original_link:
                continue
            promo_link = api.get_promotion_link(original_link, site_id)
            if promo_link:
                item["link"] = promo_link
                print(f"  ✅ {item['title'][:25]}... → {promo_link[:40]}")
            else:
                print(f"  ⚠️ 转链失败: {item['title'][:25]}... 保留原链接")
                # 转链失败时，清除可能过期的优惠券链接，避免用户点击报错
                item.pop("coupon_link", None)
                item["coupon_available"] = False
            time.sleep(0.2)
    else:
        print("\n⚠️ 未配置 site_id，跳过转链（链接不含佣金！）")

    # ====== 步骤4: 显示结果 ======
    print("\n" + "=" * 50)
    print("📋 今日优惠清单：")
    for i, item in enumerate(selected, 1):
        price = item.get("price", 0)
        orig = item.get("orig_price", 0)
        title = item.get("title", "?")[:30]
        discount = f"{(orig-price)/orig*100:.0f}折" if orig > price else ""
        link_preview = item.get("link", "")[:40]
        print(f"  {i}. {title} | ¥{price:.1f} {discount} | {link_preview}...")

    # ====== 步骤5: 生成数据 ======
    data = generate_data(selected)
    docs_dir = os.path.join(PROJECT_DIR, "docs")
    save_data(data, docs_dir)

    # 更新历史
    history = load_history()
    for item in selected:
        sku_id = item.get("sku_id", "")
        if sku_id:
            history.setdefault("sku_ids", []).append(sku_id)
        title = item.get("title", "")
        if title:
            history.setdefault("titles", []).append(title)
        # 保存品类核心词用于去重
        product_type = _extract_product_type(title, item["category"])
        if product_type:
            history.setdefault("product_types", []).append(f"{item['category']}|{product_type}")
    # 去重：同日重跑可能产生重复，用 dict 保持插入顺序
    history["sku_ids"] = list(dict.fromkeys(history["sku_ids"]))[-140:]
    history["titles"] = list(dict.fromkeys(history.get("titles", [])))[-140:]
    history["product_types"] = list(dict.fromkeys(history.get("product_types", [])))[-140:]
    today = time.strftime("%Y-%m-%d")
    history.setdefault("dates", {})[today] = len(selected)
    save_history(history)

    print("\n📤 推送到 GitHub...")
    git_push(PROJECT_DIR)

    with open(os.path.join(PROJECT_DIR, "logs", "heartbeat.log"), "a") as hf:
        hf.write(f"[END:{len(selected)}items] {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    print(f"\n🎉 完成！访问: {config['github']['pages_url']}")
    print("=" * 50)

    # ====== 步骤7: 结果验证 ======
    print("\n📋 自动核验结果...")
    verify_script = os.path.join(os.path.dirname(__file__), "verify_daily_result.py")
    if os.path.exists(verify_script):
        import subprocess
        result = subprocess.run(
            ["python3", verify_script],
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print("⚠️ 验证发现问题，请检查上述输出")
    else:
        print("  ⚠️ 验证脚本不存在，跳过")

    shutdown_on_complete()


def do_shutdown():
    """执行关机，先试无密码，失败则报错不关机"""
    import subprocess
    try:
        result = subprocess.run(
            ["sudo", "-n", "shutdown", "-h", "now"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return
        print(f"[⚠️] 关机失败: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        print("[⚠️] 关机超时")
    except Exception as e:
        print(f"[⚠️] 关机错误: {e}")


def shutdown_on_complete():
    """仅定时任务（launchd）完成后关机，手动执行不关机
    判断方式：检查环境变量 JD_PCS_DAILY_TASK
    - launchd plist 设置了此变量 → 定时任务 → 60秒后关机
    - 手动执行没有此变量 → 不关机
    """
    if os.environ.get("JD_PCS_DAILY_TASK") != "1":
        # 手动执行
        print("\n✅ 手动执行，不关机。如需关机请输入: sudo shutdown -h now")
        return

    # 定时任务模式：后台执行，60秒后关机
    print("\n📱 定时任务模式：60秒后自动关机")
    try:
        time.sleep(60)
        do_shutdown()
    except KeyboardInterrupt:
        print("✅ 已取消关机")


if __name__ == "__main__":
    main()
