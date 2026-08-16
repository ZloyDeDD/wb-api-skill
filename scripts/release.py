#!/usr/bin/env python3
"""Публикация свежего снимка: коммит, тег, пуш.

Запускается после scripts/update.py. Сам релиз на GitHub собирает
.github/workflows/release.yml — он срабатывает на пуш тега, вырезает свежую
секцию CHANGELOG.md и прикладывает архив снимка.

Тег ставится только когда у WB реально что-то поменялось: пустой синк — это
обычный коммит с новой датой снимка, засорять им ленту релизов незачем.

    python scripts/release.py --dry-run   # показать план, ничего не делая
    python scripts/release.py             # коммит, тег, пуш
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import release_notes
import wb
from wb import ROOT, configure_stdout

MAIN_BRANCH = "main"
REMOTE = "origin"

# Всё, что законно меняет update.py. Остальное коммитить сообщением
# «sync specs» нельзя — иначе правки кода уедут в релиз под чужой этикеткой.
SNAPSHOT_PATHS = ("swagger/", "CHANGELOG.md", "sources.yaml")


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} — код {result.returncode}\n{result.stderr.strip()}")
    # Только переводы строк: в выводе status --porcelain ведущий пробел значащий.
    return result.stdout.strip("\n")


def pick_tag(date: str, existing: list[str]) -> str:
    """v2026.08.12, а если такой тег занят — v2026.08.12.1, .2 и так далее."""
    base = "v" + date.replace("-", ".")
    if base not in existing:
        return base
    suffix = 1
    while f"{base}.{suffix}" in existing:
        suffix += 1
    return f"{base}.{suffix}"


def check_repo_state() -> list[str]:
    """Причины, по которым публиковать нельзя."""
    problems: list[str] = []

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        problems.append("HEAD отделён — переключитесь на ветку")
    elif branch != MAIN_BRANCH:
        problems.append(f"текущая ветка {branch}, а релизы идут из {MAIN_BRANCH}")

    if REMOTE not in git("remote").split():
        problems.append(f"нет remote {REMOTE}")

    return problems


def foreign_paths(status: str) -> list[str]:
    """Изменённые файлы, которые к снимку отношения не имеют."""
    paths = []
    for line in status.splitlines():
        path = line[3:].strip().strip('"')
        if not any(path.startswith(prefix) for prefix in SNAPSHOT_PATHS):
            paths.append(path)
    return paths


def describe_changes(changes: dict[str, int]) -> str:
    return (
        f"+{changes.get('added', 0)} "
        f"-{changes.get('removed', 0)} "
        f"~{changes.get('changed', 0)}"
    )


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(
        prog="release.py",
        description="Закоммитить снимок, поставить тег и запушить",
    )
    parser.add_argument("--dry-run", action="store_true", help="показать план, ничего не менять")
    parser.add_argument("--no-push", action="store_true", help="закоммитить и затегать локально, без пуша")
    args = parser.parse_args(argv)

    problems = check_repo_state()
    if problems:
        print("Публиковать нельзя:", file=sys.stderr)
        for problem in problems:
            print(f"  x {problem}", file=sys.stderr)
        return 2

    meta = release_notes.load_meta()
    date = meta.get("snapshot_date") or str(meta.get("updated_at", ""))[:10]
    if not date:
        print("В swagger/_meta.json нет даты снимка. Запустите python scripts/update.py", file=sys.stderr)
        return 2

    dirty = git("status", "--porcelain")
    if not dirty:
        print("Рабочее дерево чистое — публиковать нечего.")
        print("Сначала обновите снимок: python scripts/update.py")
        return 0

    foreign = foreign_paths(dirty)
    if foreign:
        print("Кроме снимка изменено ещё кое-что:", file=sys.stderr)
        for path in foreign:
            print(f"  x {path}", file=sys.stderr)
        print(
            "\nЭто не синк спецификаций — закоммитьте отдельно и обычным сообщением,"
            " потом запускайте release.py",
            file=sys.stderr,
        )
        return 2

    changes = meta.get("changes") or {}
    total = sum(changes.values())
    tag = pick_tag(date, git("tag", "--list").split()) if total else ""

    print(f"Снимок: {date}, эндпоинтов {meta.get('endpoint_count', '?')}")
    print("Изменения API: " + (describe_changes(changes) if total else "нет"))
    print("\nБудет закоммичено:")
    for line in dirty.splitlines():
        print(f"  {line}")

    if tag:
        prev_count = meta.get("previous_endpoint_count")
        count = meta.get("endpoint_count")
        changed = changes.get("changed", 0)
        message = f"Снимок WB API обновлён: {prev_count} → {count} эндпоинтов, {changed} изменено"
        print(f"\nТег: {tag}")
        print("\nЗаметки к релизу:\n")
        print(release_notes.render(tag, meta, release_notes.extract_section(
            release_notes.CHANGELOG_PATH.read_text(encoding="utf-8")
        )))
    else:
        message = f"Снимок WB API обновлён на {date}, изменений в API нет"
        print("\nТега не будет: у WB ничего не поменялось, релиз не нужен.")

    if args.dry_run:
        print("\n--dry-run: ничего не сделано.")
        return 0

    # Снимок уходит людям — проверяем его целостность до, а не после пуша.
    if wb.main(["validate"]) != 0:
        print("\nСнимок не проходит validate — публикация отменена.", file=sys.stderr)
        return 1

    git("add", "-A")
    git("commit", "-m", message)
    print(f"\nКоммит: {message}")

    if tag:
        git("tag", tag, "-m", message)
        print(f"Тег: {tag}")

    if args.no_push:
        print("\n--no-push: осталось запушить руками.")
        return 0

    git("push", REMOTE, MAIN_BRANCH)
    print(f"Запушено в {REMOTE}/{MAIN_BRANCH}")
    if tag:
        git("push", REMOTE, tag)
        print(f"Тег {tag} запушен — release.yml соберёт релиз.")
        print(f"Проверить: gh run watch && gh release view {tag}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
