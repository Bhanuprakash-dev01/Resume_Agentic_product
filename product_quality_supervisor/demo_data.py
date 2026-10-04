from __future__ import annotations

import random
from typing import Dict, Iterable, List, Tuple

from .models import PolicyCitation, ProductRecord


CATEGORY_RULES: Dict[str, Dict[str, object]] = {
    "smartphones": {
        "required_fields": ["brand", "model", "color", "storage", "price"],
        "canonical_category": "smartphones",
        "brand_aliases": {"apple": "Apple", "samsung": "Samsung", "google": "Google"},
    },
    "laptops": {
        "required_fields": ["brand", "model", "display_size", "ram", "storage", "price"],
        "canonical_category": "laptops",
        "brand_aliases": {"dell": "Dell", "lenovo": "Lenovo", "asus": "ASUS"},
    },
    "home_appliances": {
        "required_fields": ["brand", "model", "power_rating", "price"],
        "canonical_category": "home_appliances",
        "brand_aliases": {"whirlpool": "Whirlpool", "lg": "LG", "philips": "Philips"},
    },
    "shoes": {
        "required_fields": ["brand", "size", "color", "price"],
        "canonical_category": "shoes",
        "brand_aliases": {"nike": "Nike", "adidas": "Adidas", "puma": "Puma"},
    },
}

POLICY_DOCS: List[PolicyCitation] = [
    PolicyCitation(
        title="Catalog Naming Standard",
        source="Catalog Policy Handbook",
        citation="Titles must use a canonical brand name and normalized storage units. Use `128 GB` not `128` or `128gb` when storage is specified.",
        section="Naming",
    ),
    PolicyCitation(
        title="Taxonomy Requirements",
        source="Marketplace Taxonomy Manual",
        citation="Products must map to the validated taxonomy leaf node; a smartphone cannot be classified as `Computer Accessories`.",
        section="Taxonomy",
    ),
    PolicyCitation(
        title="Color Attribute Guidance",
        source="Product Attribute Standards",
        citation="Color values must follow canonical enumerations such as Black, White, Silver, Blue, Red, Pink, Green, Brown, Gold, Gray.",
        section="Attributes",
    ),
    PolicyCitation(
        title="Price Validation",
        source="Data Quality SOP",
        citation="Price values must be numeric and should not exceed category-specific business ranges without review.",
        section="Pricing",
    ),
    PolicyCitation(
        title="Duplicate Review Policy",
        source="Master Data Governance",
        citation="Near-duplicate products with identical GTIN, model, and brand should be grouped for review; uncertain matches cannot be auto-merged.",
        section="Duplicates",
    ),
]


def canonical_brand(value: str) -> str:
    aliases = {
        "apple": "Apple",
        "iphone": "Apple",
        "samsung": "Samsung",
        "google": "Google",
        "asus": "ASUS",
        "dell": "Dell",
        "lenovo": "Lenovo",
        "whirlpool": "Whirlpool",
        "lg": "LG",
        "philips": "Philips",
        "nike": "Nike",
        "adidas": "Adidas",
        "puma": "Puma",
    }
    return aliases.get(value.lower(), value.title())


def normalize_color(value: str) -> str:
    mapping = {
        "blk": "Black",
        "black": "Black",
        "wt": "White",
        "white": "White",
        "silver": "Silver",
        "silv": "Silver",
        "blue": "Blue",
        "red": "Red",
        "gold": "Gold",
        "gray": "Gray",
        "grey": "Gray",
    }
    if not value:
        return ""
    return mapping.get(value.lower(), value.title())


def normalize_storage(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace(" ", "")
    if text.endswith("gb") and text[:-2].isdigit():
        return f"{int(text[:-2])} GB"
    if text.endswith("mb") and text[:-2].isdigit():
        return f"{int(text[:-2])} MB"
    if text.isdigit():
        return f"{int(text)} GB"
    return value


def build_category_examples() -> Dict[str, List[Dict[str, object]]]:
    return {
        "smartphones": [
            {"title": "Apple iPhone 15 128GB - Black", "brand": "Apple", "model": "iPhone 15", "color": "Black", "storage": "128 GB", "price": 799},
            {"title": "Samsung Galaxy S24 256GB - Silver", "brand": "Samsung", "model": "Galaxy S24", "color": "Silver", "storage": "256 GB", "price": 899},
            {"title": "Google Pixel 8 128GB - White", "brand": "Google", "model": "Pixel 8", "color": "White", "storage": "128 GB", "price": 699},
        ],
        "laptops": [
            {"title": "Dell XPS 13 512GB Laptop - Silver", "brand": "Dell", "model": "XPS 13", "display_size": "13.4 in", "ram": "16 GB", "storage": "512 GB", "price": 1299},
            {"title": "Lenovo Yoga 7 14 1TB - Black", "brand": "Lenovo", "model": "Yoga 7 14", "display_size": "14 in", "ram": "16 GB", "storage": "1 TB", "price": 1499},
            {"title": "ASUS Zenbook 14 512GB - Gray", "brand": "ASUS", "model": "Zenbook 14", "display_size": "14 in", "ram": "16 GB", "storage": "512 GB", "price": 1199},
        ],
        "home_appliances": [
            {"title": "Whirlpool Refrigerator 22 cu ft - White", "brand": "Whirlpool", "model": "Top-Freezer", "power_rating": "350 W", "price": 899},
            {"title": "LG Washer 4.5 cu ft - Silver", "brand": "LG", "model": "Front Load", "power_rating": "600 W", "price": 749},
            {"title": "Philips Air Fryer 5.8 qt - Black", "brand": "Philips", "model": "Air Fryer", "power_rating": "1500 W", "price": 119},
        ],
        "shoes": [
            {"title": "Nike Air Max 270 Running Shoe - Black/White", "brand": "Nike", "model": "Air Max 270", "size": "9 US", "color": "Black", "price": 149},
            {"title": "Adidas Ultraboost 23 - Grey", "brand": "Adidas", "model": "Ultraboost 23", "size": "8 US", "color": "Gray", "price": 169},
            {"title": "Puma Velocity Nitro - Red", "brand": "Puma", "model": "Velocity Nitro", "size": "10 US", "color": "Red", "price": 130},
        ],
    }


def generate_demo_products(total: int = 720) -> List[ProductRecord]:
    rng = random.Random(42)
    category_examples = build_category_examples()
    products: List[ProductRecord] = []
    product_counter = 0

    def make_base(category: str, exemplar: Dict[str, object], index: int) -> ProductRecord:
        nonlocal product_counter
        product_counter += 1
        sku = f"SKU-{category}-{index:04d}"
        title = str(exemplar["title"])
        brand = str(exemplar["brand"])
        return ProductRecord(
            sku=sku,
            title=title,
            category=category,
            brand=brand,
            color=exemplar.get("color"),
            storage=exemplar.get("storage"),
            price=exemplar.get("price"),
            weight=exemplar.get("weight"),
            dimensions=exemplar.get("dimensions"),
            description=f"{brand} {title} in a clean, valid catalog entry.",
            gtin=f"{category.upper()}-{index:012d}",
            model=str(exemplar.get("model", "Generic")),
            metadata={"source": "synthetic_demo"},
        )

    for category, examples in category_examples.items():
        for idx, exemplar in enumerate(examples, start=1):
            products.append(make_base(category, exemplar, idx))

    category_names = list(category_examples.keys())
    while len(products) < total:
        category = rng.choice(category_names)
        exemplar = rng.choice(category_examples[category])
        product = make_base(category, exemplar, len(products) + 1)
        products.append(product)

    # Create intentionally corrupted records and duplicates.
    for idx in range(1, min(120, total // 5 + 1)):
        category = rng.choice(category_names)
        exemplar = rng.choice(category_examples[category])
        unsafe = make_base(category, exemplar, len(products) + 1)
        unsafe.title = unsafe.title.replace("-", " ")
        unsafe.brand = rng.choice([unsafe.brand.lower(), "APPLE", "apple"])
        unsafe.color = rng.choice([None, "blk", "", "Blue", "black"])
        unsafe.storage = rng.choice(["128", "128gb", "128 GB", "256 gb", None])
        unsafe.price = rng.choice(["79999", 79999, -50, 123456789])
        unsafe.description = "" if idx % 4 == 0 else unsafe.description
        unsafe.metadata["quality_issue"] = "synthetic_corruption"
        products.append(unsafe)

    # Create a limited duplicate ring.
    seed = ProductRecord(
        sku="SKU-DUP-001",
        title="Apple iPhone 15 128GB - Black",
        category="smartphones",
        brand="Apple",
        color="Black",
        storage="128 GB",
        price=799,
        description="Apple iPhone 15 128GB - Black.",
        gtin="DUP-000000000001",
        model="iPhone 15",
        metadata={"source": "duplicate_group"},
    )
    products.append(seed)
    for i in range(1, 6):
        dup = ProductRecord(
            sku=f"SKU-DUP-{i + 1:03d}",
            title=f"Apple iphone 15 blk {128 if i % 2 == 0 else 256}",
            category="Computer Accessories" if i % 2 == 0 else "smartphones",
            brand="apple" if i % 2 == 0 else "Apple",
            color="blk" if i % 2 == 0 else "Black",
            storage=f"{128 if i % 2 == 0 else 256}GB" if i % 2 == 0 else "256 GB",
            price=79999 if i % 2 == 0 else 899,
            description="Slightly altered title for duplicate detection.",
            gtin="DUP-000000000001",
            model="iPhone 15",
            metadata={"source": "near_duplicate"},
        )
        products.append(dup)

    # Trim to target count while leaving a meaningful issue mix.
    return products[:total]


def product_lookup_map(products: Iterable[ProductRecord]) -> Dict[str, ProductRecord]:
    return {product.sku: product for product in products}
