#!/usr/bin/env python3
"""Читалка локального снимка OpenAPI-спецификаций Wildberries Seller API.

Поиск идёт по компактному индексу swagger/_index.json, сырой YAML читается
только для конкретного эндпоинта. Сетевых запросов не делает.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import yaml
except ImportError:  # pragma: no cover - защита окружения
    raise SystemExit("Нужен PyYAML. Установка: python -m pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parents[1]
SWAGGER_DIR = ROOT / "swagger"
INDEX_PATH = SWAGGER_DIR / "_index.json"
META_PATH = SWAGGER_DIR / "_meta.json"

METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")
STALE_AFTER_DAYS = 30
MAX_SCHEMA_DEPTH = 6


def configure_stdout() -> None:
    """Русский текст в Windows-консоли иначе превращается в мусор."""
    for stream in (sys.stdout, sys.stderr):
        try:
            # line_buffering — чтобы вывод скрипта и подпроцессов не перемешивался
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass


# --------------------------------------------------------------------------
# Загрузка спецификаций
# --------------------------------------------------------------------------


def spec_files(swagger_dir: Path = SWAGGER_DIR) -> list[Path]:
    return sorted(p for p in swagger_dir.glob("*.yaml") if not p.name.startswith("_"))


def load_spec(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: не разобрался как YAML-словарь")
    return data


def _hosts_from_servers(servers: Any) -> list[str]:
    hosts = []
    for server in servers or []:
        url = (server or {}).get("url") if isinstance(server, dict) else None
        if not url:
            continue
        hosts.append(re.sub(r"^https?://", "", url).rstrip("/"))
    return hosts


def _fingerprint(operation: dict[str, Any]) -> str:
    """Отпечаток операции — чтобы отличить изменившийся эндпоинт от нетронутого."""
    blob = json.dumps(operation, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def iter_operations(spec: dict[str, Any], filename: str) -> Iterator[dict[str, Any]]:
    """Разворачивает spec в плоские записи об эндпоинтах."""
    section = (spec.get("info") or {}).get("title") or filename
    spec_servers = spec.get("servers")

    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        path_servers = item.get("servers")
        for method in METHODS:
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            servers = operation.get("servers") or path_servers or spec_servers
            hosts = _hosts_from_servers(servers)
            tokens = operation.get("x-token-types") or []
            yield {
                "fingerprint": _fingerprint(operation),
                "method": method.upper(),
                "path": path,
                "hosts": hosts,
                "file": filename,
                "section": section,
                "tags": list(operation.get("tags") or []),
                "summary": (operation.get("summary") or "").strip(),
                "operationId": operation.get("operationId") or "",
                "category": operation.get("x-category") or "",
                "tokens": tokens if isinstance(tokens, list) else [tokens],
                "readonly": bool(operation.get("x-readonly-method")),
                "deprecated": bool(operation.get("deprecated")),
            }


def build_index(swagger_dir: Path = SWAGGER_DIR) -> dict[str, Any]:
    """Собирает компактный индекс всех эндпоинтов снимка."""
    endpoints: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []

    for path in spec_files(swagger_dir):
        spec = load_spec(path)
        records = list(iter_operations(spec, path.name))
        endpoints.extend(records)
        files.append(
            {
                "file": path.name,
                "title": (spec.get("info") or {}).get("title") or path.name,
                "version": (spec.get("info") or {}).get("version") or "",
                "endpoints": len(records),
            }
        )

    endpoints.sort(key=lambda r: (r["file"], r["path"], r["method"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files,
        "endpoints": endpoints,
    }


def load_index() -> dict[str, Any]:
    if INDEX_PATH.exists():
        with INDEX_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    if not spec_files():
        raise SystemExit(
            "Снимок пуст: в swagger/ нет YAML-файлов.\n"
            "Обновите: git pull, либо соберите снимок сами — python scripts/update.py"
        )
    print("! Индекс swagger/_index.json отсутствует, собираю на лету", file=sys.stderr)
    return build_index()


def load_meta() -> dict[str, Any]:
    if not META_PATH.exists():
        return {}
    with META_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def snapshot_age_days() -> float | None:
    meta = load_meta()
    stamp = meta.get("updated_at")
    if not stamp:
        return None
    try:
        updated = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - updated).total_seconds() / 86400


def freshness_line() -> str:
    age = snapshot_age_days()
    meta = load_meta()
    if age is None:
        return "Снимок: дата неизвестна (нет swagger/_meta.json)"
    date = str(meta.get("updated_at", ""))[:10]
    mark = "  << УСТАРЕЛ, обновите: git pull" if age > STALE_AFTER_DAYS else ""
    return f"Снимок: {date}, возраст {age:.0f} дн., источник {meta.get('source', '?')}{mark}"


# --------------------------------------------------------------------------
# $ref
# --------------------------------------------------------------------------


def resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        return None
    node: Any = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


def deref(spec: dict[str, Any], node: Any, seen: frozenset[str] = frozenset()) -> Any:
    """Разворачивает $ref на один уровень, защищаясь от циклов."""
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node
    if ref in seen:
        return {"description": f"<цикл {ref}>"}
    target = resolve_ref(spec, ref)
    if target is None:
        return {"description": f"<не найден {ref}>"}
    return deref(spec, target, seen | {ref})


# --------------------------------------------------------------------------
# Рендер схем
# --------------------------------------------------------------------------


def _type_label(schema: dict[str, Any]) -> str:
    kind = schema.get("type")
    if not kind:
        for combinator in ("oneOf", "anyOf", "allOf"):
            if combinator in schema:
                return combinator
        return "object" if "properties" in schema else "any"
    if kind == "array":
        return "array"
    fmt = schema.get("format")
    return f"{kind}<{fmt}>" if fmt else str(kind)


def _short(text: Any, limit: int = 110) -> str:
    if not text:
        return ""
    flat = re.sub(r"\s+", " ", str(text)).strip()
    flat = re.sub(r"<[^>]+>", "", flat).strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def render_schema(
    spec: dict[str, Any],
    schema: Any,
    indent: int = 2,
    depth: int = 0,
    lines: list[str] | None = None,
    required: set[str] | None = None,
    name: str | None = None,
) -> list[str]:
    lines = lines if lines is not None else []
    schema = deref(spec, schema)
    if not isinstance(schema, dict):
        return lines

    pad = " " * indent
    label = _type_label(schema)

    if name is not None:
        flag = ", обяз." if required and name in required else ""
        note = _short(schema.get("description"))
        enum = schema.get("enum")
        extra = f" enum: {', '.join(map(str, enum[:8]))}" if enum else ""
        lines.append(f"{pad}{name} ({label}{flag})" + (f" — {note}" if note else "") + extra)

    if depth >= MAX_SCHEMA_DEPTH:
        return lines

    if label == "array":
        items = deref(spec, schema.get("items"))
        if isinstance(items, dict) and (items.get("properties") or items.get("items")):
            render_schema(spec, items, indent + 2, depth + 1, lines)
        elif isinstance(items, dict) and name is not None:
            lines[-1] = lines[-1].replace("(array", f"(array of {_type_label(items)}", 1)
        return lines

    for combinator in ("oneOf", "anyOf", "allOf"):
        for variant in schema.get(combinator) or []:
            render_schema(spec, variant, indent + (2 if name else 0), depth + 1, lines)

    properties = schema.get("properties")
    if isinstance(properties, dict):
        req = set(schema.get("required") or [])
        child_indent = indent + 2 if name is not None else indent
        for prop_name, prop_schema in properties.items():
            render_schema(spec, prop_schema, child_indent, depth + 1, lines, req, prop_name)

    return lines


# --------------------------------------------------------------------------
# Команды
# --------------------------------------------------------------------------


def cmd_map(args: argparse.Namespace) -> int:
    index = load_index()
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in index["endpoints"]:
        by_file[record["file"]].append(record)

    print(f"Wildberries Seller API — {len(index['endpoints'])} эндпоинтов, {len(index['files'])} разделов")
    print(freshness_line())
    print()

    for entry in index["files"]:
        records = by_file.get(entry["file"], [])
        hosts = sorted({h for r in records for h in r["hosts"]})
        print(f"{entry['title']} ({len(records)}) — swagger/{entry['file']}")
        if hosts:
            print(f"  хосты: {', '.join(hosts)}")
        tags = Counter(tag for r in records for tag in r["tags"])
        for tag, count in tags.most_common():
            print(f"  - {tag} ({count})")
        print()
    return 0


def _score(record: dict[str, Any], words: list[str]) -> int:
    haystacks = (
        (record["path"].lower(), 5),
        (record["summary"].lower(), 4),
        (" ".join(record["tags"]).lower(), 3),
        (record["operationId"].lower(), 3),
        (record["section"].lower(), 1),
    )
    total = 0
    for word in words:
        for text, weight in haystacks:
            if word in text:
                total += weight
    return total


def cmd_search(args: argparse.Namespace) -> int:
    index = load_index()
    words = [w for w in re.split(r"\s+", args.query.lower().strip()) if w]
    if not words:
        print("Пустой запрос")
        return 2

    candidates = index["endpoints"]
    if args.tag:
        needle = args.tag.lower()
        candidates = [r for r in candidates if any(needle in t.lower() for t in r["tags"])]

    scored = [(s, r) for r in candidates if (s := _score(r, words)) > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["path"]))

    if not scored:
        print(f"Ничего не найдено по запросу: {args.query}")
        print("Попробуйте другие слова или python scripts/wb.py map")
        return 1

    print(f"Найдено {len(scored)}, показано {min(len(scored), args.limit)}:")
    print()
    for _, record in scored[: args.limit]:
        host = record["hosts"][0] if record["hosts"] else "-"
        flags = []
        if record["deprecated"]:
            flags.append("DEPRECATED")
        if record["tokens"]:
            flags.append("токен: " + ", ".join(record["tokens"]))
        suffix = f"  [{'; '.join(flags)}]" if flags else ""
        print(f"{record['method']:6} {record['path']}")
        print(f"       {record['summary']}")
        print(f"       {host} · {record['tags'][0] if record['tags'] else '-'} · swagger/{record['file']}{suffix}")
    return 0


def _find_operation(method: str, path: str) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    """Возвращает (файл, spec, path_item, operation)."""
    for spec_path in spec_files():
        spec = load_spec(spec_path)
        item = (spec.get("paths") or {}).get(path)
        if not isinstance(item, dict):
            continue
        operation = item.get(method.lower())
        if isinstance(operation, dict):
            return spec_path, spec, item, operation
    return None


def resolve_path_arg(raw: str) -> str:
    """Приводит аргумент к пути из спецификации.

    Git Bash на Windows разворачивает аргумент, начинающийся со слэша, в путь
    файловой системы: /content/v2/... превращается в C:/Program Files/Git/content/v2/...
    Поэтому путь ищется ещё и по совпадению окончания.
    """
    known = {record["path"] for record in load_index()["endpoints"]}
    if raw in known:
        return raw
    slashed = raw if raw.startswith("/") else "/" + raw
    if slashed in known:
        return slashed
    tail_matches = sorted((p for p in known if raw.endswith(p)), key=len, reverse=True)
    return tail_matches[0] if tail_matches else slashed


def cmd_detail(args: argparse.Namespace) -> int:
    method = args.method.upper()
    args.path = resolve_path_arg(args.path)
    found = _find_operation(method, args.path)
    if found is None:
        print(f"Не найдено: {method} {args.path}")
        index = load_index()
        close = [r for r in index["endpoints"] if args.path.lower() in r["path"].lower()][:8]
        if close:
            print("\nПохожие пути:")
            for record in close:
                print(f"  {record['method']:6} {record['path']}")
        return 1

    spec_path, spec, path_item, operation = found
    servers = operation.get("servers") or path_item.get("servers") or spec.get("servers")
    hosts = _hosts_from_servers(servers)

    print(f"{method} {args.path}")
    print(f"Раздел:   {(spec.get('info') or {}).get('title', '')} (swagger/{spec_path.name})")
    print(f"Хост:     {', '.join('https://' + h for h in hosts) or '—'}")
    print(f"Теги:     {', '.join(operation.get('tags') or []) or '—'}")
    if operation.get("summary"):
        print(f"Кратко:   {operation['summary']}")
    if operation.get("x-token-types"):
        print(f"Токен:    {', '.join(operation['x-token-types'])}")
    if operation.get("x-category"):
        print(f"Категория:{operation['x-category']}")
    if operation.get("deprecated"):
        print("ВНИМАНИЕ: эндпоинт помечен deprecated")

    security = operation.get("security") or spec.get("security") or []
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    names = [name for rule in security for name in rule]
    if names:
        described = []
        for name in names:
            scheme = schemes.get(name) or {}
            described.append(f"{name} ({scheme.get('in', '?')}: {scheme.get('name', '?')})")
        print(f"Авторизация: {', '.join(described)}")

    description = operation.get("description")
    if description:
        print("\nОписание:")
        for line in str(description).splitlines():
            print(f"  {line}")

    parameters = list(path_item.get("parameters") or []) + list(operation.get("parameters") or [])
    if parameters:
        print("\nПараметры:")
        for raw in parameters:
            param = deref(spec, raw)
            schema = deref(spec, param.get("schema") or {})
            req = ", обяз." if param.get("required") else ""
            note = _short(param.get("description"))
            print(f"  {param.get('name', '?')} ({param.get('in', '?')}, {_type_label(schema)}{req})"
                  + (f" — {note}" if note else ""))
            if args.schemas and (schema.get("properties") or schema.get("items")):
                for line in render_schema(spec, schema, indent=4):
                    print(line)

    body = deref(spec, operation.get("requestBody") or {})
    if body:
        print("\nТело запроса:" + (" (обязательно)" if body.get("required") else ""))
        for media, media_obj in (body.get("content") or {}).items():
            print(f"  {media}")
            schema = (media_obj or {}).get("schema")
            if args.schemas:
                for line in render_schema(spec, schema, indent=4):
                    print(line)
            else:
                resolved = deref(spec, schema)
                keys = list((resolved.get("properties") or {}).keys())
                if keys:
                    print(f"    поля: {', '.join(keys[:20])}" + (" …" if len(keys) > 20 else ""))
                print("    (полная схема: добавьте --schemas)")

    responses = operation.get("responses") or {}
    if responses:
        print("\nОтветы:")
        for code, raw in responses.items():
            response = deref(spec, raw)
            print(f"  {code} — {_short(response.get('description')) or '—'}")
            if not args.schemas:
                continue
            for media, media_obj in (response.get("content") or {}).items():
                print(f"    {media}")
                for line in render_schema(spec, (media_obj or {}).get("schema"), indent=6):
                    print(line)
    return 0


def cmd_protocol(args: argparse.Namespace) -> int:
    index = load_index()
    schemes: dict[str, Any] = {}
    codes: Counter[str] = Counter()
    for spec_path in spec_files():
        spec = load_spec(spec_path)
        schemes.update((spec.get("components") or {}).get("securitySchemes") or {})
        for item in (spec.get("paths") or {}).values():
            if not isinstance(item, dict):
                continue
            for method in METHODS:
                operation = item.get(method)
                if isinstance(operation, dict):
                    codes.update((operation.get("responses") or {}).keys())

    print("Протокол Wildberries Seller API (из локального снимка)")
    print(freshness_line())

    print("\nАвторизация:")
    for name, scheme in schemes.items():
        print(f"  {name}: {scheme.get('type')} в {scheme.get('in')}, заголовок {scheme.get('name')}")
    print("  Токен создаётся в кабинете продавца, передаётся как есть, без префикса Bearer.")

    hosts = Counter(h for r in index["endpoints"] for h in r["hosts"])
    print("\nХосты:")
    for host, count in hosts.most_common():
        print(f"  https://{host} ({count} эндпоинтов)")

    tokens = Counter(t for r in index["endpoints"] for t in r["tokens"])
    if tokens:
        print("\nКатегории токенов, заданные явно (x-token-types):")
        for token, count in tokens.most_common():
            print(f"  {token} ({count})")
        print("  Для остальных эндпоинтов категория определяется хостом/разделом.")

    print("\nКоды ответов, встречающиеся в спецификациях:")
    for code, count in sorted(codes.items()):
        print(f"  {code} ({count})")

    print("\nЛимиты запросов в машиночитаемом виде WB не публикует —")
    print("они описаны текстом в поле description конкретных операций.")
    print("Смотрите: python scripts/wb.py detail <METHOD> <PATH>")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    problems: list[str] = []
    warnings: list[str] = []
    broken_refs: list[str] = []
    seen: dict[tuple[str, str], str] = {}
    total = 0

    files = spec_files()
    if not files:
        print("В swagger/ нет YAML-файлов. Обновите: git pull, либо python scripts/update.py")
        return 1

    for spec_path in files:
        try:
            spec = load_spec(spec_path)
        except Exception as exc:  # noqa: BLE001 - показать пользователю причину
            problems.append(f"{spec_path.name}: не парсится — {exc}")
            continue

        if not str(spec.get("openapi", "")).startswith("3."):
            problems.append(f"{spec_path.name}: нет openapi: 3.x")
        if not spec.get("paths"):
            problems.append(f"{spec_path.name}: пустой paths")

        for record in iter_operations(spec, spec_path.name):
            total += 1
            key = (record["method"], record["path"])
            if key in seen:
                problems.append(
                    f"дубль {record['method']} {record['path']}: {seen[key]} и {spec_path.name}"
                )
            else:
                seen[key] = spec_path.name
            if not record["hosts"]:
                warnings.append(f"{spec_path.name}: {record['method']} {record['path']} — не определён хост")

        # Битые $ref — дефекты в спецификациях самого WB, чинить их нам нечем.
        # Это предупреждение, а не ошибка: иначе validate падал бы всегда.
        for ref in sorted(set(_collect_refs(spec))):
            if ref.startswith("#/") and resolve_ref(spec, ref) is None:
                broken_refs.append(f"{spec_path.name}: битый $ref {ref} (дефект спецификации WB)")

    print(f"Файлов: {len(files)}, эндпоинтов: {total}")

    if INDEX_PATH.exists():
        index = load_index()
        indexed = {(r["method"], r["path"]) for r in index["endpoints"]}
        if indexed != set(seen):
            missing = len(set(seen) - indexed)
            extra = len(indexed - set(seen))
            problems.append(f"индекс разошёлся с YAML: нет в индексе {missing}, лишних {extra}")
        else:
            print("Индекс сходится с YAML")
    else:
        warnings.append("нет swagger/_index.json")

    for warning in sorted(set(warnings))[:20]:
        print(f"! {warning}")
    if len(set(warnings)) > 20:
        print(f"! …ещё {len(set(warnings)) - 20} предупреждений")

    if broken_refs:
        print(f"\nБитых $ref в спецификациях WB: {len(broken_refs)}")
        for ref in broken_refs[:10]:
            print(f"  ! {ref}")
        if len(broken_refs) > 10:
            print(f"  ! …ещё {len(broken_refs) - 10}")

    if problems:
        print(f"\nОШИБОК: {len(problems)}")
        for problem in problems[:40]:
            print(f"  x {problem}")
        return 1

    print("\nOK: ошибок нет")
    return 0


def _collect_refs(node: Any, acc: list[str] | None = None) -> list[str]:
    acc = acc if acc is not None else []
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            acc.append(ref)
        for value in node.values():
            _collect_refs(value, acc)
    elif isinstance(node, list):
        for value in node:
            _collect_refs(value, acc)
    return acc


def cmd_stale(args: argparse.Namespace) -> int:
    meta = load_meta()
    age = snapshot_age_days()
    print(freshness_line())
    if meta.get("renamed_sections"):
        print(f"Переименования при последнем обновлении: {', '.join(meta['renamed_sections'])}")
    print(f"Эндпоинтов: {meta.get('endpoint_count', '?')}, файлов: {meta.get('file_count', '?')}")

    stale = age is not None and age > STALE_AFTER_DAYS
    if stale:
        print(f"\nСнимок старше {STALE_AFTER_DAYS} дней. Обновите: git pull")
        print("Если снимок в репозитории тоже несвежий — соберите свой: python scripts/update.py")
    return 1 if (stale and args.fail_if_stale) else 0


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(
        prog="wb.py",
        description="Локальный справочник по Wildberries Seller API",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("map", help="разделы, теги, хосты, счётчики").set_defaults(func=cmd_map)

    search = sub.add_parser("search", help="поиск эндпоинтов")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=15)
    search.add_argument("--tag", default="")
    search.set_defaults(func=cmd_search)

    detail = sub.add_parser("detail", help="подробности эндпоинта")
    detail.add_argument("method")
    detail.add_argument("path")
    detail.add_argument("--schemas", action="store_true", help="развернуть схемы тела и ответов")
    detail.set_defaults(func=cmd_detail)

    sub.add_parser("protocol", help="авторизация, хосты, токены, коды").set_defaults(func=cmd_protocol)
    sub.add_parser("validate", help="проверка целостности снимка").set_defaults(func=cmd_validate)
    stale = sub.add_parser("stale", help="возраст снимка")
    stale.add_argument(
        "--fail-if-stale",
        action="store_true",
        help=f"код возврата 1, если снимку больше {STALE_AFTER_DAYS} дней",
    )
    stale.set_defaults(func=cmd_stale)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
