#!/usr/bin/env python3
"""Обновление локального снимка OpenAPI-спецификаций Wildberries.

Источник один — портал WB, через браузер (антибот другого пути не оставляет).

Порядок работы:
  1. качаем каждый раздел из sources.yaml;
  2. на 404 выясняем новое имя файла по слагу страницы раздела и повторяем —
     переименования вроде 05-orders-dbs -> 05-dbs чинятся сами;
  3. валидируем скачанное до того, как что-то перезаписать;
  4. атомарно подменяем swagger/, пересобираем индекс и метаданные;
  5. печатаем и записываем в CHANGELOG.md, что изменилось в API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import fetch_wb
import wb
from wb import INDEX_PATH, META_PATH, ROOT, SWAGGER_DIR, build_index, configure_stdout

CONFIG_PATH = ROOT / "sources.yaml"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"

# Имя файла спецификации написано в HTML страницы раздела.
XFN_PATTERN = re.compile(r'x-file-name\\?"?:\s*\\?"?([a-z0-9-]+)', re.IGNORECASE)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"Нет файла конфигурации: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


# --------------------------------------------------------------------------
# Шаг 1-2: загрузка с восстановлением переименованных разделов
# --------------------------------------------------------------------------


def discover_filename(session: fetch_wb.BrowserSession, cfg: dict[str, Any], section: dict[str, Any]) -> str | None:
    """Достаёт актуальное имя файла раздела со страницы его документации."""
    status, html = session.get(cfg["docs_url"].format(slug=section["slug"]))
    if status != 200:
        return None
    match = XFN_PATTERN.search(html)
    if not match:
        return None
    return f"{section['prefix']}-{match.group(1)}.yaml"


def acquire_specs(cfg: dict[str, Any]) -> tuple[dict[str, str], list[str], list[str]]:
    """Скачивает все разделы. Возвращает (файлы, переименования, проблемы)."""
    sections = cfg["sections"]
    payloads: dict[str, str] = {}
    renames: list[str] = []
    problems: list[str] = []

    with fetch_wb.browser_session(sections[0]["file"], cfg["spec_url"]) as session:
        for section in sections:
            name = section["file"]
            status, text = session.get_spec(name, cfg["spec_url"])

            if status == 404:
                print(f"  ! {name}: 404, ищу новое имя по слагу {section['slug']}")
                discovered = discover_filename(session, cfg, section)
                if not discovered:
                    problems.append(
                        f"раздел {section['slug']} ({name}): WB отвечает 404,"
                        " и новое имя определить не удалось"
                    )
                    continue
                if discovered == name:
                    problems.append(f"раздел {section['slug']}: {name} отдаёт 404, хотя имя актуально")
                    continue
                status, text = session.get_spec(discovered, cfg["spec_url"])
                if status != 200:
                    problems.append(f"раздел {section['slug']}: {discovered} тоже недоступен (HTTP {status})")
                    continue
                renames.append(f"{name} → {discovered}")
                section["file"] = discovered
                name = discovered

            if status != 200:
                problems.append(f"{name}: HTTP {status} от WB")
                continue

            payloads[name] = text

    return payloads, renames, problems


def apply_renames_to_config(renames: list[str]) -> None:
    """Правит имена файлов в sources.yaml, сохраняя комментарии и форматирование."""
    text = CONFIG_PATH.read_text(encoding="utf-8")
    for rename in renames:
        old, new = rename.split(" → ")
        text = text.replace(f"file: {old}", f"file: {new}")
    CONFIG_PATH.write_text(text, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# Шаг 3: валидация до записи
# --------------------------------------------------------------------------


def validate_payloads(payloads: dict[str, str], previous_count: int, max_drop_pct: float) -> list[str]:
    problems: list[str] = []
    total = 0

    for name, text in sorted(payloads.items()):
        if not text.lstrip().startswith("openapi:"):
            problems.append(f"{name}: не начинается с 'openapi:' — похоже на заглушку антибота")
            continue
        try:
            spec = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            problems.append(f"{name}: не парсится как YAML — {exc}")
            continue
        if not isinstance(spec, dict) or not spec.get("paths"):
            problems.append(f"{name}: пустой или отсутствующий paths")
            continue
        total += sum(1 for _ in wb.iter_operations(spec, name))

    if total == 0:
        problems.append("во всех файлах вместе ноль эндпоинтов")
    elif previous_count:
        drop = (previous_count - total) / previous_count * 100
        if drop > max_drop_pct:
            problems.append(
                f"эндпоинтов стало {total} против {previous_count} — падение {drop:.0f}%,"
                f" больше допустимых {max_drop_pct:.0f}%"
            )
    return problems


# --------------------------------------------------------------------------
# Шаг 5: что изменилось
# --------------------------------------------------------------------------


def diff_indexes(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[str]]:
    def key(record: dict[str, Any]) -> tuple[str, str]:
        return record["method"], record["path"]

    old_map = {key(r): r for r in old.get("endpoints", [])}
    new_map = {key(r): r for r in new.get("endpoints", [])}

    def describe(record: dict[str, Any]) -> str:
        return f"`{record['method']} {record['path']}` — {record.get('summary') or '—'} ({record['file']})"

    added = [describe(new_map[k]) for k in sorted(new_map.keys() - old_map.keys())]
    removed = [describe(old_map[k]) for k in sorted(old_map.keys() - new_map.keys())]
    changed = [
        describe(new_map[k])
        for k in sorted(old_map.keys() & new_map.keys())
        if old_map[k].get("fingerprint") != new_map[k].get("fingerprint")
    ]

    old_files = {f["file"] for f in old.get("files", [])}
    new_files = {f["file"] for f in new.get("files", [])}
    new_sections = [
        f"`{f['file']}` — {f['title']} ({f['endpoints']} эндпоинтов)"
        for f in new.get("files", [])
        if f["file"] not in old_files
    ]
    gone_sections = [
        f"`{f['file']}` — {f['title']}"
        for f in old.get("files", [])
        if f["file"] not in new_files
    ]

    return {
        "Новые разделы": new_sections,
        "Пропавшие разделы": gone_sections,
        "Добавлены эндпоинты": added,
        "Удалены эндпоинты": removed,
        "Изменены": changed,
    }


def count_changes(diff: dict[str, list[str]]) -> dict[str, int]:
    """Счётчики диффа под ASCII-ключами — их читает scripts/release.py."""
    keys = {
        "Добавлены эндпоинты": "added",
        "Удалены эндпоинты": "removed",
        "Изменены": "changed",
        "Новые разделы": "new_sections",
        "Пропавшие разделы": "gone_sections",
    }
    return {ascii_key: len(diff.get(title, [])) for title, ascii_key in keys.items()}


def render_diff(diff: dict[str, list[str]], limit: int = 60) -> list[str]:
    lines: list[str] = []
    for title, items in diff.items():
        if not items:
            continue
        lines.append(f"### {title} ({len(items)})")
        lines.extend(f"- {item}" for item in items[:limit])
        if len(items) > limit:
            lines.append(f"- …ещё {len(items) - limit}")
        lines.append("")
    return lines


def write_changelog(header: str, body: list[str]) -> None:
    existing = ""
    if CHANGELOG_PATH.exists():
        existing = CHANGELOG_PATH.read_text(encoding="utf-8")
        if existing.startswith("# "):
            existing = existing.split("\n", 1)[1].lstrip("\n")
    entry = "\n".join([header, ""] + body).rstrip()
    CHANGELOG_PATH.write_text(
        f"# Изменения Wildberries API\n\n{entry}\n\n{existing}",
        encoding="utf-8",
        newline="\n",
    )


# --------------------------------------------------------------------------
# Главная процедура
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(
        prog="update.py",
        description="Обновить локальный снимок спецификаций Wildberries API",
    )
    parser.add_argument("--dry-run", action="store_true", help="показать изменения, ничего не записывать")
    args = parser.parse_args(argv)

    config = load_config()
    wb_cfg = config["wildberries"]
    max_drop = float(config.get("validation", {}).get("max_endpoint_drop_pct", 10))

    old_index: dict[str, Any] = {"endpoints": [], "files": []}
    if INDEX_PATH.exists():
        old_index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    previous_count = len(old_index.get("endpoints", []))

    print(f"Источник: dev.wildberries.ru, разделов в конфиге: {len(wb_cfg['sections'])}")
    try:
        payloads, renames, problems = acquire_specs(wb_cfg)
    except fetch_wb.FetchUnavailable as exc:
        print(f"\nОШИБКА: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - браузер может упасть по-разному
        print(f"\nОШИБКА: браузер не отработал — {exc}", file=sys.stderr)
        return 2

    print(f"  получено разделов: {len(payloads)}")

    if renames:
        print("\n!!! WB переименовал разделы:")
        for rename in renames:
            print(f"!!!   {rename}")
        print("!!! Новые имена подставлены автоматически.")

    if problems:
        print("\nОШИБКИ ЗАГРУЗКИ, snapshot не тронут:", file=sys.stderr)
        for problem in problems:
            print(f"  x {problem}", file=sys.stderr)
        print(
            "\nПосмотрите актуальный список разделов на"
            " https://dev.wildberries.ru/docs/openapi/ и поправьте sources.yaml",
            file=sys.stderr,
        )
        return 2

    validation_problems = validate_payloads(payloads, previous_count, max_drop)
    if validation_problems:
        print("\nОБНОВЛЕНИЕ ОТКЛОНЕНО, snapshot не тронут:", file=sys.stderr)
        for problem in validation_problems:
            print(f"  x {problem}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="wb-specs-") as tmp:
        staging = Path(tmp)
        for name, text in payloads.items():
            (staging / name).write_text(text, encoding="utf-8", newline="\n")
        new_index = build_index(staging)

        diff = diff_indexes(old_index, new_index)
        new_count = len(new_index["endpoints"])
        changes = sum(len(items) for items in diff.values())

        print(f"\nЭндпоинтов: {previous_count} → {new_count}")
        if changes == 0:
            print("Изменений нет — снимок уже актуален.")
        else:
            print()
            for line in render_diff(diff):
                print(line)

        if args.dry_run:
            print("--dry-run: ничего не записано.")
            return 0

        SWAGGER_DIR.mkdir(parents=True, exist_ok=True)
        for stale in SWAGGER_DIR.glob("*.yaml"):
            stale.unlink()
        for name in payloads:
            shutil.copy2(staging / name, SWAGGER_DIR / name)

    if renames:
        apply_renames_to_config(renames)

    INDEX_PATH.write_text(
        json.dumps(new_index, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    now = datetime.now(timezone.utc)
    meta = {
        "updated_at": now.isoformat(timespec="seconds"),
        # Отдельным полем, потому что бейдж shields умеет только целиком взять значение.
        "snapshot_date": now.strftime("%Y-%m-%d"),
        "source": "dev.wildberries.ru",
        "endpoint_count": len(new_index["endpoints"]),
        "previous_endpoint_count": previous_count,
        "file_count": len(new_index["files"]),
        "changes": count_changes(diff),
        "renamed_sections": renames,
        "files": {
            name: {"sha256": sha256(text), "bytes": len(text.encode("utf-8"))}
            for name, text in sorted(payloads.items())
        },
    }
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    if changes:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        intro = [f"Источник: dev.wildberries.ru. Эндпоинтов: {previous_count} → {new_count}.", ""]
        if renames:
            intro = [f"Переименованы разделы: {', '.join(renames)}.", ""] + intro
        write_changelog(f"## {today}", intro + render_diff(diff))
        print(f"CHANGELOG.md обновлён ({changes} изменений).")

    print("\nГотово. Проверка: python scripts/wb.py validate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
