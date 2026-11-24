#!/usr/bin/env python3
"""Собирает данные для страницы /gasmix из Resources/.

Читает газовые реакции (Atmospherics/reactions.yml, _Funkystation/Atmospherics/reactions.yml),
прототипы газов (Atmospherics/gases.yml, _Funkystation, _ES) и локализацию газов (en-US/ru-RU).

Стехиометрия (вход/выход в молях) и пояснения заданы в REACTION_INFO: они выведены
из кода эффектов в DeepLagoon-Station/Content.Server/Atmos/Reactions/*.cs и
Content.Server/_Funkystation/Atmos/Reactions/*.cs (константы — Content.Shared/Atmos/Atmospherics.cs).

Запуск: python3 scripts/build-gas-data.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


class ResourceLoader(yaml.SafeLoader):
    """YAML-загрузчик, сохраняющий теги вида `!type:PlasmaFireReaction`."""


def _tagged_node(loader, tag_suffix, node):
    """Сохраняет имя тега в поле `__tag__`, чтобы не терять типы эффектов."""
    if isinstance(node, yaml.MappingNode):
        data = loader.construct_mapping(node, deep=True)
        if isinstance(data, dict):
            data["__tag__"] = str(tag_suffix).removeprefix("type:")
            return data
        return data
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


ResourceLoader.add_multi_constructor("!", _tagged_node)

ROOT = Path(__file__).resolve().parent.parent
PROTOTYPES = ROOT / "Resources" / "Prototypes"
ATMOS_DIR = PROTOTYPES / "Atmospherics"
FUNKY_ATMOS_DIR = PROTOTYPES / "_Funkystation" / "Atmospherics"
ES_ATMOS_DIR = PROTOTYPES / "_ES" / "Atmospherics"
LOCALE_EN = ROOT / "Resources" / "Locale" / "en-US"
LOCALE_RU = ROOT / "Resources" / "Locale" / "ru-RU"
OUT = ROOT / "app" / "data" / "gas.json"

# Gas enum order from Content.Shared.Atmos.Atmospherics.Gas
GAS_ORDER = [
    "Oxygen",
    "Nitrogen",
    "CarbonDioxide",
    "Plasma",
    "Tritium",
    "WaterVapor",
    "Ammonia",
    "NitrousOxide",
    "Frezon",
    "BZ",
    "Healium",
    "Nitrium",
    "Pluoxium",
    "Smoke",
]

# Стехиометрия и пояснения. Ключ — id прототипа gasReaction.
#
# input/output — моли на один «оборот» реакции (нормировано по ведущему продукту/расходу).
# Для реакций с переменным выходом добавляется outputVariants.
REACTION_INFO: dict[str, dict] = {
    "AmmoniaOxygenReaction": {
        "title": "Окисление аммиака",
        "summary": "Аммиак реагирует с кислородом при нагреве выше 50 °C, давая оксид азота и водяной пар.",
        "input": {"Ammonia": 1, "Oxygen": 1},
        "output": {"NitrousOxide": 0.5, "WaterVapor": 1.5},
        "notes": [
            "Скорость зависит от концентраций: ∝ (доля NH₃)² · (доля O₂)², поэтому разбавленная смесь реагирует медленно.",
        ],
    },
    "bzFormation": {
        "title": "Образование BZ",
        "summary": "Плазма и оксид азота образуют BZ при низком давлении и температуре ниже 40 °C.",
        "input": {"Plasma": 0.8, "NitrousOxide": 0.4},
        "output": {"BZ": 1},
        "notes": [
            "Расход на 1 BZ: 0.8 плазмы + 0.4 N₂O; скорость ∝ (объём / давление) и растёт при низком давлении.",
            "Для полной скорости N₂O по молям должно быть не меньше плазмы — избыток N₂O не расходуется.",
            "Если плазма занимает больше 75 % смеси (плазма + N₂O), часть N₂O разлагается в N₂ и O₂.",
        ],
    },
    "FrezonCoolant": {
        "title": "Фрезоновое охлаждение",
        "summary": "Азот и фрезон превращаются в оксид азота, поглощая тепло — это самый сильный хладагент.",
        "input": {"Frezon": 1, "Nitrogen": 5},
        "output": {"NitrousOxide": 6},
        "notes": [
            "Поглощает 600 кДж на моль фрезона; эффект усиливается с ростом температуры среды (до ×10 у 373 K), но выше 373 K не растёт.",
            "Скорость ограничена теплоёмкостью смеси, поэтому малое количество газа охлаждает слабо.",
        ],
    },
    "FrezonProduction": {
        "title": "Синтез фрезона",
        "summary": "Тритий и кислород на азотном катализаторе дают фрезон при температуре ниже 73.15 K.",
        "input": {"Tritium": 1, "Oxygen": 8, "Nitrogen": 0.8},
        "output": {"Frezon": 0.18},
        "notes": [
            "Эффективность = T / 73.15 K: чем холоднее, тем меньше выход, но и меньше нужно азота-катализатора.",
            "Кислород расходуется в 8 раз быстрее трития; неиспользованная часть уходит в азот.",
            "Азот нужен как катализатор: при 73.15 K — не менее 0.8 моль на 1 моль трития.",
        ],
    },
    "HealiumProduction": {
        "title": "Синтез хилиума",
        "summary": "BZ и фрезон при низкой температуре образуют хилиум.",
        "input": {"BZ": 1, "Frezon": 11},
        "output": {"Healium": 12},
        "notes": [
            "Пропорция 1 BZ : 11 фрезона даёт максимум при 23.15 K; эффективность = 23.15 / T, скорость ∝ T / 293.15.",
            "При нагреве выход падает, при T выше 293.15 K реакция прекращается.",
        ],
    },
    "N2ODecomposition": {
        "title": "Разложение оксида азота",
        "summary": "При температуре от 850 K оксид азота распадается на азот и кислород.",
        "input": {"NitrousOxide": 1},
        "output": {"Nitrogen": 1, "Oxygen": 0.5},
        "notes": [
            "За тик разлагается половина имеющегося N₂O (1 / 2 моль).",
        ],
    },
    "NitriumDecomposition": {
        "title": "Разложение нитриума",
        "summary": "Нитриум распадается на азот и водяной пар при температуре ниже 343 K.",
        "input": {"Nitrium": 1},
        "output": {"WaterVapor": 1, "Nitrogen": 1},
        "notes": [
            "Кислород нужен как катализатор (порог 0.01 моль) и не расходуется.",
            "Скорость = T / 2984 за тик: на холоде реакция идёт очень медленно, при 343 K — быстрее всего.",
            "Реакция выделяет 30 кДж на моль.",
        ],
    },
    "NitriumProduction": {
        "title": "Синтез нитриума",
        "summary": "Тритий, азот и BZ при температуре от 1500 K образуют нитриум.",
        "input": {"Tritium": 1, "Nitrogen": 1, "BZ": 0.05},
        "output": {"Nitrium": 1},
        "notes": [
            "Минимум для запуска: 20 трития, 10 азота, 5 BZ.",
            "В YAML указан порог 20 азота, но код эффекта проверяет 10 — ориентируйтесь на код.",
            "Реакция поглощает 100 кДж на моль.",
        ],
    },
    "PlasmaFire": {
        "title": "Горение плазмы",
        "summary": "Плазма горит в кислороде при температуре от 373 K, выделяя тепло и создавая очаг огня.",
        "input": {"Plasma": 1, "Oxygen": 1.4},
        "output": {"CarbonDioxide": 1},
        "outputVariants": [
            {"label": "O₂ / плазма < 10", "output": {"CarbonDioxide": 1}},
            {"label": "O₂ / плазма > 30", "output": {"Tritium": 1}},
            {"label": "10 … 30", "output": {"Tritium": 0.5, "CarbonDioxide": 0.5}},
        ],
        "notes": [
            "Кислорода сгорает 1.4 моль на 1 плазму при 373 K; к 700 K расход падает до 0.4.",
            "Соотношение O₂/плазма определяет продукт: меньше 10 — почти весь CO₂, больше 30 — почти весь тритий.",
        ],
    },
    "PluoxiumProduction": {
        "title": "Синтез плюоксиума",
        "summary": "CO₂ и кислород со следами трития образуют плюоксиум при 50–273 K.",
        "input": {"CarbonDioxide": 1, "Oxygen": 0.5, "Tritium": 0.01},
        "output": {"Pluoxium": 1, "WaterVapor": 0.01},
        "notes": [
            "Тритий работает катализатором: 0.01 моль на 1 моль CO₂.",
            "За тик образуется не более 5 моль плюоксиума.",
        ],
    },
    "TritiumFire": {
        "title": "Горение трития",
        "summary": "Тритий горит при температуре от 700 K, превращаясь в водяной пар.",
        "input": {"Tritium": 1, "Oxygen": 9},
        "output": {"WaterVapor": 10},
        "notes": [
            "За один тик в среде с избытком кислорода сгорает 1/10 трития, при этом кислорода уходит ~0.9 моль на 1 моль трития.",
            "При недостатке кислорода тритий расходуется медленно — 1 моль O₂ сжигает 0.01 моль трития за тик.",
            "Реакция выделяет тепло и создаёт очаг огня.",
        ],
    },
}


def kebab(prototype_id: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", prototype_id).lower()


def load_locale(directory: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    if not directory.exists():
        return names
    for path in sorted(directory.rglob("*.ftl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([\w.-]+)\s*=\s*(.+)$", line)
            if match:
                key, value = match.groups()
                names.setdefault(key, value.strip())
    return names


def normalize_color(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{3,8}", text):
        return None
    return f"#{text.lower()}"


def load_gas_prototypes(en: dict[str, str], ru: dict[str, str]) -> list[dict]:
    """Газы берём из прототипов type: gas — там же лежит актуальный цвет."""
    found: dict[int, dict] = {}
    for directory in (ATMOS_DIR, FUNKY_ATMOS_DIR, ES_ATMOS_DIR):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.yml")):
            try:
                data = yaml.load(path.read_text(encoding="utf-8"), Loader=ResourceLoader) or []
            except Exception:
                continue
            for entry in data:
                if not isinstance(entry, dict) or entry.get("type") != "gas":
                    continue
                raw_id = entry.get("id")
                try:
                    gas_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if gas_id >= len(GAS_ORDER):
                    continue
                name_key = str(entry.get("name") or "")
                found[gas_id] = {
                    "id": GAS_ORDER[gas_id],
                    "name": en.get(name_key) or name_key or GAS_ORDER[gas_id],
                    "nameRu": ru.get(name_key) or en.get(name_key) or name_key or GAS_ORDER[gas_id],
                    "color": normalize_color(entry.get("color")),
                }

    gases: list[dict] = []
    for gas_id, gas_name in enumerate(GAS_ORDER):
        gas = found.get(gas_id)
        if gas is None:
            gas = {"id": gas_name, "name": gas_name, "nameRu": gas_name, "color": None}
        gases.append(gas)
    return gases


def parse_requirements(req) -> dict[str, float]:
    result: dict[str, float] = {}
    if req is None:
        return result
    if isinstance(req, dict):
        for k, v in req.items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv > 0:
                result[str(k)] = fv
    elif isinstance(req, list):
        for i, v in enumerate(req):
            if i >= len(GAS_ORDER):
                break
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv > 0:
                result[GAS_ORDER[i]] = fv
    return result


def effect_name(effect) -> str:
    if isinstance(effect, dict):
        tag = effect.get("__tag__")
        if tag:
            return str(tag)
        for k in effect.keys():
            if k != "__tag__":
                return str(k)
        return "effect"
    return type(effect).__name__


def source_key(path: Path) -> str:
    return "funky" if "_Funkystation" in path.parts else "atmospherics"


def load_gas_reactions() -> list[dict]:
    reactions: list[dict] = []
    files: list[Path] = []
    for directory in (ATMOS_DIR, FUNKY_ATMOS_DIR):
        if directory.exists():
            files.extend(sorted(directory.glob("*.yml")))
    for path in files:
        try:
            data = yaml.load(path.read_text(encoding="utf-8"), Loader=ResourceLoader) or []
        except Exception:
            continue
        for entry in data:
            if not isinstance(entry, dict) or entry.get("type") != "gasReaction":
                continue
            rid = entry.get("id")
            if not rid:
                continue
            meta = REACTION_INFO.get(rid, {})
            min_temp = entry.get("minimumTemperature")
            max_temp = entry.get("maximumTemperature")
            min_energy = entry.get("minimumEnergy")
            reactions.append({
                "id": rid,
                "title": meta.get("title", rid),
                "summary": meta.get("summary", ""),
                "priority": entry.get("priority", 0),
                "minTemp": float(min_temp) if min_temp is not None else None,
                "maxTemp": float(max_temp) if max_temp is not None else None,
                "minEnergy": float(min_energy) if min_energy is not None else 0.0,
                "reactants": parse_requirements(entry.get("minimumRequirements")),
                "input": meta.get("input", {}),
                "output": meta.get("output", {}),
                "outputVariants": meta.get("outputVariants", []),
                "notes": meta.get("notes", []),
                "effects": [effect_name(eff) for eff in (entry.get("effects") or [])],
                "source": source_key(path),
            })
    return reactions


def main() -> None:
    en = load_locale(LOCALE_EN)
    ru = load_locale(LOCALE_RU)
    gases = load_gas_prototypes(en, ru)
    reactions = load_gas_reactions()

    payload = {
        "gases": gases,
        "reactions": sorted(reactions, key=lambda r: ((r.get("source") or "").lower(), (r.get("id") or "").lower())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"{OUT.relative_to(ROOT)}: {len(payload['gases'])} газов, {len(reactions)} реакций")


if __name__ == "__main__":
    main()
