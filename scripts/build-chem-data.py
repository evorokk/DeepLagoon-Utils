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
import sys
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
PROTOTYPES_DIR = ROOT / "Resources" / "Prototypes"
REACTION_GLOBS = ("**/Recipes/Reactions/**/*.yml", "**/Recipes/Reactions/**/*.yaml")
REAGENT_GLOBS = ("**/Reagents/**/*.yml", "**/Reagents/**/*.yaml")
LOCALE_DIR = ROOT / "Resources" / "Locale" / "en-US"
OUT = ROOT / "app" / "data" / "chem.json"


def kebab(prototype_id: str) -> str:
    return re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
        "-",
        prototype_id,
    ).lower()


def locale_keys(prototype_id: str) -> list[str]:
    keys = [kebab(prototype_id)]
    legacy = re.sub(r"(?<!^)(?=[A-Z])", "-", prototype_id).lower()
    if legacy not in keys:
        keys.append(legacy)
    keys.append(prototype_id.lower())
    return keys


def resolve_name(names: dict[str, str], prototype_id: str) -> str:
    for key in locale_keys(prototype_id):
        if key in names:
            return names[key]
    return prototype_id


def load_names() -> dict[str, str]:
    names: dict[str, str] = {}
    if not LOCALE_DIR.exists():
        return names
    for path in sorted(LOCALE_DIR.rglob("*.ftl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"warn: cannot read locale {path}: {exc}", file=sys.stderr)
            continue
        for line in lines:
            match = re.match(r"^([\w-]+)\s*=\s*(.+)$", line)
            if match:
                key, value = match.groups()
                if key.startswith("reagent-name-"):
                    names.setdefault(key.removeprefix("reagent-name-"), value.strip())
    return names


def iter_prototype_files(globs: tuple[str, ...]) -> list[Path]:
    if not PROTOTYPES_DIR.exists():
        return []
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in globs:
        for path in sorted(PROTOTYPES_DIR.glob(pattern)):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files)


def load_yaml_entries(path: Path) -> list[dict]:
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=ResourceLoader) or []
    except Exception as exc:  # noqa: BLE001 - build should skip broken files, not fail
        print(f"warn: cannot parse {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        print(
            f"warn: unexpected YAML root in {path.relative_to(ROOT)}: {type(data).__name__}",
            file=sys.stderr,
        )
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def load_reagents(names: dict[str, str]) -> dict[str, dict]:
    reagents: dict[str, dict] = {}
    for path in iter_prototype_files(REAGENT_GLOBS):
        for entry in load_yaml_entries(path):
            if entry.get("type") != "reagent":
                continue
            rid = entry.get("id")
            if not isinstance(rid, str) or not rid:
                continue
            if rid in reagents:
                continue
            reagents[rid] = {
                "id": rid,
                "name": resolve_name(names, rid),
                "color": entry.get("color"),
            }
    return reagents


def load_reactions(names: dict[str, str]) -> list[dict]:
    reactions: list[dict] = []
    seen_ids: set[str] = set()
    for path in iter_prototype_files(REACTION_GLOBS):
        for entry in load_yaml_entries(path):
            if entry.get("type") != "reaction":
                continue
            reaction_id = entry.get("id")
            if not isinstance(reaction_id, str) or not reaction_id:
                continue
            if reaction_id in seen_ids:
                continue

            reactants_raw = entry.get("reactants")
            products_raw = entry.get("products")
            if not isinstance(reactants_raw, dict):
                reactants_raw = {}
            if not isinstance(products_raw, dict):
                products_raw = {}

            reactants: dict[str, float | int] = {}
            for rid, details in reactants_raw.items():
                if not isinstance(rid, str):
                    continue
                amount = 1
                if isinstance(details, dict):
                    amount = details.get("amount", 1)
                if isinstance(amount, (int, float)):
                    reactants[rid] = amount

            products: dict[str, float | int] = {}
            for rid, details in products_raw.items():
                if not isinstance(rid, str):
                    continue
                amount = details
                if isinstance(details, dict):
                    amount = details.get("amount", 1)
                if isinstance(amount, (int, float)):
                    products[rid] = amount

            mixer = entry.get("requiredMixerCategories") or []
            if not isinstance(mixer, list):
                mixer = []

            seen_ids.add(reaction_id)
            reactions.append(
                {
                    "id": reaction_id,
                    "group": path.stem,
                    "reactants": reactants,
                    "products": products,
                    "minTemp": entry.get("minTemp"),
                    "maxTemp": entry.get("maxTemp"),
                    "mixer": [m for m in mixer if isinstance(m, str)],
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
        reagents[rid] = {"id": rid, "name": resolve_name(names, rid), "color": None}

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
