#!/usr/bin/env python3
"""Собирает данные для страницы /chem из Resources/.

Читает прототипы реакций (Resources/Prototypes/Recipes/Reactions/*.yml),
реагентов (Resources/Prototypes/Reagents/**/*.yml) и английские названия
из локализации, результат пишет в app/data/chem.json.

Запуск: python3 scripts/build-chem-data.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


class ResourceLoader(yaml.SafeLoader):
    """YAML-загрузчик, терпимый к тегам вида `!type:Something` из SS14."""


def _ignore_unknown_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


ResourceLoader.add_multi_constructor("!", _ignore_unknown_tag)

ROOT = Path(__file__).resolve().parent.parent
REACTIONS_DIR = ROOT / "Resources" / "Prototypes" / "Recipes" / "Reactions"
REAGENTS_DIR = ROOT / "Resources" / "Prototypes" / "Reagents"
LOCALE_DIR = ROOT / "Resources" / "Locale" / "en-US"
OUT = ROOT / "app" / "data" / "chem.json"


def kebab(prototype_id: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", prototype_id).lower()


def load_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for path in LOCALE_DIR.rglob("*.ftl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([\w-]+)\s*=\s*(.+)$", line)
            if match:
                key, value = match.groups()
                if key.startswith("reagent-name-"):
                    names.setdefault(key.removeprefix("reagent-name-"), value.strip())
    return names


def load_reagents(names: dict[str, str]) -> dict[str, dict]:
    reagents: dict[str, dict] = {}
    for path in REAGENTS_DIR.rglob("*.yml"):
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=ResourceLoader) or []
        for entry in data:
            if not isinstance(entry, dict) or entry.get("type") != "reagent":
                continue
            rid = entry.get("id")
            if not rid:
                continue
            reagents[rid] = {
                "id": rid,
                "name": names.get(kebab(rid), rid),
                "color": entry.get("color"),
            }
    return reagents


def load_reactions(names: dict[str, str]) -> list[dict]:
    reactions: list[dict] = []
    for path in sorted(REACTIONS_DIR.glob("*.yml")):
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=ResourceLoader) or []
        for entry in data:
            if not isinstance(entry, dict) or entry.get("type") != "reaction":
                continue
            reactants = {
                rid: details.get("amount", 1)
                for rid, details in (entry.get("reactants") or {}).items()
            }
            products = {
                rid: details.get("amount", 1) if isinstance(details, dict) else details
                for rid, details in (entry.get("products") or {}).items()
            }
            reactions.append(
                {
                    "id": entry["id"],
                    "group": path.stem,
                    "reactants": reactants,
                    "products": products,
                    "minTemp": entry.get("minTemp"),
                    "maxTemp": entry.get("maxTemp"),
                    "mixer": entry.get("requiredMixerCategories") or [],
                }
            )
    return reactions


def main() -> None:
    names = load_names()
    reagents = load_reagents(names)
    reactions = load_reactions(names)

    # Названия продуктов/реагентов, не описанных как прототип реагента.
    missing = {
        rid
        for reaction in reactions
        for rid in list(reaction["reactants"]) + list(reaction["products"])
        if rid not in reagents
    }
    for rid in sorted(missing):
        reagents[rid] = {"id": rid, "name": names.get(kebab(rid), rid), "color": None}

    payload = {
        "reagents": sorted(reagents.values(), key=lambda r: r["name"].lower()),
        "reactions": sorted(reactions, key=lambda r: r["id"].lower()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"{OUT.relative_to(ROOT)}: {len(payload['reagents'])} реагентов, {len(reactions)} реакций")


if __name__ == "__main__":
    main()
