#!/usr/bin/env python3
"""Собирает данные для страницы /vendo из Resources/.

Читает прототипы шаттлов (type: vessel), карты шаттлов, цены сущностей
(по формуле PricingSystem.GetEstimatedPrice из игры) и русские названия из
локализации. Результат пишет в app/data/vendo.json.

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

# Main filter is price > 0; additionally drop obvious non-scrap map infrastructure.
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


def get_comp(entry: dict, comp_type: str) -> dict | None:
    for comp in entry.get("components") or []:
        if isinstance(comp, dict) and comp.get("type") == comp_type:
            return comp
    return None


def has_comp(entry: dict, comp_type: str) -> bool:
    return get_comp(entry, comp_type) is not None


def get_parents(entry: dict) -> list[str]:
    parent = entry.get("parent")
    if parent is None:
        return []
    if isinstance(parent, str):
        return [parent]
    if isinstance(parent, list):
        return [p for p in parent if isinstance(p, str)]
    return []


def is_excluded_proto(proto_id: str) -> bool:
    if proto_id in EXCLUDE_EXACT:
        return True
    for prefix in EXCLUDE_PROTO_PREFIXES:
        if proto_id.startswith(prefix):
            return True
    return False


def as_float(v, default: float = 0.0) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return default


def as_int(v, default: int = 0) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    return default


def load_material_prices(prototypes_dir: Path) -> dict[str, float]:
    prices: dict[str, float] = {}
    for path in prototypes_dir.rglob("*.yml"):
        for entry in load_yaml_file(path):
            if not isinstance(entry, dict) or entry.get("type") != "material":
                continue
            mid = entry.get("id")
            price = entry.get("price")
            if isinstance(mid, str) and isinstance(price, (int, float)):
                prices[mid] = float(price)
    return prices


def load_reagent_prices(prototypes_dir: Path) -> dict[str, float]:
    prices: dict[str, float] = {}
    for path in prototypes_dir.rglob("*.yml"):
        for entry in load_yaml_file(path):
            if not isinstance(entry, dict) or entry.get("type") != "reagent":
                continue
            rid = entry.get("id")
            ppu = entry.get("pricePerUnit")
            if isinstance(rid, str) and isinstance(ppu, (int, float)):
                prices[rid] = float(ppu)
    return prices


def resolve_comp(proto_id: str, comp_type: str, entries: dict[str, dict], cache: dict[str, dict | None], visiting: set[str]) -> dict | None:
    key = f"{proto_id}\0{comp_type}"
    if key in cache:
        return cache[key]
    if proto_id in visiting:
        return None
    visiting.add(proto_id)
    entry = entries.get(proto_id)
    if entry is None:
        cache[key] = None
        visiting.discard(proto_id)
        return None
    comp = get_comp(entry, comp_type)
    if comp is not None:
        cache[key] = comp
        visiting.discard(proto_id)
        return comp
    for parent in get_parents(entry):
        p = resolve_comp(parent, comp_type, entries, cache, visiting)
        if p is not None:
            cache[key] = p
            visiting.discard(proto_id)
            return p
    cache[key] = None
    visiting.discard(proto_id)
    return None


def resolve_has_comp(proto_id: str, comp_type: str, entries: dict[str, dict], cache: dict[str, bool], visiting: set[str]) -> bool:
    key = f"{proto_id}\0{comp_type}"
    if key in cache:
        return cache[key]
    if proto_id in visiting:
        return False
    visiting.add(proto_id)
    entry = entries.get(proto_id)
    if entry is None:
        cache[key] = False
        visiting.discard(proto_id)
        return False
    if has_comp(entry, comp_type):
        cache[key] = True
        visiting.discard(proto_id)
        return True
    for parent in get_parents(entry):
        if resolve_has_comp(parent, comp_type, entries, cache, visiting):
            cache[key] = True
            visiting.discard(proto_id)
            return True
    cache[key] = False
    visiting.discard(proto_id)
    return False


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


def get_materials_price(entry: dict, entries: dict[str, dict], material_prices: dict[str, float], comp_cache: dict[str, dict | None], has_cache: dict[str, bool]) -> float:
    comp = resolve_comp(entry.get("id", ""), "PhysicalComposition", entries, comp_cache, set()) if entry.get("id") else get_comp(entry, "PhysicalComposition")
    if comp is None:
        return 0.0
    mat_comp = comp.get("materialComposition")
    if not isinstance(mat_comp, dict):
        return 0.0
    # MaterialComponent gate matches PricingSystem: only entities with MaterialComponent count as materials
    has_material = resolve_has_comp(entry.get("id", ""), "Material", entries, has_cache, set()) if entry.get("id") else has_comp(entry, "Material")
    if not has_material:
        # In SS14, PhysicalComposition without MaterialComponent can still contribute in some cases?
        # PricingSystem.GetMaterialsPrice checks HasComp<MaterialComponent>(uid) && TryComp<PhysicalCompositionComponent>
        return 0.0
    price = 0.0
    for mat_id, qty in mat_comp.items():
        if isinstance(mat_id, str) and isinstance(qty, (int, float)):
            price += material_prices.get(mat_id, 0.0) * float(qty)
    stack = resolve_comp(entry.get("id", ""), "Stack", entries, comp_cache, set()) if entry.get("id") else get_comp(entry, "Stack")
    if stack is not None:
        count = as_int(stack.get("count"), 1)
        if count > 0:
            price *= count
    return price


def get_stack_price(entry: dict, entries: dict[str, dict], comp_cache: dict[str, dict | None], has_cache: dict[str, bool]) -> float:
    # Don't double-count material prices
    has_material = resolve_has_comp(entry.get("id", ""), "Material", entries, has_cache, set()) if entry.get("id") else has_comp(entry, "Material")
    if has_material:
        return 0.0
    stack_price_comp = resolve_comp(entry.get("id", ""), "StackPrice", entries, comp_cache, set()) if entry.get("id") else get_comp(entry, "StackPrice")
    stack_comp = resolve_comp(entry.get("id", ""), "Stack", entries, comp_cache, set()) if entry.get("id") else get_comp(entry, "Stack")
    if stack_price_comp is None or stack_comp is None:
        return 0.0
    price = as_float(stack_price_comp.get("price"), 0.0)
    count = as_int(stack_comp.get("count"), 1)
    return price * max(count, 0)


def get_static_price(entry: dict, entries: dict[str, dict], comp_cache: dict[str, dict | None]) -> float | None:
    comp = resolve_comp(entry.get("id", ""), "StaticPrice", entries, comp_cache, set()) if entry.get("id") else get_comp(entry, "StaticPrice")
    if comp is None:
        return None
    price = comp.get("price")
    if isinstance(price, (int, float)):
        return float(price)
    return None


def get_solutions_price(entry: dict, entries: dict[str, dict], reagent_prices: dict[str, float], comp_cache: dict[str, dict | None], has_cache: dict[str, bool]) -> float:
    has_ignore = resolve_has_comp(entry.get("id", ""), "IgnoreSolutionPriceComponent", entries, has_cache, set()) if entry.get("id") else has_comp(entry, "IgnoreSolutionPriceComponent")
    if has_ignore:
        return 0.0
    sol_mgr = resolve_comp(entry.get("id", ""), "SolutionContainerManager", entries, comp_cache, set()) if entry.get("id") else get_comp(entry, "SolutionContainerManager")
    if sol_mgr is None:
        return 0.0
    solutions = sol_mgr.get("solutions")
    if not isinstance(solutions, dict):
        return 0.0
    total = 0.0
    for _name, sol in solutions.items():
        if not isinstance(sol, dict):
            continue
        reagents = sol.get("reagents")
        if isinstance(reagents, list):
            for r in reagents:
                if not isinstance(r, dict):
                    continue
                rid = r.get("ReagentId") or r.get("reagent")
                qty = r.get("Quantity") or r.get("quantity")
                if isinstance(rid, str) and isinstance(qty, (int, float)):
                    total += float(qty) * reagent_prices.get(rid, 0.0)
        elif isinstance(reagents, dict):
            for rid, qty in reagents.items():
                if isinstance(rid, str) and isinstance(qty, (int, float)):
                    total += float(qty) * reagent_prices.get(rid, 0.0)
    return total


def get_estimated_price(proto_id: str, entries: dict[str, dict], material_prices: dict[str, float], reagent_prices: dict[str, float], cache: dict[str, float | None], comp_cache: dict[str, dict | None], has_cache: dict[str, bool], visiting: set[str]) -> float | None:
    """Mirrors PricingSystem.GetEstimatedPrice / GetPrice for prototype data."""
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

    price = 0.0
    price += get_materials_price(entry, entries, material_prices, comp_cache, has_cache)
    price += get_solutions_price(entry, entries, reagent_prices, comp_cache, has_cache)

    old_price = price
    price += get_stack_price(entry, entries, comp_cache, has_cache)
    if old_price == price:
        sp = get_static_price(entry, entries, comp_cache)
        if sp is not None:
            price += sp

    cache[proto_id] = price
    visiting.discard(proto_id)
    return price


def load_lathe_recipe_costs(prototypes_dir: Path, material_prices: dict[str, float]) -> dict[str, float]:
    """Fallback: material cost of lathe recipe producing this entity (what it's made of)."""
    costs: dict[str, float] = {}
    for path in prototypes_dir.rglob("*.yml"):
        for entry in load_yaml_file(path):
            if not isinstance(entry, dict) or entry.get("type") != "latheRecipe":
                continue
            result = entry.get("result")
            if not isinstance(result, str):
                continue
            materials = entry.get("materials")
            if not isinstance(materials, dict):
                continue
            cost = 0.0
            any_mat = False
            for mat_id, amount in materials.items():
                if isinstance(mat_id, str) and isinstance(amount, (int, float)):
                    any_mat = True
                    cost += material_prices.get(mat_id, 0.0) * float(amount)
            if not any_mat:
                continue
            prev = costs.get(result)
            if prev is None or cost < prev:
                costs[result] = cost
    return costs


def load_stack_spawns(prototypes_dir: Path) -> dict[str, str]:
    spawns: dict[str, str] = {}
    for path in prototypes_dir.rglob("*.yml"):
        for entry in load_yaml_file(path):
            if not isinstance(entry, dict) or entry.get("type") != "stack":
                continue
            sid = entry.get("id")
            spawn = entry.get("spawn")
            if isinstance(sid, str) and isinstance(spawn, str):
                spawns[sid] = spawn
    return spawns


def get_board_composition_cost(board_id: str, entries: dict[str, dict], material_prices: dict[str, float], reagent_prices: dict[str, float], cache: dict[str, float | None], comp_cache: dict[str, dict | None], has_cache: dict[str, bool], recipe_costs: dict[str, float], stack_spawns: dict[str, str]) -> float | None:
    """Estimate machine cost from MachineBoard requirements (what it's made of)."""
    board = entries.get(board_id)
    if board is None:
        return None
    mb = get_comp(board, "MachineBoard")
    if mb is None:
        mb = resolve_comp(board_id, "MachineBoard", entries, comp_cache, set())
    if mb is None:
        return None
    total = 0.0
    any_part = False

    # Stack requirements (materials like Glass, Steel, Cable)
    stack_reqs = mb.get("stackRequirements")
    if isinstance(stack_reqs, dict):
        for stack_id, amount in stack_reqs.items():
            if not isinstance(stack_id, str) or not isinstance(amount, (int, float)) or amount <= 0:
                continue
            spawn = stack_spawns.get(stack_id)
            if not spawn:
                continue
            unit_price = get_price_with_fallback(spawn, entries, material_prices, reagent_prices, cache, comp_cache, has_cache, recipe_costs, stack_spawns)
            if unit_price is not None and unit_price > 0:
                total += unit_price * float(amount)
                any_part = True

    # Tag/component requirements with default prototypes
    for key in ("tagRequirements", "componentRequirements"):
        reqs = mb.get(key)
        if not isinstance(reqs, dict):
            continue
        for _name, info in reqs.items():
            if not isinstance(info, dict):
                continue
            amount = info.get("amount", 0)
            default_proto = info.get("defaultPrototype")
            if not isinstance(default_proto, str) or not isinstance(amount, (int, float)) or amount <= 0:
                continue
            part_price = get_price_with_fallback(default_proto, entries, material_prices, reagent_prices, cache, comp_cache, has_cache, recipe_costs, stack_spawns)
            if part_price is not None and part_price > 0:
                total += part_price * float(amount)
                any_part = True

    # Machine part requirements (Capacitor, MatterBin, etc.) - best effort via default prototypes
    reqs = mb.get("requirements")
    if isinstance(reqs, dict):
        for part_id, amount in reqs.items():
            # requirements map ProtoId<MachinePartPrototype> to int; we can't easily resolve without loading MachinePartPrototype
            # but we can try common naming: MachinePartPrototype id often matches entity or we skip
            pass

    return total if any_part else None


def get_price_with_fallback(proto_id: str, entries: dict[str, dict], material_prices: dict[str, float], reagent_prices: dict[str, float], cache: dict[str, float | None], comp_cache: dict[str, dict | None], has_cache: dict[str, bool], recipe_costs: dict[str, float], stack_spawns: dict[str, str] | None = None) -> float | None:
    price = get_estimated_price(proto_id, entries, material_prices, reagent_prices, cache, comp_cache, has_cache, set())
    if price is not None and price > 0:
        return price
    # Fallback: lathe recipe material cost (composition/recipe, as noted in vendo TODO)
    rc = recipe_costs.get(proto_id)
    if rc is not None and rc > 0:
        return rc
    # Fallback: machine board composition (what it's made of)
    machine_comp = resolve_comp(proto_id, "Machine", entries, comp_cache, set())
    if machine_comp is not None:
        board = machine_comp.get("board")
        if isinstance(board, str) and board:
            if stack_spawns is not None:
                board_cost = get_board_composition_cost(board, entries, material_prices, reagent_prices, cache, comp_cache, has_cache, recipe_costs, stack_spawns)
                if board_cost is not None and board_cost > 0:
                    return board_cost
            board_price = get_price_with_fallback(board, entries, material_prices, reagent_prices, cache, comp_cache, has_cache, recipe_costs, stack_spawns)
            if board_price is not None and board_price > 0:
                return board_price
    return price


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


def has_preserve_on_sale(proto_id: str, entries: dict[str, dict], comp_cache: dict[str, dict | None]) -> bool:
    comp = resolve_comp(proto_id, "ShipyardSellCondition", entries, comp_cache, set())
    if comp is None:
        return False
    return bool(comp.get("preserveOnSale", False))


def main() -> None:
    print("Loading materials and reagents...")
    material_prices = load_material_prices(PROTOTYPES_DIR)
    reagent_prices = load_reagent_prices(PROTOTYPES_DIR)
    print(f"  materials: {len(material_prices)}, reagents with price: {len(reagent_prices)}")

    print("Loading lathe recipe costs...")
    recipe_costs = load_lathe_recipe_costs(PROTOTYPES_DIR, material_prices)
    print(f"  recipe costs: {len(recipe_costs)}")

    print("Loading stack spawns...")
    stack_spawns = load_stack_spawns(PROTOTYPES_DIR)
    print(f"  stacks: {len(stack_spawns)}")

    print("Loading vessels...")
    vessels: list[dict] = []
    for path in PROTOTYPES_DIR.rglob("*.yml"):
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
            if etype == "entity" or etype == "construction" or "components" in entry or "parent" in entry:
                if etype != "vessel":
                    all_entries[eid] = entry
    print(f"  entity-like protos: {len(all_entries)}")

    print("Loading locale...")
    ru_ent = load_ftl_names(LOCALE_RU_DIR, "ent-")
    en_ent = load_ftl_names(LOCALE_EN_DIR, "ent-")

    print("Building shuttle data...")
    price_cache: dict[str, float | None] = {}
    comp_cache: dict[str, dict | None] = {}
    has_cache: dict[str, bool] = {}
    name_cache: dict[str, str | None] = {}
    seen_item_protos: set[str] = set()
    shuttle_items: list[dict] = []

    for vessel, counts in vessel_maps:
        vid = vessel.get("id")
        items: list[dict] = []
        appraisal = 0.0
        for proto_id, count in counts.items():
            price = get_price_with_fallback(proto_id, all_entries, material_prices, reagent_prices, price_cache, comp_cache, has_cache, recipe_costs, stack_spawns)
            # Appraisal: include all entities with positive price, excluding PreserveOnSale (LacksPreserveOnSaleComp)
            if price is not None and price > 0 and not has_preserve_on_sale(proto_id, all_entries, comp_cache):
                appraisal += price * count
            if is_excluded_proto(proto_id):
                continue
            if price is None or price <= 0:
                continue
            seen_item_protos.add(proto_id)
            items.append({"id": proto_id, "count": count})
        items.sort(key=lambda x: (-(get_price_with_fallback(x["id"], all_entries, material_prices, reagent_prices, price_cache, comp_cache, has_cache, recipe_costs, stack_spawns) or 0), x["id"]))

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

    catalog_ids = set(seen_item_protos)
    catalog: list[dict] = []
    for proto_id in sorted(catalog_ids):
        price = get_price_with_fallback(proto_id, all_entries, material_prices, reagent_prices, price_cache, comp_cache, has_cache, recipe_costs, stack_spawns) or 0
        if price <= 0:
            continue
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
