# Изменения Wildberries API

## 2026-08-16

Источник: dev.wildberries.ru. Эндпоинтов: 288 → 286.

### Удалены эндпоинты (2)
- `GET /api/v1/analytics/banned-products/shadowed` — Скрытые из каталога (12-reports.yaml)
- `POST /api/analytics/v1/item-rating` — Получить отчёт (11-analytics.yaml)

### Изменены (45)
- `DELETE /adv/v0/normquery/bids` — Удалить ставки поисковых кластеров (08-promotion.yaml)
- `GET /adv/v0/delete` — Удаление кампании (08-promotion.yaml)
- `GET /adv/v0/pause` — Пауза кампании (08-promotion.yaml)
- `GET /adv/v0/start` — Запуск кампании (08-promotion.yaml)
- `GET /adv/v0/stop` — Завершение кампании (08-promotion.yaml)
- `GET /adv/v1/advert` — Информация о медиакампании (08-promotion.yaml)
- `GET /adv/v1/adverts` — Список медиакампаний (08-promotion.yaml)
- `GET /adv/v1/balance` — Баланс (08-promotion.yaml)
- `GET /adv/v1/budget` — Бюджет кампании (08-promotion.yaml)
- `GET /adv/v1/count` — Количество медиакампаний (08-promotion.yaml)
- `GET /adv/v1/payments` — Получение истории пополнений счёта (08-promotion.yaml)
- `GET /adv/v1/promotion/count` — Списки кампаний (08-promotion.yaml)
- `GET /adv/v1/supplier/subjects` — Предметы для кампаний (08-promotion.yaml)
- `GET /adv/v1/upd` — Получение истории затрат (08-promotion.yaml)
- `GET /adv/v3/fullstats` — Статистика кампаний (08-promotion.yaml)
- `GET /api/advert/v0/bids/recommendations` — Рекомендуемые ставки для карточек товаров и поисковых кластеров (08-promotion.yaml)
- `GET /api/advert/v1/config` — Конфигурационные значения продвижения (08-promotion.yaml)
- `GET /api/advert/v2/adverts` — Информация о кампаниях (08-promotion.yaml)
- `GET /api/marketplace/v3/fbs/settings/autoreturns` — Получить настройки автовозврата продавца (03-orders-fbs.yaml)
- `GET /api/marketplace/v3/fbs/settings/autoreturns/subcategories/restricted` — Получить предметы, которые не хранятся на складах WB (03-orders-fbs.yaml)
- `GET /api/v1/calendar/promotions` — Список акций (08-promotion.yaml)
- `GET /api/v1/calendar/promotions/details` — Детальная информация об акциях (08-promotion.yaml)
- `GET /api/v1/calendar/promotions/nomenclatures` — Список товаров для участия в акции (08-promotion.yaml)
- `PATCH /adv/v0/auction/nms` — Изменение списка карточек товаров в кампаниях (08-promotion.yaml)
- `PATCH /api/advert/v1/bids` — Изменение ставок в кампаниях (08-promotion.yaml)
- `PATCH /api/marketplace/v3/fbs/settings/autoreturns` — Обновить настройки автовозврата продавца (03-orders-fbs.yaml)
- `PATCH /api/marketplace/v3/fbs/settings/autoreturns/items` — Обновить настройки автовозврата товаров (03-orders-fbs.yaml)
- `POST /adv/v0/normquery/bids` — Установить ставки для поисковых кластеров (08-promotion.yaml)
- `POST /adv/v0/normquery/get-bids` — Список ставок поисковых кластеров (08-promotion.yaml)
- `POST /adv/v0/normquery/get-minus` — Список минус-фраз кампаний (08-promotion.yaml)
- `POST /adv/v0/normquery/list` — Списки активных и неактивных поисковых кластеров (08-promotion.yaml)
- `POST /adv/v0/normquery/set-minus` — Установка и удаление минус-фраз (08-promotion.yaml)
- `POST /adv/v0/normquery/stats` — Статистика поисковых кластеров (08-promotion.yaml)
- `POST /adv/v0/rename` — Переименование кампании (08-promotion.yaml)
- `POST /adv/v1/budget/deposit` — Пополнение бюджета кампании (08-promotion.yaml)
- `POST /adv/v1/normquery/stats` — Статистика по поисковым кластерам с детализацией по дням (08-promotion.yaml)
- `POST /adv/v1/stats` — Статистика медиакампаний (08-promotion.yaml)
- `POST /adv/v2/seacat/save-ad` — Создать кампанию (08-promotion.yaml)
- `POST /adv/v2/supplier/nms` — Карточки товаров для кампаний (08-promotion.yaml)
- `POST /api/advert/v1/bids/min` — Минимальные ставки для карточек товаров (08-promotion.yaml)
- `POST /api/content/v1/recommendations/list` — Список рекомендаций в карточках товаров (02-items.yaml)
- `POST /api/content/v1/recommendations/set` — Установить рекомендации для товаров (02-items.yaml)
- `POST /api/marketplace/v3/fbs/settings/autoreturns/items` — Получить настройки автовозврата товаров (03-orders-fbs.yaml)
- `POST /api/v1/calendar/promotions/upload` — Добавить товар в акцию (08-promotion.yaml)
- `PUT /adv/v0/auction/placements` — Изменение мест размещения в кампаниях с ручной ставкой (08-promotion.yaml)

История пополняется автоматически при каждом запуске `python scripts/update.py`:
скрипт сравнивает новый снимок с предыдущим и дописывает сюда, какие эндпоинты
у WB появились, исчезли или изменились.

## 2026-08-12

Первый снимок: 288 эндпоинтов в 13 разделах, загружен напрямую с dev.wildberries.ru.
