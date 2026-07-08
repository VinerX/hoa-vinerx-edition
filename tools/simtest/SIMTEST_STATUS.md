# SimTest Phase 1 — Итоги попытки автоматизации (2026-07-08)

## Что работает

| Компонент | Статус |
|-----------|--------|
| `-start_save=autosave` (без расширения) | ✅ Загружает сейв, пропуская главное меню |
| `-nolauncher` + `-start_save` | ❌ НЕ работает — `-start_save` требует Paradox Launcher |
| `-hands_off` + `-debug` | ✅ Игра авто-запускается после загрузки |
| Paradox Launcher → hoi4.exe | ✅ Лаунчер обрабатывает `-start_save` и запускает игру |
| Копирование сейва → autosave.hoi4 | ✅ Работает |
| `continue_game.json` | ✅ Обновляется, игра читает, но `-start_save` приоритетнее |
| `game.log` мониторинг | ✅ Читается, но **HOI4 обрезает файл при старте** (фикс: сброс offset=0 если размер уменьшился) |
| `error.log` мониторинг | ✅ Растёт монотонно во время загрузки |
| `psutil` для поиска/kill процессов | ✅ Находит PID игры отдельно от PID лаунчера |
| `on_startup` → `country_event` | ❓ События парсятся без ошибок, но `log` в `immediate` не появляется в game.log |
| `on_monthly` → `country_event` | ❓ Не тестировали — игра убивалась до первого месячного тика |

## Что НЕ работает (блокеры)

### 1. HOI4 обрезает `game.log` при каждом запуске
**Симптом:** После запуска размер game.log падает (было 1030 байт → стало 383).
**Фикс в runner.py:** `read_tail` сбрасывает offset на 0, если размер файла уменьшился.
**Статус:** ✅ исправлено.

### 2. `vx_simtest_events.txt` — ошибка парсинга
**Симптом:** `Unexpected token: } near line: 41`
**Причина:** `if = { limit = {...} log = "..." }` в одну строку не валиден в `immediate`.
**Фикс:** Разнесено на многострочный формат:
```txt
if = {
    limit = { ... }
    log = "..."
}
```
**Статус:** ✅ исправлено в dev, но НЕ протестировано (тест не перезапускался после фикса).

### 3. `[SIMTEST]` маркеры не появляются в game.log
**Симптом:** После загрузки сейва `on_unit_leader_created` пишется в game.log, а `[SIMTEST] STARTUP` — нет.
**Вероятная причина:** Комбинация багов #1 и #2:
- До фикса #2: события vx_simtest не грузились из-за ошибки парсинга → `country_event = vx_simtest.1` не срабатывал
- До фикса #1: даже если бы события сработали, game.log читался с неправильного offset

**Статус:** ⚠️ Оба фикса в коде, но не протестированы вместе.

### 4. Загрузка сейва занимает ~5-6 минут
**Причина:** 117 MB бинарный сейв + мод HOA с replace_path на большинство common/*
**Следствие:** Каждый тест-цикл > 5 минут только на загрузку.
**Решение:** Для production использовать более лёгкие сейвы (меньше стран, меньше юнитов).

### 5. `-start_save` требует Paradox Launcher
**Симптом:** Без лаунчера (с `-nolauncher`) флаг игнорируется, игра уходит в главное меню.
**Решение:** Запускать `hoi4.exe` БЕЗ `-nolauncher`, лаунчер обрабатывает `-start_save` и передаёт управление игре.

## Время загрузки (из логов)

| Стадия | Время от старта |
|--------|----------------|
| defines loaded | ~20 сек |
| provinces loaded | ~45 сек |
| Resetting game | ~90 сек |
| History execution done | ~2.5 мин |
| SINGLEPLAYER-game launch | ~5.5 мин |
| RestoreDeviceObjects | ~6 мин |
| Первый игровой тик | ~6.5 мин |

## Файлы в коммите

```
.gitignore                          (+4 строки — simtest generated dirs)
common/on_actions/vx_simtest_on_actions.txt   (test harness: on_startup/on_monthly → events)
events/vx_simtest_events.txt                  (vx_simtest.1 STARTUP, vx_simtest.2 CHECKPOINT)
localisation/english/vx_simtest_l_english.yml (minimal EN loc)
tools/simtest/runner.py                        (Python: launch, monitor, report)
```

## Gitignore (НЕ в коммите)

```
tools/simtest/reports/       — сгенерированные отчёты
tools/simtest/test_saves/    — бинарные сейвы (сотни MB)
tools/simtest/baselines/     — baseline error.log
tools/simtest/last_run.log   — отладочный лог раннера
```

## Что делать дальше

1. **Перезапустить тест** с обоими фиксами (parser + truncation). Если `[SIMTEST] STARTUP` появится — фаза 1 MVP работает.
2. **Дождаться первого `on_monthly` тика** (игра должна добежать до следующего месяца) — проверить `[SIMTEST] CHECKPOINT`.
3. **Уменьшить размер тестового сейва** — удалить ненужные страны/юниты, сохранить plaintext для быстрой загрузки.
4. **Добавить `TEST_COMPLETE`** — условие остановки по дате (пока раннер ждёт таймаут).
5. **Сделать `sync-to-rebuild` скрипт** — чтобы не копировать файлы вручную перед каждым тестом.
