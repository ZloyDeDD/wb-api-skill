# wb-api-skill

[![tests](https://github.com/ZloyDeDD/wb-api-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/ZloyDeDD/wb-api-skill/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/ZloyDeDD/wb-api-skill?display_name=tag)](https://github.com/ZloyDeDD/wb-api-skill/releases/latest)
![snapshot](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FZloyDeDD%2Fwb-api-skill%2Fmain%2Fswagger%2F_meta.json&query=%24.snapshot_date&label=snapshot)
![endpoints](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FZloyDeDD%2Fwb-api-skill%2Fmain%2Fswagger%2F_meta.json&query=%24.endpoint_count&label=endpoints)

Скилл для Claude Code (и других агентов, читающих `SKILL.md`) — справочник по **Wildberries Seller API** поверх снимка OpenAPI-спецификаций, который **регулярно обновляется**.

Главное отличие от аналогов: документация здесь не приколочена гвоздями. Снимок сверяется с порталом WB примерно раз в месяц; что появилось, исчезло или изменилось — в [Releases](https://github.com/ZloyDeDD/wb-api-skill/releases) и `CHANGELOG.md`. Дата снимка и число эндпоинтов — в бейджах выше. Если ждать не хочется, `scripts/update.py` соберёт свежий снимок локально той же командой, которой пользуется мейнтейнер.

## Установка

Claude Code, личный скилл:

```bash
git clone https://github.com/ZloyDeDD/wb-api-skill.git ~/.claude/skills/wb-api
python -m pip install -r ~/.claude/skills/wb-api/requirements.txt
```

Скилл в проекте — то же самое в `.claude/skills/wb-api`.

Каталог называется `wb-api`, без суффикса: Claude Code ищет скилл по имени каталога, и оно должно совпадать с `name` в `SKILL.md`.

Для обновления снимка нужен браузерный драйвер (см. «Как это работает»):

```bash
python -m pip install -r requirements-update.txt
```

## Использование

Скилл подхватывается сам, когда речь заходит о Wildberries API, карточках товаров, ценах, остатках, заказах, поставках, отзывах, аналитике, отчётах, продвижении, тарифах или финансах.

Примеры запросов:

```
Какой эндпоинт WB отдаёт остатки на складах продавца?
Покажи схему запроса и ответа для POST /content/v2/get/cards/list
Сгенерируй Python-клиент для сборочных заданий FBS
На каком хосте живёт аналитика WB?
```

## Справочник

```bash
python scripts/wb.py map                                   # разделы, теги, хосты
python scripts/wb.py search "остатки на складах"           # поиск эндпоинтов
python scripts/wb.py search "отзывы" --tag Отзывы --limit 5
python scripts/wb.py detail GET /api/v3/stocks
python scripts/wb.py detail POST /content/v2/get/cards/list --schemas
python scripts/wb.py protocol                              # авторизация, хосты, токены, коды
python scripts/wb.py validate                              # целостность снимка
python scripts/wb.py stale                                 # возраст снимка
```

Сети `wb.py` не трогает и клиентом к API не является: он читает локальные YAML и печатает компактный результат, чтобы агенту не приходилось загружать в контекст мегабайты спецификаций.

Поиск идёт по `swagger/_index.json` — плоскому индексу всех эндпоинтов, который пересобирается при обновлении. Сырой YAML читается только в `detail` и только для запрошенной операции.

## Обновление

Снимок ведёт мейнтейнер: сверяет его с порталом WB примерно раз в месяц и выкладывает результат сюда. Свежесть видно по бейджам `snapshot` и `release`, содержание изменений — в [Releases](https://github.com/ZloyDeDD/wb-api-skill/releases) и `CHANGELOG.md`.

Обновиться:

```bash
git -C ~/.claude/skills/wb-api pull
```

Без git — скачайте `wb-swagger-*.zip` из последнего релиза и распакуйте поверх `swagger/`.

### Собрать снимок самому

Нужно, если ждать очередной сверки не хочется или проект перестали вести:

```bash
python -m pip install -r requirements-update.txt
python scripts/update.py             # обновить снимок
python scripts/update.py --dry-run   # показать изменения, ничего не писать
```

Что происходит:

1. **Загрузка.** Все разделы из `sources.yaml` качаются с `dev.wildberries.ru` через браузер.
2. **Починка переименований.** WB регулярно меняет имена файлов: `02-products` → `02-items`, `10-tariffs` → `10-rates`, `05-orders-dbs` → `05-dbs`. Если раздел отвечает 404, скрипт открывает страницу его документации по слагу, читает оттуда актуальное `x-file-name`, скачивает раздел под новым именем и правит `sources.yaml`. Вмешательство нужно, только если WB сменит сам слаг или заведёт новый раздел.
3. **Валидация до записи.** Каждый файл должен начинаться с `openapi:`, парситься, иметь непустой `paths`, а суммарное число эндпоинтов — не просесть больше чем на 10%. Не прошло — на диске ничего не меняется, код возврата ненулевой.
4. **Атомарная подмена** `swagger/`, пересборка `_index.json` и `_meta.json`.
5. **Отчёт.** Что добавилось, что удалено, что изменилось — в консоль и в `CHANGELOG.md`.

Локальный снимок при этом расходится с репозиторием — следующий `git pull` попросит разрешить конфликт в `swagger/`. Проще всего откатиться на версию из репозитория: `git checkout -- swagger CHANGELOG.md`.

### Как выпускается релиз

Для мейнтейнера. Скачивание спек остаётся локальным — антибот WB требует видимого браузера, из CI челлендж не пройти. Автоматизирована только сборка релиза:

```bash
python scripts/update.py             # забрать свежие спеки
python scripts/release.py --dry-run  # показать коммит, тег и заметки
python scripts/release.py            # коммит, тег, пуш
```

`release.py` коммитит снимок и, **если у WB что-то поменялось**, ставит тег по дате снимка — `v2026.08.12` (при повторе в тот же день `v2026.08.12.1`). Пустая сверка — обычный коммит без тега, чтобы лента релизов не забивалась записями «изменений нет».

Пуш тега запускает `.github/workflows/release.yml`: он берёт заметки из свежей секции `CHANGELOG.md` (`scripts/release_notes.py`), прикладывает архив `swagger/` и публикует релиз.

## Как это работает

Спеки лежат по адресу `https://dev.wildberries.ru/api/swagger/yaml/ru/<файл>?region=ru`, но взять их простым HTTP-запросом нельзя: портал закрыт антиботом WBAAS и отдаёт `HTTP 498` с JS-челленджем вместо YAML — с любого IP и с любым User-Agent.

Челлендж проходит только настоящий браузер, и с двумя оговорками:

- **headless блокируется** — Chrome запускается видимым окном;
- **обычный Playwright тоже блокируется**: он выставляет `navigator.webdriver = true`, антибот это видит и показывает «Подозрительная активность» бесконечно.

Поэтому `scripts/fetch_wb.py` использует **[patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)** — форк Playwright, который этот признак прячет. С ним челлендж проходится за пару секунд, дальше все разделы качаются в одной сессии через `fetch()` в контексте страницы.

Если patchright не установлен, скрипт пробует обычный playwright и, если антибот не пустил, честно об этом сообщает. Снимок при этом остаётся нетронутым.

### Почему без зеркал

Готовые зеркала спек на GitHub существуют и удобны, но у них своя задержка, и отстают они незаметно. Показательный случай: одно такое зеркало продолжало отдавать раздел DBS под старым именем `05-orders-dbs.yaml` уже после того, как WB переименовал его в `05-dbs.yaml`, — и вместе с именем застыло содержимое, в котором не хватало эндпоинта `POST /api/marketplace/v3/dbs/orders/final-price`. Снаружи это выглядит как совершенно нормальный свежий снимок.

Прямая загрузка стоит одного видимого окна Chrome на минуту раз в месяц и снимает весь класс таких проблем.

## Тесты

```bash
python tests/test_update.py
```

Сеть не используется, браузер подменяется заглушкой. Проверяются восстановление переименованных разделов, отбраковка мусора вместо перезаписи снимка и отчёт об изменениях.

## Состав репозитория

| Путь | Что это |
|------|---------|
| `SKILL.md` | инструкции агенту |
| `swagger/*.yaml` | снимок OpenAPI-спецификаций WB (русские) |
| `swagger/_index.json` | плоский индекс эндпоинтов для быстрого поиска |
| `swagger/_meta.json` | дата снимка, счётчики, sha256 файлов, переименования |
| `scripts/wb.py` | справочник по снимку |
| `scripts/update.py` | обновление снимка |
| `scripts/fetch_wb.py` | загрузка с WB через браузер |
| `scripts/release.py` | коммит, тег и пуш свежего снимка |
| `scripts/release_notes.py` | заметки к релизу из `CHANGELOG.md` |
| `sources.yaml` | список разделов и пороги валидации |
| `tests/test_update.py` | тесты защитной логики |
| `.github/workflows/` | тесты, сборка релиза по тегу, напоминание о возрасте снимка |
| `CHANGELOG.md` | история изменений API |

## Лицензия

Код — MIT (см. `LICENSE`). Спецификации в `swagger/` принадлежат Wildberries; подробности в `NOTICE`.
