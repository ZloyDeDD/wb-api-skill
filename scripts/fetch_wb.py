#!/usr/bin/env python3
"""Загрузка данных с dev.wildberries.ru через настоящий браузер.

Портал закрыт антиботом WBAAS: обычный HTTP-запрос получает HTTP 498 с
JS-челленджем вместо ответа, с любого IP и с любым User-Agent. Челлендж
проходит только браузер, причём:

  * headless блокируется — Chrome запускается видимым окном;
  * обычный Playwright тоже блокируется, потому что выставляет
    navigator.webdriver = true, и челлендж не завершается никогда.
    Поэтому используется patchright — форк Playwright, который это прячет.

Один раз пройденный челлендж действует на всю сессию, поэтому все запросы
выполняются внутри одного BrowserSession через fetch() в контексте страницы.
"""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SPEC_URL_TEMPLATE = "https://dev.wildberries.ru/api/swagger/yaml/ru/{file}?region=ru"
CHALLENGE_TIMEOUT_MS = 180_000
CHALLENGE_STEP_MS = 2_000
BROWSER_CHANNELS = ("chrome", "msedge", None)


class FetchUnavailable(RuntimeError):
    """Браузерная загрузка невозможна в этом окружении."""


def _require_driver() -> tuple[Any, str]:
    try:
        from patchright.sync_api import sync_playwright

        return sync_playwright, "patchright"
    except ImportError:
        pass
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright, "playwright"
    except ImportError as exc:
        raise FetchUnavailable(
            "Не установлен ни patchright, ни playwright — загрузка невозможна.\n"
            "Установка: python -m pip install -r requirements-update.txt"
        ) from exc


def _launch(playwright: Any, headless: bool) -> Any:
    last_error: Exception | None = None
    for channel in BROWSER_CHANNELS:
        options: dict[str, Any] = {"headless": headless}
        if channel:
            options["channel"] = channel
        try:
            return playwright.chromium.launch(**options)
        except Exception as exc:  # noqa: BLE001 - перебираем доступные браузеры
            last_error = exc
    raise FetchUnavailable(
        "Не удалось запустить Chrome, Edge или Chromium.\n"
        f"Последняя ошибка: {last_error}"
    )


class BrowserSession:
    """Страница с пройденным антиботом. Все запросы идут через её fetch()."""

    def __init__(self, page: Any, verbose: bool) -> None:
        self._page = page
        self._verbose = verbose

    def get(self, url: str) -> tuple[int, str]:
        payload = self._page.evaluate(
            """async (url) => {
                const response = await fetch(url, { credentials: 'include' });
                return { status: response.status, text: await response.text() };
            }""",
            url,
        )
        return payload["status"], payload["text"]

    def get_spec(self, filename: str, url_template: str = SPEC_URL_TEMPLATE) -> tuple[int, str]:
        if self._verbose:
            print(f"  скачиваю {filename}", file=sys.stderr)
        status, text = self.get(url_template.format(file=filename))
        if status == 200 and not text.startswith("openapi:"):
            raise FetchUnavailable(f"{filename}: ответ не похож на OpenAPI YAML")
        return status, text


def _pass_challenge(page: Any, probe_url: str, verbose: bool) -> None:
    page.goto(probe_url, wait_until="domcontentloaded", timeout=60_000)
    waited = 0
    last_head = ""
    while waited < CHALLENGE_TIMEOUT_MS:
        try:
            head = page.evaluate("() => (document.body?.innerText || '').slice(0, 80)")
        except Exception:  # noqa: BLE001 - идёт навигация, пробуем ещё раз
            head = ""
        if head.startswith("openapi:"):
            return
        if verbose and head and head != last_head:
            print(f"  [антибот] {' '.join(head.split())[:70]}", file=sys.stderr)
            last_head = head
        page.wait_for_timeout(CHALLENGE_STEP_MS)
        waited += CHALLENGE_STEP_MS
    raise FetchUnavailable(
        f"Антибот не пропустил за {CHALLENGE_TIMEOUT_MS // 1000} с.\n"
        "Если стоит обычный playwright — поставьте patchright:\n"
        "  python -m pip install -r requirements-update.txt"
    )


@contextmanager
def browser_session(
    probe_file: str = "01-general.yaml",
    url_template: str = SPEC_URL_TEMPLATE,
    headless: bool = False,
    verbose: bool = True,
) -> Iterator[BrowserSession]:
    """Открывает браузер, проходит антибот и отдаёт сессию для запросов."""
    sync_playwright, driver = _require_driver()
    if verbose:
        print(f"  драйвер браузера: {driver}", file=sys.stderr)

    with sync_playwright() as playwright:
        browser = _launch(playwright, headless)
        try:
            context = browser.new_context(
                locale="ru-RU",
                viewport={"width": 1280, "height": 800},
                extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"},
            )
            page = context.new_page()
            _pass_challenge(page, url_template.format(file=probe_file), verbose)
            yield BrowserSession(page, verbose)
        finally:
            browser.close()


def fetch_files(
    files: list[str],
    url_template: str = SPEC_URL_TEMPLATE,
    headless: bool = False,
    verbose: bool = True,
) -> dict[str, str]:
    """Скачивает указанные спеки. Отсутствующие у WB (404) пропускает."""
    if not files:
        return {}

    result: dict[str, str] = {}
    with browser_session(files[0], url_template, headless, verbose) as session:
        for name in files:
            status, text = session.get_spec(name, url_template)
            if status == 404:
                print(f"  ! {name}: WB отвечает 404", file=sys.stderr)
                continue
            if status != 200:
                raise FetchUnavailable(f"{name}: HTTP {status} от WB")
            result[name] = text
    return result


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="fetch_wb.py",
        description="Скачать OpenAPI-спеки напрямую с dev.wildberries.ru",
    )
    parser.add_argument("files", nargs="+", help="имена файлов, например 01-general.yaml")
    parser.add_argument("--out", type=Path, required=True, help="куда сохранить")
    parser.add_argument("--headless", action="store_true", help="скрытый режим (обычно блокируется)")
    args = parser.parse_args(argv)

    try:
        payloads = fetch_files(args.files, headless=args.headless)
    except FetchUnavailable as exc:
        print(f"Загрузка не удалась: {exc}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in payloads.items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"{args.out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
