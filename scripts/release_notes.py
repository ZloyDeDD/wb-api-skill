#!/usr/bin/env python3
"""Заметки к релизу из CHANGELOG.md и swagger/_meta.json.

Отдельный источник правды заводить незачем: update.py уже описал изменения
в CHANGELOG.md, а счётчики положил в _meta.json. Здесь только сборка.

Печатает markdown в stdout — им пользуются и .github/workflows/release.yml,
и человек, которому нужно посмотреть заметки до пуша тега:

    python scripts/release_notes.py --version v2026.08.12
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from wb import META_PATH, ROOT, configure_stdout

CHANGELOG_PATH = ROOT / "CHANGELOG.md"
REPO_URL = "https://github.com/ZloyDeDD/wb-api-skill"


def extract_section(text: str, date: str | None = None) -> tuple[str, list[str]]:
    """Возвращает (дата, строки тела) блока `## <дата>` из CHANGELOG.md.

    Без аргумента date берётся самый верхний блок — он же самый свежий.
    """
    header: str | None = None
    body: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if header is not None:  # дошли до предыдущей записи — дальше не наше
                break
            found = line[3:].strip()
            if date is None or found == date:
                header = found
            continue
        if header is not None:
            body.append(line)

    if header is None:
        return "", []

    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return header, body


def load_meta() -> dict[str, Any]:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def summary_line(meta: dict[str, Any]) -> str:
    count = meta.get("endpoint_count", "?")
    previous = meta.get("previous_endpoint_count")
    endpoints = f"эндпоинтов: {previous} → {count}" if previous else f"эндпоинтов: {count}"
    return (
        f"Источник: {meta.get('source', 'dev.wildberries.ru')} · "
        f"{endpoints} · разделов: {meta.get('file_count', '?')} · "
        f"снимок от {meta.get('snapshot_date', '?')}"
    )


def render(version: str, meta: dict[str, Any], section: tuple[str, list[str]]) -> str:
    _, body = section
    lines = [summary_line(meta), ""]

    if body:
        lines += body + [""]
    else:
        lines += ["Изменений эндпоинтов нет — обновились сопутствующие файлы.", ""]

    if meta.get("renamed_sections"):
        lines += [f"WB переименовал разделы: {', '.join(meta['renamed_sections'])}.", ""]

    asset = f"wb-swagger-{version}.zip" if version else "wb-swagger-*.zip"
    lines += [
        "## Как обновиться",
        "",
        "Скилл установлен через `git clone`:",
        "",
        "```bash",
        "git -C ~/.claude/skills/wildberries-api pull",
        "```",
        "",
        f"Без git — скачайте `{asset}` из ассетов этого релиза и распакуйте поверх `swagger/`.",
        "",
        f"Полная история изменений API: [CHANGELOG.md]({REPO_URL}/blob/main/CHANGELOG.md).",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(
        prog="release_notes.py",
        description="Собрать заметки к релизу из CHANGELOG.md и swagger/_meta.json",
    )
    parser.add_argument("--version", default="", help="тег релиза, например v2026.08.12")
    parser.add_argument("--date", default=None, help="дата секции CHANGELOG; по умолчанию верхняя")
    args = parser.parse_args(argv)

    text = CHANGELOG_PATH.read_text(encoding="utf-8") if CHANGELOG_PATH.exists() else ""
    print(render(args.version, load_meta(), extract_section(text, args.date)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
