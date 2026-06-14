#!/usr/bin/env python3
"""
京东副业 PCS - 每日主脚本
获取优惠商品 → 筛选 → 生成网页 → git push
"""
import json
import os
import sys
import subprocess
import time

# 添加 scripts 目录到 path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from jd_api import JdUnionAPI
from product_filter import filter_products, rank_and_select, load_history, save_history
from page_generator import generate_data, save_data


def load_config():
    """加载配置文件"""
    config_path = os.path.join(PROJECT_DIR, "config.json")
    if not os.path.exists(config_path):
        print(f"[✗] 配置文件不存在: {config_path}")
        sys.exit(1)
    with open(config_path, "r") as f:
        return json.load(f)


def git_push(repo_dir):
    """将更改推送到 GitHub"""
    try:
        # git add
        subprocess.run(["git", "-C", repo_dir, "add", "docs/data.json"], check=True, timeout=10)

        # git commit
        today = time.strftime("%Y-%m-%d")
        msg = f"更新商品数据 {today}"
        result = subprocess.run(["git", "-C", repo_dir, "commit", "-m", msg],
                                capture_output=True, text=True, timeout=10)
        # 如果没有变化，跳过push
        if "nothing to commit" in result.stdout + result.stderr:
            print("[✓] 数据无变化，跳过推送")
            return

        # git push
        subprocess.run(["git", "-C", repo_dir, "push"], check=True, timeout=60)
        print("[✓] 已推送到 GitHub")
    except subprocess.TimeoutExpired:
        print("[✗] Git 操作超时")
    except Exception as e:
        print(f"[✗] Git 错误: {e}")


def main():
    print("=" * 50)
    print(f"🛒 京东优惠精选 - 每日采集")
    print(f"📅 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 加载配置
    config = load_config()
    jd_config = config["jd_union"]
    push_config = config["push"]

    # 初始化 API
    api = JdUnionAPI(
        app_key=jd_config["app_key"],
        secret_key=jd_config["secret_key"],
    )

    # 要查询的频道 - 每频道取2页，增加商品多样性
    channels = {
        27: "食品",
        29: "家居生活",
        10: "9.9包邮",
        1: "好券商品",
        22: "实时热销榜",
    }
    pages = [1, 2]  # 每个频道取前2页

    all_items = []

    # 逐频道获取商品
    for elite_id, name in channels.items():
        for page in pages:
            print(f"\n🔍 获取频道: {name} (eliteId={elite_id}, 第{page}页)")
            items = api.fetch_jingfen_goods(elite_id, page=page, page_size=50)
            for item in items:
                converted = api.convert_to_item(item, elite_id)
                if converted:
                    all_items.append(converted)
            print(f"  有效商品: {len(items)} 条")
            # 避免请求太快
            time.sleep(0.3)

    # 如果没获取到任何商品，生成空数据
    if not all_items:
        print("\n⚠️ 未获取到任何商品！")
        print("可能原因：")
        print("  1. API密钥未激活（需在 union.jd.com 申请接口权限）")
        print("  2. 接口权限审核中（审核约1-2周）")
        print("  3. 请求参数有误")

        # 生成示例数据供测试网页
        print("\n📝 生成空的 data.json...")
        data = generate_data([])
        save_data(data, os.path.join(PROJECT_DIR, "docs"))
        return

    print(f"\n📊 共获取 {len(all_items)} 条原始商品")

    # 筛选
    filtered = filter_products(all_items, push_config)
    print(f"🔍 筛选后 {len(filtered)} 条")

    # 排序 + 选取
    max_items = push_config.get("max_items", 10)
    selected = rank_and_select(filtered, max_items)
    print(f"✅ 最终选取 {len(selected)} 条")

    # 显示选取结果
    print("\n" + "=" * 50)
    print("📋 今日优惠清单：")
    for i, item in enumerate(selected, 1):
        price = item.get("price", 0)
        orig = item.get("orig_price", 0)
        title = item.get("title", "?")[:30]
        discount = f"{(orig-price)/orig*100:.0f}折" if orig > price else ""
        print(f"  {i}. {title} | ¥{price:.1f} {discount}")

    # 生成数据文件
    data = generate_data(selected)
    docs_dir = os.path.join(PROJECT_DIR, "docs")
    save_data(data, docs_dir)

    # 更新历史记录
    history = load_history()
    for item in selected:
        sku_id = item.get("sku_id", "")
        if sku_id:
            history.setdefault("sku_ids", []).append(sku_id)
    # 只保留最近30天的
    history["sku_ids"] = history["sku_ids"][-300:]
    today = time.strftime("%Y-%m-%d")
    history.setdefault("dates", {})[today] = len(selected)
    save_history(history)

    # 推送到 GitHub
    print("\n📤 推送到 GitHub...")
    # 为自动推送添加 GIT_SSH_COMMAND 环境变量（避免交互式确认）
    git_push(PROJECT_DIR)

    print(f"\n🎉 完成！访问: {config['github']['pages_url']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
