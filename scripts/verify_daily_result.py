#!/usr/bin/env python3
"""
每日任务结果验证脚本
用法: python3 scripts/verify_daily_result.py [data.json路径]
"""

import json
from difflib import SequenceMatcher
import re
import sys
from pathlib import Path
from collections import Counter

PROJECT_DIR = Path(__file__).resolve().parent.parent

def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else PROJECT_DIR / "docs" / "data.json"
    with open(data_path) as f:
        data = json.load(f)

    items = data['items']
    total = len(items)
    issues = []

    print("=" * 50)
    print("📋 每日任务结果核验")
    print("=" * 50)
    print()

    # 1. SKU 重复检查
    skus = [item['link'].split('/')[-1].replace('.html', '') for item in items]
    sku_counts = Counter(skus)
    dupes = {s: c for s, c in sku_counts.items() if c > 1}
    if dupes:
        issues.append(f"SKU 重复: {dupes}")
        print(f"❌ SKU 重复: {dupes}")
    else:
        print(f"✅ 无 SKU 重复 ({total} 个独立商品)")

    # 2. 品牌去重检查
    brands = []
    for item in items:
        title = item.get('title', '')
        # 提取前几个字作为品牌标识
        brand = title[:6] if len(title) > 6 else title
        brands.append(brand)
    brand_counts = Counter(brands)
    brand_dupes = {b: c for b, c in brand_counts.items() if c > 1 and c < len(items)}
    # 只报同品牌超过1个的
    # 注意：这里不是精确的品牌提取，只是近似检查
    dupes_exact = {}
    for item in items:
        title = item['title']
        # 精确提取品牌（括号中的英文品牌）
        import re
        m = re.match(r'^([A-Za-z一-鿿]{2,6})', title)
        if m:
            b = m.group(1)
            if b not in dupes_exact:
                dupes_exact[b] = 0
            dupes_exact[b] += 1
    serious_dupes = {b: c for b, c in dupes_exact.items() if c > 1}
    if serious_dupes:
        issues.append(f"疑似品牌重复: {serious_dupes}")
        print(f"⚠️ 疑似品牌重复: {serious_dupes}")
    else:
        print(f"✅ 品牌不重复")

    # 3. 价格验证检查
    verified = sum(1 for item in items if item.get('price_verified'))
    not_verified = total - verified
    if not_verified > 0:
        print(f"⚠️ {not_verified}/{total} 个商品未经京东页面验证（price_verified=False）")
    else:
        print(f"✅ 全部商品已标记验证通过")

    # 4. 分类分布检查
    cats = Counter(item.get('category', '未知') for item in items)
    print(f"\n📊 品类分布:")
    for cat, count in cats.most_common():
        pct = count / total * 100
        bar = '█' * int(pct / 5)
        print(f"  {cat:6s} {count:2d}个 ({pct:3.0f}%) {bar}")

    food_pct = cats.get('食品', 0) / total * 100
    daily_pct = cats.get('日用品', 0) / total * 100
    baby_pct = cats.get('母婴', 0) / total * 100
    health_pct = cats.get('保健品', 0) / total * 100

    if food_pct > 60:
        issues.append(f"食品占比 {food_pct:.0f}% 过高（>60%）")
        print(f"\n⚠️ 食品占比 {food_pct:.0f}% 过高")
    if daily_pct + baby_pct < 30:
        issues.append(f"日用品+母婴占比仅 {daily_pct+baby_pct:.0f}%（<30%）")
        print(f"⚠️ 日用品+母婴占比仅 {daily_pct+baby_pct:.0f}%")

    # 5. 每个商品的可疑分类抽查
    sus_kw_food = ['驱蚊', '爽身', '沐浴', '洗发', '洗衣', '牙刷', '牙膏', '纸巾', '马桶']
    sus_kw_health = ['维生素', '钙片', '蛋白粉', '鱼油']
    for item in items:
        title = item['title']
        cat = item.get('category', '')
        for kw in sus_kw_food:
            if kw in title and cat == '食品':
                issues.append(f"可疑分类: [{cat}] {title[:40]}... 含「{kw}」")
                print(f"❌ 可疑分类: [{cat}] {title[:40]}... 含「{kw}」")
        for kw in sus_kw_health:
            if kw in title and cat not in ('保健品',):
                issues.append(f"可疑分类: [{cat}] {title[:40]}... 含「{kw}」")


def check_dedup_effectiveness(data, history):
    """检查去重有效性"""
    issues = []
    
    items = data['items']
    total = len(items)
    
    print("\n=== 去重有效性检查 ===")
    
    # 1. 检查sku_id完整性
    no_sku = [item for item in items if not item.get('sku_id')]
    if no_sku:
        issues.append(f"sku_id缺失: {len(no_sku)}/{total}个商品")
        print(f"⚠️ sku_id缺失: {len(no_sku)}/{total}个商品")
        for item in no_sku[:3]:
            print(f"   - {item['title'][:40]}...")
    else:
        print(f"✅ sku_id完整性: {total}/{total}")
    
    # 2. 检查product_type覆盖率
    # 需要从history中计算
    product_types = history.get('product_types', [])
    sku_ids = history.get('sku_ids', [])
    
    if len(product_types) < len(sku_ids) * 0.8:
        issues.append(f"product_types覆盖率低: {len(product_types)}/{len(sku_ids)} ({len(product_types)/len(sku_ids)*100:.0f}%)")
        print(f"⚠️ product_types覆盖率: {len(product_types)}/{len(sku_ids)} ({len(product_types)/len(sku_ids)*100:.0f}%)")
    else:
        print(f"✅ product_types覆盖率: {len(product_types)}/{len(sku_ids)} ({len(product_types)/len(sku_ids)*100:.0f}%)")
    
    # 3. 检查今日商品是否与历史重复
    today_skus = set(item.get('sku_id', '') for item in items if item.get('sku_id'))
    history_skus = set(sku_ids[-140:]) if sku_ids else set()
    
    dupes = today_skus & history_skus
    if dupes:
        issues.append(f"发现重复SKU: {dupes}")
        print(f"❌ 发现重复SKU: {dupes}")
    else:
        print(f"✅ 今日商品与历史无SKU重复")
    
    # 4. 检查标题相似度
    def clean_title(t):
        t = re.sub(r'[【\[(\(<].*?([】\)\)>]|\$)', '', t).strip()
        t = re.sub(r'\s+', '', t)
        return t
    
    today_titles = [clean_title(item['title']) for item in items]
    history_titles = [clean_title(t) for t in history.get('titles', [])[-140:]]
    
    title_dupes = []
    for i, t1 in enumerate(today_titles):
        for t2 in history_titles:
            if t1 and t2:
                sim = SequenceMatcher(None, t1, t2).ratio()
                if sim >= 0.80:
                    title_dupes.append((items[i]['title'][:40], t2[:40], sim))
                    break
    
    if title_dupes:
        issues.append(f"发现相似标题: {len(title_dupes)}个")
        print(f"⚠️ 发现相似标题: {len(title_dupes)}个")
        for t1, t2, sim in title_dupes[:3]:
            print(f"   - '{t1}...' vs '{t2}...' (相似度{sim:.2f})")
    else:
        print(f"✅ 今日商品与历史无标题重复")
    
    return issues

    # 在main函数中调用
    history_path = PROJECT_DIR / "docs" / "history.json"
    history = {}
    if history_path.exists():
        with open(history_path) as f:
            history = json.load(f)
    
    dedup_issues = check_dedup_effectiveness(data, history)
    issues.extend(dedup_issues)
    
    # 总结
    print()
    print("=" * 50)
    if issues:
        print(f"❌ 发现 {len(issues)} 个问题：")
        for i, issue in enumerate(issues[:5], 1):
            print(f"  {i}. {issue}")
        sys.exit(1)
    else:
        print("✅ 全部核验通过")
        sys.exit(0)

if __name__ == "__main__":
    main()
