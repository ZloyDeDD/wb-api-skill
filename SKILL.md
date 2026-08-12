---
name: wildberries-api
description: Swagger-backed Wildberries seller API reference for WB marketplace integrations. Use when building or debugging code that calls Wildberries/WB seller API endpoints, choosing endpoints, checking request/response schemas, authentication headers, hosts, rate limits, or API capabilities.
---

# Wildberries Seller API

Локальный снимок OpenAPI-спецификаций в `swagger/*.yaml` — единственный источник истины по этому API. Отвечай по нему, а не по памяти: WB меняет эндпоинты часто, и то, что ты помнишь, скорее всего устарело.

## Порядок работы

Помощник требует PyYAML. Если его нет: `python -m pip install -r requirements.txt`.

1. Начинай с компактных запросов к снимку:
   - обзор разделов: `python scripts/wb.py map`
   - поиск: `python scripts/wb.py search "<запрос>" --limit 15`
   - конкретный эндпоинт: `python scripts/wb.py detail <METHOD> <PATH>`
   - со схемами тела и ответов: `python scripts/wb.py detail <METHOD> <PATH> --schemas`
   - авторизация, хосты, токены, коды: `python scripts/wb.py protocol`
2. Сырой `swagger/*.yaml` открывай только когда вывода скрипта не хватает: нужны вложенные примеры, значения enum или длинное описание целиком. Целиком файлы не читай — они по 100–350 КБ.
3. Целостность снимка: `python scripts/wb.py validate`.

## Свежесть

Перед содержательным ответом по API сверься с `python scripts/wb.py stale`.

Снимок старше 30 дней — скажи об этом пользователю прямо: назови дату снимка и предложи `git pull` (снимок в репозитории обновляет мейнтейнер). Если и там несвежо — предложи собрать свой снимок: `python scripts/update.py`. Не делай вид, что данные свежие.

Если пользователь ждёт эндпоинт, которого в снимке нет, — так и скажи: «в снимке от такой-то даты этого нет». Не выдумывай путь и не подгоняй похожий. Предложи обновить снимок.

## Правила ответа

- Указывай метод, путь, хост, файл-источник (`swagger/NN-name.yaml`), схему авторизации, тип токена и релевантные коды ответов.
- Хост бери с самой операции: у WB он разный для разных доменов (`content-api`, `marketplace-api`, `advert-api`, `statistics-api`, `seller-analytics-api`, `common-api` и другие). Общего хоста нет.
- Лимиты запросов WB в машиночитаемом виде не публикует — они описаны текстом внутри `description` конкретной операции. Приводи их оттуда дословно, не выдумывай числа.
- Не сочиняй общие правила протокола. Всё, что говоришь про авторизацию, песочницу или статус-коды, должно опираться на `securitySchemes`, `servers`, `x-token-types` и `responses` из снимка.
- Эндпоинт с `deprecated: true` предлагай только если замены нет, и обязательно предупреждай.

## Генерация кода

- Токен читай из переменной окружения или конфига, никогда не зашивай в код.
- Передавай токен в заголовке `Authorization` по схеме `HeaderApiKey` — как есть, без префикса `Bearer`.
- Базовый URL бери с той операции, которую вызываешь.
- Пагинацию, поллинг задач, ретраи и валидацию полей добавляй только там, где этого требует схема или описание эндпоинта.

## Обновление снимка

Обычный путь — `git pull`: снимок сверяется с порталом WB примерно раз в месяц, изменения описаны в релизах и `CHANGELOG.md`.

`python scripts/update.py` — собрать свежий снимок самому: качает спеки напрямую с dev.wildberries.ru, проверяет результат до записи и дописывает в `CHANGELOG.md`, что изменилось в API. Нужен браузер и `requirements-update.txt`. Подробности в README.md.
