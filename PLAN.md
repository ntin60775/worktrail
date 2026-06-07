# Worktrail v0.2 — Эволюция task-centric-knowledge

## Цель

Превратить worktrail из трекера времени в **единственный источник истины по задачам** —
полноценную замену `task-centric-knowledge` без его недостатков, сохранив лёгкость и git-nativity worktrail.

## Текущее состояние (v0.1)

### Что есть
- SQLite-ядро: таблицы `tasks`, `sessions`, `checkpoints`, `config`
- Учёт времени: `start → checkpoint → stop`
- Git-хуки: авто-чекпоинт на commit, авто-стоп/старт на checkout
- Статусная модель: 4 статуса (`active`, `paused`, `done`, `archived`)
- Простой CLI: `worktrail start/stop/checkpoint/status/report/init`
- Мигратор из `knowledge/tasks/`
- SKILL.md для агента
- Русский CLI, английский код, одна зависимость (`pyyaml`)

### Чего не хватает (против task-centric-knowledge)
- Журнал знаний: decisions, design, spec, notes — нет нигде
- Статусная модель: только 4 статуса, у t-c-k было 8
- Подзадачи: `parent_id` в схеме есть, но CLI не поддерживает
- Архивация: нет команды `archive`
- Легковесные исследования: нет режима exploration
- Группировка в инициативы: нет
- Экспорт задачи в Markdown: `report --save` только агрегированный

## Что предлагается (v0.2)

### 1. Таблица `journal` — база знаний задачи

```sql
CREATE TABLE journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    kind TEXT NOT NULL CHECK (kind IN ('proposal', 'design', 'spec', 'decision', 'note', 'artifact')),
    title TEXT,
    body TEXT,
    created_at TEXT NOT NULL
);
```

**Kind'ы:**
- `proposal` — «почему делаем задачу» (аналог OpenSpec proposal.md)
- `design` — «как будем делать» (аналог OpenSpec design.md)
- `spec` — инварианты в дельта-формате ADDED/MODIFIED/REMOVED (аналог упрощённого sdd.md)
- `decision` — ключевое решение с обоснованием (аналог decisions.md)
- `note` — свободная заметка, наблюдение
- `artifact` — ссылка на файл/скриншот/лог

**CLI:**
```bash
worktrail journal TASK-0037 --kind decision --title "Выбор GUI-стека" --body "..."
worktrail journal TASK-0037 --kind spec --title "API /tunnel/status" --body "ADDED: ..."
worktrail journal list TASK-0037
worktrail journal show TASK-0037 5   # по ID записи
```

**Экспорт:**
```bash
worktrail report --task TASK-0037 --save
# → .worktrail/reports/TASK-0037.md
# содержит: время + чекпоинты + journal (все kind'ы)
```

### 2. Расширенная статусная модель (8 статусов)

Взять проверенную модель из t-c-k:

```
draft → active → review → delivery → done → archived
                 ↘ blocked → active
                          ↘ cancelled
```

| Статус | Семантика |
|---|---|
| `draft` | Задача создана, работа не начата |
| `active` | В работе (tracker запущен) |
| `blocked` | Заблокирована внешней зависимостью |
| `review` | Код/решение на ревью |
| `delivery` | Поставка заказчику / выгрузка |
| `done` | Завершена |
| `archived` | В архиве |
| `cancelled` | Отменена |

**CLI:**
```bash
worktrail status TASK-0037 --set review
worktrail status TASK-0037 --set blocked --note "Ждём API ключ от заказчика"
```

### 3. Подзадачи — довести `parent_id` до рабочего состояния

**CLI:**
```bash
worktrail start TASK-0037.1 --parent TASK-0037 --name "Сайдбар: иконки статусов"
worktrail list --parent TASK-0037    # все подзадачи
```

**Правила:**
- Подзадача наследует статус родителя при создании
- `worktrail report --task TASK-0037 --recursive` включает подзадачи
- При стопе родителя с активными подзадачами — предупреждение

### 4. Команда `archive`

```bash
worktrail archive TASK-0037           # перенос в архив (done → archived)
worktrail archive TASK-0037 --force   # архивировать даже если не done
worktrail list --archived             # показать архив
```

- Завершённые задачи уходят из `worktrail status` по умолчанию
- `worktrail list --all` показывает всё включая архив
- Данные не удаляются, только статус меняется

### 5. Режим `explore` — легковесное исследование

```bash
worktrail explore "Разобраться в API OpenSpec"
worktrail explore "Почему падает тест на Wayland" --parent TASK-0037
```

- Создаёт задачу с kind=`exploration` (новое поле в tasks)
- Не требует `worktrail stop` — можно закрыть без подсчёта времени
- Можно добавить journal-записи с выводами
- Не засоряет список активных задач

**Схема:** добавить поле `kind TEXT DEFAULT 'task' CHECK (kind IN ('task', 'exploration', 'initiative'))`

### 6. Инициативы — группировка задач

```bash
worktrail initiative "Миграция на GTK4"            # создаёт initiative
worktrail start TASK-0037 --initiative "Миграция на GTK4"   # привязка задачи
worktrail initiative list                            # список инициатив
worktrail initiative show "Миграция на GTK4"         # прогресс по всем задачам инициативы
```

Инициатива — это задача с `kind='initiative'` (родитель верхнего уровня).

### 7. Поле `branch` в tasks — связь с git-веткой

```sql
ALTER TABLE tasks ADD COLUMN branch TEXT;
```

- При `worktrail start` авто-заполняется из `git branch --show-current`
- Позволяет `worktrail status` определять задачу по ветке (уже работает в git_bridge, но без сохранения)
- При архивации ветку можно удалить (с подтверждением)

### 8. Улучшение `report --save` — полноценный Markdown-экспорт

Структура экспорта одной задачи:
```markdown
# TASK-0037: Чиним сайдбар

**Статус:** done | **Ветка:** task/task-0037-fix-sidebar
**Создана:** 2026-05-20 | **Завершена:** 2026-05-22
**Общее время:** 4h 32m

## Чекпоинты
...

## Журнал (journal)
### [proposal] Почему делаем
### [design] Архитектурный подход
### [spec] Инварианты
### [decision] Решения
### [note] Заметки
```

## Что НЕ делать

- **НЕ создавать Markdown-файлы** в `.worktrail/tasks/` — SQLite остаётся единственным хранилищем
- **НЕ копировать DDD-ядро** из t-c-k — worktrail остаётся плоским (таблицы + CLI)
- **НЕ добавлять Node.js** — остаёмся на Python + pyyaml
- **НЕ усложнять SKILL.md** — контракт агента остаётся минимальным
- **НЕ интегрировать Mnemopi в код worktrail** — Mnemopi работает отдельно, читает SQLite через `recall`

## План реализации

### Фаза 1: Схема и модели (core)
1. Добавить таблицу `journal` в `_SCHEMA_SQL` (db.py)
2. Добавить поле `kind` в таблицу `tasks`
3. Добавить поле `branch` в таблицу `tasks`
4. Обновить статусный CHECK: 8 статусов вместо 4
5. Добавить модель `JournalEntry` в models.py
6. Обновить модель `Task`: поля `kind`, `branch`, новый статусный набор

### Фаза 2: Repository
1. CRUD для `journal`: `add_journal_entry`, `list_journal_entries`, `get_journal_entry`
2. Обновить `create_task` с учётом `kind` и `branch`
3. Обновить `update_task_status` для 8 статусов
4. Метод `get_subtasks(parent_id)` 
5. Метод `get_initiative_tasks(initiative_id)`
6. Метод `list_tasks` с фильтрами: `--archived`, `--kind`, `--parent`

### Фаза 3: CLI-команды
1. `journal` — add, list, show
2. `status` — set с новыми статусами
3. `archive` — archive, list --archived
4. `explore` — лёгкая задача
5. `initiative` — create, list, show
6. `list` — с фильтрами
7. `report` — улучшить --save для одной задачи

### Фаза 4: Миграция и совместимость
1. Авто-миграция схемы (ALTER TABLE для существующих БД)
2. Мигратор из knowledge/ — добавить journal-импорт из decisions.md, sdd.md
3. Обратная совместимость: старый CLI не ломается

### Фаза 5: SKILL.md и документация
1. Обновить SKILL.md — новые команды
2. README проекта
3. CHANGELOG

## Критические файлы

| Файл | Что меняется |
|---|---|
| `src/worktrail/core/db.py` | `_SCHEMA_SQL`: +journal, +kind, +branch, +8 статусов |
| `src/worktrail/core/models.py` | +JournalEntry, обновление Task |
| `src/worktrail/core/repository.py` | +journal CRUD, обновление статусов, фильтры |
| `src/worktrail/cli/commands.py` | +journal, archive, explore, initiative |
| `src/worktrail/cli/handlers/task.py` | Обновление start/stop под kind/branch/статусы |
| `src/worktrail/cli/handlers/report.py` | Полноценный Markdown-экспорт задачи |
| `SKILL.md` | Новые команды |
| `README.md` | Версия 0.2.0 |

## Верификация

- **Тесты**: unit-тесты на journal CRUD, миграцию схемы, 8 статусов, CLI-команды
- **Интеграция**: сквозной сценарий: `init → start → checkpoint → journal → stop → report --save → archive`
- **Совместимость**: открыть `.worktrail/runtime.db` от v0.1 в v0.2 — данные на месте, схема мигрировала
- **Миграция из knowledge/**: запустить `worktrail migrate --from-knowledge` на singbox-проекте — задачи, journal созданы
