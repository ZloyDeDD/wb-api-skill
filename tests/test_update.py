#!/usr/bin/env python3
"""Тесты защитной логики обновления.

Проверяют то, что дорого сломать молча: восстановление переименованных
разделов, отбраковку мусора вместо перезаписи снимка и отчёт об изменениях.

Запуск: python tests/test_update.py
Сеть не используется — браузерная сессия подменяется заглушкой.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

import fetch_wb  # noqa: E402
import update  # noqa: E402
import wb  # noqa: E402

SPEC = """openapi: 3.0.1
info:
  title: Тест
  version: test
paths:
  /ping:
    servers:
      - url: https://common-api.wildberries.ru
    get:
      tags: [Проверка]
      summary: Проверка подключения
      responses:
        '200':
          description: OK
  /news:
    servers:
      - url: https://common-api.wildberries.ru
    get:
      tags: [Новости]
      summary: Новости
      responses:
        '200':
          description: OK
"""

CFG = {
    "spec_url": "https://wb.invalid/{file}",
    "docs_url": "https://wb.invalid/docs/{slug}",
    "sections": [{"prefix": "05", "slug": "orders-dbs", "file": "05-orders-dbs.yaml"}],
}

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class FakeSession:
    """Отвечает по заранее заданной карте URL -> (статус, тело)."""

    def __init__(self, routes: dict[str, tuple[int, str]]) -> None:
        self.routes = routes
        self.requested: list[str] = []

    def get(self, url: str) -> tuple[int, str]:
        self.requested.append(url)
        return self.routes.get(url, (404, '{"error":"File not found"}'))

    def get_spec(self, filename: str, url_template: str) -> tuple[int, str]:
        return self.get(url_template.format(file=filename))


def install_session(routes: dict[str, tuple[int, str]]) -> FakeSession:
    session = FakeSession(routes)

    @contextmanager
    def fake_browser_session(*args, **kwargs):
        yield session

    fetch_wb.browser_session = fake_browser_session
    return session


def fresh_cfg() -> dict:
    return {**CFG, "sections": [dict(section) for section in CFG["sections"]]}


# --------------------------------------------------------------------------
# Переименование разделов
# --------------------------------------------------------------------------


def test_plain_download() -> None:
    install_session({"https://wb.invalid/05-orders-dbs.yaml": (200, SPEC)})
    payloads, renames, problems = update.acquire_specs(fresh_cfg())
    check("обычная загрузка", payloads.keys() == {"05-orders-dbs.yaml"}, f"-> {list(payloads)}")
    check("без переименований", not renames and not problems, f"-> {renames} {problems}")


def test_rename_recovered_via_slug() -> None:
    install_session(
        {
            "https://wb.invalid/05-dbs.yaml": (200, SPEC),
            "https://wb.invalid/docs/orders-dbs": (200, '{"x-file-name":"dbs","title":"DBS"}'),
        }
    )
    cfg = fresh_cfg()
    payloads, renames, problems = update.acquire_specs(cfg)
    check("переименованный раздел скачан", "05-dbs.yaml" in payloads, f"-> {list(payloads)}")
    check("переименование зафиксировано", renames == ["05-orders-dbs.yaml → 05-dbs.yaml"], f"-> {renames}")
    check("ошибок нет", not problems, f"-> {problems}")
    check("конфиг в памяти обновлён", cfg["sections"][0]["file"] == "05-dbs.yaml")


def test_rename_unrecoverable() -> None:
    # Страница раздела тоже пропала — чинить нечем, нужно вмешательство человека.
    install_session({})
    payloads, renames, problems = update.acquire_specs(fresh_cfg())
    check("нерешаемый 404 попадает в ошибки", bool(problems), f"-> {problems}")
    check("ничего не скачано", not payloads and not renames, f"-> {payloads} {renames}")


def test_config_patch_preserves_comments() -> None:
    original = update.CONFIG_PATH.read_text(encoding="utf-8")
    try:
        update.apply_renames_to_config(["05-dbs.yaml → 05-something.yaml"])
        patched = update.CONFIG_PATH.read_text(encoding="utf-8")
        check("имя в конфиге заменено", "file: 05-something.yaml" in patched)
        check("комментарии на месте", "# Откуда берутся" in patched)
        check("остальные разделы не тронуты", "file: 01-general.yaml" in patched)
    finally:
        update.CONFIG_PATH.write_text(original, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# Отбраковка мусора
# --------------------------------------------------------------------------


def test_rejects_antibot_page() -> None:
    payloads = {"01-general.yaml": "<!doctype html><html>Проверяем браузер</html>"}
    check("заглушка антибота отбракована", bool(update.validate_payloads(payloads, 2, 10)))


def test_rejects_broken_yaml() -> None:
    payloads = {"01-general.yaml": "openapi: 3.0.1\npaths:\n  - [unclosed\n"}
    check("битый YAML отбракован", bool(update.validate_payloads(payloads, 2, 10)))


def test_rejects_empty_paths() -> None:
    payloads = {"01-general.yaml": "openapi: 3.0.1\ninfo:\n  title: X\npaths: {}\n"}
    check("пустой paths отбракован", bool(update.validate_payloads(payloads, 2, 10)))


def test_rejects_big_drop() -> None:
    check("обвал числа эндпоинтов отбракован",
          bool(update.validate_payloads({"01-general.yaml": SPEC}, 100, 10)))


def test_accepts_good_payload() -> None:
    problems = update.validate_payloads({"01-general.yaml": SPEC}, 2, 10)
    check("нормальный набор принят", not problems, f"-> {problems}")


# --------------------------------------------------------------------------
# Отчёт об изменениях и разбор аргументов
# --------------------------------------------------------------------------


def test_diff_detects_changes() -> None:
    spec = yaml.safe_load(SPEC)
    old_index = {
        "files": [{"file": "a.yaml", "title": "Тест", "endpoints": 2}],
        "endpoints": list(wb.iter_operations(spec, "a.yaml")),
    }
    changed = yaml.safe_load(SPEC.replace("summary: Новости", "summary: Новости портала"))
    new_index = {
        "files": [{"file": "a.yaml", "title": "Тест", "endpoints": 1}],
        "endpoints": [r for r in wb.iter_operations(changed, "a.yaml") if r["path"] != "/ping"],
    }
    diff = update.diff_indexes(old_index, new_index)
    check("диф видит удалённый эндпоинт", len(diff["Удалены эндпоинты"]) == 1, f"-> {diff}")
    check("диф видит изменённый эндпоинт", len(diff["Изменены"]) == 1, f"-> {diff}")
    check("диф не выдумывает добавленных", not diff["Добавлены эндпоинты"], f"-> {diff}")


def test_path_arg_survives_git_bash() -> None:
    known = {record["path"] for record in wb.load_index()["endpoints"]}
    if "/content/v2/get/cards/list" not in known:
        print("  skip путь для проверки Git Bash отсутствует в снимке")
        return
    mangled = "C:/Program Files/Git/content/v2/get/cards/list"
    check("путь, испорченный Git Bash, восстановлен",
          wb.resolve_path_arg(mangled) == "/content/v2/get/cards/list")


def main() -> int:
    wb.configure_stdout()
    print("Переименование разделов:")
    test_plain_download()
    test_rename_recovered_via_slug()
    test_rename_unrecoverable()
    test_config_patch_preserves_comments()

    print("Отбраковка мусора:")
    test_rejects_antibot_page()
    test_rejects_broken_yaml()
    test_rejects_empty_paths()
    test_rejects_big_drop()
    test_accepts_good_payload()

    print("Отчёт об изменениях и разбор аргументов:")
    test_diff_detects_changes()
    test_path_arg_survives_git_bash()

    print()
    if failures:
        print(f"ПРОВАЛЕНО: {len(failures)} — {', '.join(failures)}")
        return 1
    print("Все проверки пройдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
