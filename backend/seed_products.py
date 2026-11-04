"""
change-skin 商城后端 · 商品种子导入

从 index.html 的静态商品卡里抽出商品，灌进 products 表。
这样前端改成调 API 之后，商品内容与原来完全一致（不丢数据）。

用法：
    python seed_products.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import db

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

# 中文名 → slug / 分类 / 副标题 的映射（短名用于 URL 与 category 筛选）
CATEGORY_MAP = {
    # equipment 装备
    "便携式电磁炮": ("railgun", "equipment"),
    "全感 VR 头显": ("vr-headset", "equipment"),
    "青芒发光太刀": ("katana", "equipment"),
    "二次元客制化键盘": ("keyboard", "equipment"),
    "星辉魔法杖": ("magic-staff", "equipment"),
    "全息投影终端": ("hologram-terminal", "equipment"),
    "侦察无人机": ("drone", "equipment"),
    "能量光剑": ("lightsaber", "equipment"),
    "像素复古掌机": ("retro-handheld", "equipment"),
    "机械义肢": ("mech-arm", "equipment"),
    "精灵长弓": ("elf-bow", "equipment"),
    # figure 手办模型
    "精品少女手办": ("figure", "figure"),
    "合金机甲模型": ("mecha-model", "figure"),
    "Q 版粘土人": ("nendoroid", "figure"),
    "亚克力立牌套装": ("acrylic-stand", "figure"),
    # apparel 服饰
    "JK 水手服": ("jk-uniform", "apparel"),
    "和风巫女服": ("miko-outfit", "apparel"),
    "黑革过膝长靴": ("boots", "apparel"),
    "经典女仆装": ("maid-outfit", "apparel"),
    "樱花纹和风羽织": ("haori", "apparel"),
    "限定版运动鞋": ("sneaker", "apparel"),
    # accessory 配件
    "透明橱窗痛包": ("itabag", "accessory"),
    "猫耳降噪耳机": ("cat-ear-headset", "accessory"),
    "等身抱枕套": ("dakimakura", "accessory"),
    "朱纹狐狸面具": ("fox-mask", "accessory"),
    "狐耳毛绒玩偶": ("fox-plush", "accessory"),
    "魔法少女变身手镯": ("henshin-bracelet", "accessory"),
    "二次元马克杯": ("mug", "accessory"),
    "星愿香水": ("perfume", "accessory"),
    "魔法阵挂钟": ("wall-clock", "accessory"),
    # decor 装饰
    "和风挂轴": ("wall-scroll", "decor"),
    # service 服务
    "痛车定制服务": ("itasha", "service"),
    "痛车贴膜套装": ("car-wrap", "service"),
}


def parse_products() -> list[dict]:
    """从 index.html 提取商品卡。"""
    html = INDEX.read_text(encoding="utf-8")
    # 匹配每个 <li class="product-item"> ... </li>
    blocks = re.findall(
        r'<li class="product-item[^"]*"[^>]*>(.*?)</li>',
        html,
        re.S,
    )
    if not blocks:
        blocks = re.findall(
            r'<li[^>]*class="[^"]*product-item[^"]*"[^>]*>(.*?)</li>',
            html,
            re.S,
        )

    out: list[dict] = []
    seen: set[str] = set()

    for b in blocks:
        name_m = re.search(r'<h3 class="product-name"[^>]*>(.*?)</h3>', b, re.S)
        img_m = re.search(r'<img[^>]+src="([^"]+)"', b)
        price_m = re.search(r'<data value="(\d+)"', b)
        meta_m = re.search(r'<p class="product-meta"[^>]*>(.*?)</p>', b, re.S)
        badge_m = re.search(r'<span class="[^"]*product-badge[^"]*">(.*?)</span>', b, re.S)

        if not (name_m and img_m and price_m):
            continue

        name = re.sub(r"<[^>]+>", "", name_m.group(1)).strip()
        if not name or name in seen:
            continue
        seen.add(name)

        slug, category = CATEGORY_MAP.get(name, (re.sub(r"\W+", "-", name).strip("-"), "other"))
        image = img_m.group(1).split("/")[-1]

        meta = re.sub(r"<[^>]+>", "", meta_m.group(1)).strip() if meta_m else ""
        sales_m = re.search(r"月销\s*([\d.]+)(k)?", meta)
        rating_m = re.search(r"好评\s*([\d.]+)%", meta)

        sales = 0
        if sales_m:
            v = float(sales_m.group(1))
            sales = int(v * 1000) if sales_m.group(2) else int(v)

        rating = float(rating_m.group(1)) if rating_m else 0.0

        badge_raw = re.sub(r"<[^>]+>", "", badge_m.group(1)).strip() if badge_m else ""
        badge = {"热销": "hot", "NEW": "new", "新品": "new", "特惠": "sale", "折扣": "sale"}.get(badge_raw, "")

        out.append(
            {
                "slug": slug,
                "name": name,
                "description": meta,
                "price_cents": int(price_m.group(1)) * 100,
                "category": category,
                "image": image,
                "badge": badge or None,
                "monthly_sales": sales,
                "rating": rating,
                "stock": 999,
                "sort_order": len(out),
            }
        )

    return out


def main() -> int:
    products = parse_products()
    print(f"从 index.html 解析到 {len(products)} 个商品")

    if not products:
        print("没有解析到商品，退出", file=sys.stderr)
        return 1

    inserted = 0
    for p in products:
        db.execute(
            """
            INSERT INTO products
                (slug, name, description, price_cents, category, image,
                 badge, monthly_sales, rating, stock, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                description = VALUES(description),
                price_cents = VALUES(price_cents),
                category = VALUES(category),
                image = VALUES(image),
                badge = VALUES(badge),
                monthly_sales = VALUES(monthly_sales),
                rating = VALUES(rating),
                sort_order = VALUES(sort_order)
            """,
            (
                p["slug"], p["name"], p["description"], p["price_cents"],
                p["category"], p["image"], p["badge"], p["monthly_sales"],
                p["rating"], p["stock"], p["sort_order"],
            ),
        )
        inserted += 1
        print(f"  + {p['name']:<20} CNY{p['price_cents']/100:>8.2f}  [{p['category']}]")

    total = db.fetch_one("SELECT COUNT(*) AS n FROM products")
    print(f"\n写入 {inserted} 条，库内共 {total['n']} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
