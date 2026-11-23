#!/usr/bin/env python3
"""Собирает данные для страницы /vendo из Resources/.

Читает прототипы шаттлов (type: vessel), карты шаттлов, цены сущностей
(StaticPrice) и русские названия из локализации. Результат пишет в
app/data/vendo.json.

Запуск: python3 scripts/build-vendo-data.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import yaml

try:
    from yaml import CSafeLoader as _BaseLoader
except Exception:
    from yaml import SafeLoader as _BaseLoader


class ResourceLoader(_BaseLoader):
    """YAML-загрузчик, терпимый к тегам вида `!type:Something` из SS14."""


def _ignore_unknown_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


ResourceLoader.add_multi_constructor("!", _ignore_unknown_tag)

ROOT = Path(__file__).resolve().parent.parent
PROTOTYPES_DIR = ROOT / "Resources" / "Prototypes"
LOCALE_RU_DIR = ROOT / "Resources" / "Locale" / "ru-RU"
LOCALE_EN_DIR = ROOT / "Resources" / "Locale" / "en-US"
OUT = ROOT / "app" / "data" / "vendo.json"

# Main filter is StaticPrice > 0; additionally drop obvious non-scrap map infrastructure.
EXCLUDE_PROTO_PREFIXES = (
    "Wall", "ReinforcedWall", "Window", "Grille", "Cable", "Wire",
    "GasPipe", "GasPort", "GasVent", "GasMixer", "GasFilter",
    "GasDualPortVentPump", "GasPassiveVent", "GasPressurePump", "GasVolumePump",
    "GasValve", "AtmosDeviceFan", "Airlock", "Firelock",
    "Shutters", "BlastDoor", "Catwalk", "Plating", "Floor", "Lattice",
    "SpawnPoint", "WarpPoint", "Sign", "Poster", "Decal", "Puddle",
)
EXCLUDE_EXACT = {
    "", "Action", "DebugException", "DebugExceptionInitialize", "DebugExceptionStartup",
}


def load_ftl_names(locale_dir: Path, prefix: str) -> dict[str, str]:
    names: dict[str, str] = {}
    if not locale_dir.exists():
        return names
    for path in locale_dir.rglob("*.ftl"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in text.splitlines():
            if line.startswith(" ") or line.startswith("\t") or not line or line.startswith("#"):
                continue
            m = re.match(r"^([\w.\-]+)\s*=\s*(.+)$", line)
            if not m:
                continue
            key, value = m.groups()
            if key.startswith(prefix):
                names.setdefault(key.removeprefix(prefix), value.strip())
    return names


def load_yaml_file(path: Path):
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=ResourceLoader)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def get_static_price(entry: dict) -> float | None:
    for comp in entry.get("components") or []:
        if isinstance(comp, dict) and comp.get("type") == "StaticPrice":
            price = comp.get("price")
            if isinstance(price, (int, float)):
                return float(price)
    return None


def get_parents(entry: dict) -> list[str]:
    parent = entry.get("parent")
    if parent is None:
        return []
    if isinstance(parent, str):
        return [parent]
    if isinstance(parent, list):
        return [p for p in parent if isinstance(p, str)]
    return []


def resolve_price(proto_id: str, entries: dict[str, dict], cache: dict[str, float | None], visiting: set[str]) -> float | None:
    if proto_id in cache:
        return cache[proto_id]
    if proto_id in visiting:
        return None
    visiting.add(proto_id)
    entry = entries.get(proto_id)
    if entry is None:
        cache[proto_id] = None
        visiting.discard(proto_id)
        return None
    price = get_static_price(entry)
    if price is not None:
        cache[proto_id] = price
        visiting.discard(proto_id)
        return price
    for parent in get_parents(entry):
        p = resolve_price(parent, entries, cache, visiting)
        if p is not None:
            cache[proto_id] = p
            visiting.discard(proto_id)
            return p
    cache[proto_id] = None
    visiting.discard(proto_id)
    return None


def resolve_name(proto_id: str, entries: dict[str, dict], cache: dict[str, str | None], visiting: set[str]) -> str | None:
    if proto_id in cache:
        return cache[proto_id]
    if proto_id in visiting:
        return None
    visiting.add(proto_id)
    entry = entries.get(proto_id)
    if entry is None:
        cache[proto_id] = None
        visiting.discard(proto_id)
        return None
    name = entry.get("name")
    if isinstance(name, str) and name.strip():
        cache[proto_id] = name.strip()
        visiting.discard(proto_id)
        return cache[proto_id]
    for parent in get_parents(entry):
        n = resolve_name(parent, entries, cache, visiting)
        if n is not None:
            cache[proto_id] = n
            visiting.discard(proto_id)
            return n
    cache[proto_id] = None
    visiting.discard(proto_id)
    return None


def is_excluded_proto(proto_id: str) -> bool:
    if proto_id in EXCLUDE_EXACT:
        return True
    for prefix in EXCLUDE_PROTO_PREFIXES:
        if proto_id.startswith(prefix):
            return True
    return False


def parse_map_protos(map_path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    try:
        text = map_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return counts
    for m in re.finditer(r"^\s*-?\s*proto:\s*['\"]?([^'\"\n#]+?)['\"]?\s*$", text, re.MULTILINE):
        proto = m.group(1).strip()
        if proto:
            counts[proto] += 1
    return counts


def resolve_map_path(shuttle_path: str) -> Path | None:
    rel = shuttle_path.lstrip("/")
    candidate = ROOT / "Resources" / rel
    if candidate.exists():
        return candidate
    return None


def main() -> None:
    print("Loading vessels...")
    vessels: list[dict] = []
    for path in PROTOTYPES_DIR.rglob("*.yml"):
        # vessels live in Shipyard dirs; cheap path filter
        pstr = str(path)
        if "Shipyard" not in pstr:
            continue
        for entry in load_yaml_file(path):
            if entry.get("type") == "vessel" and isinstance(entry.get("id"), str):
                vessels.append(entry)
    print(f"  vessels: {len(vessels)}")

    print("Loading maps and collecting item protos...")
    vessel_maps: list[tuple[dict, Counter[str]]] = []
    needed: set[str] = set()
    missing_maps: list[str] = []
    for vessel in vessels:
        shuttle_path = vessel.get("shuttlePath")
        if not isinstance(shuttle_path, str):
            continue
        map_path = resolve_map_path(shuttle_path)
        if map_path is None:
            missing_maps.append(f"{vessel.get('id')}: {shuttle_path}")
            continue
        counts = parse_map_protos(map_path)
        vessel_maps.append((vessel, counts))
        for proto_id in counts:
            if not is_excluded_proto(proto_id):
                needed.add(proto_id)
    if missing_maps:
        print(f"  WARN: {len(missing_maps)} missing maps")
        for m in missing_maps[:10]:
            print(f"    {m}")
    print(f"  maps: {len(vessel_maps)}, unique item protos: {len(needed)}")

    print("Loading entity prototypes...")
    all_entries: dict[str, dict] = {}
    for path in PROTOTYPES_DIR.rglob("*.yml"):
        for entry in load_yaml_file(path):
            if not isinstance(entry, dict):
                continue
            etype = entry.get("type")
            eid = entry.get("id")
            if not isinstance(eid, str):
                continue
            # Keep entities and any proto that may be a parent (abstract, etc.)
            if etype == "entity" or etype == "construction" or "components" in entry or "parent" in entry:
                if etype != "vessel":
                    all_entries[eid] = entry
    print(f"  entity-like protos: {len(all_entries)}")

    print("Loading locale...")
    ru_ent = load_ftl_names(LOCALE_RU_DIR, "ent-")
    en_ent = load_ftl_names(LOCALE_EN_DIR, "ent-")

    print("Building shuttle data...")
    price_cache: dict[str, float | None] = {}
    name_cache: dict[str, str | None] = {}
    seen_item_protos: set[str] = set()
    shuttle_items: list[dict] = []

    for vessel, counts in vessel_maps:
        vid = vessel.get("id")
        items: list[dict] = []
        appraisal = 0.0
        for proto_id, count in counts.items():
            price = resolve_price(proto_id, all_entries, price_cache, set())
            if price is not None and price > 0:
                appraisal += price * count
            if is_excluded_proto(proto_id):
                continue
            if price is None or price <= 0:
                continue
            seen_item_protos.add(proto_id)
            items.append({"id": proto_id, "count": count})
        items.sort(key=lambda x: (-(resolve_price(x["id"], all_entries, price_cache, set()) or 0), x["id"]))

        shuttle_items.append({
            "id": vid,
            "name": vessel.get("name") or vid,
            "price": int(vessel.get("price") or 0),
            "appraisal": int(appraisal),
            "category": str(vessel.get("category") or ""),
            "group": str(vessel.get("group") or ""),
            "classes": vessel.get("class") or [],
            "engines": vessel.get("engine") or [],
            "shuttlePath": vessel.get("shuttlePath"),
            "purchasable": bool(vessel.get("purchasable", True)),
            "items": items,
        })

    shuttle_items.sort(key=lambda s: (s["name"] or "").lower())

    catalog: list[dict] = []
    for proto_id in sorted(seen_item_protos):
        price = resolve_price(proto_id, all_entries, price_cache, set()) or 0
        proto_name = resolve_name(proto_id, all_entries, name_cache, set()) or proto_id
        ru = ru_ent.get(proto_id) or proto_name
        en = en_ent.get(proto_id) or proto_name
        catalog.append({
            "id": proto_id,
            "name": ru,
            "nameEn": en,
            "price": int(price) if price == int(price) else round(price, 2),
        })
    catalog.sort(key=lambda x: (x["name"] or "").lower())

    payload = {
        "sellRate": 0.85,
        "shuttles": shuttle_items,
        "catalog": catalog,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(shuttle_items)} shuttles, {len(catalog)} catalog items")


if __name__ == "__main__":
    main()
