# Repository Guidelines

## Project Overview

**worktrail** — CLI-инструмент учёта рабочего времени и управления знаниями по задачам внутри git-репозитория. Хранит всё в локальном SQLite (`.worktrail/runtime.db`), не требует облачных сервисов. Вывод на русском, код на английском.

- Python **3.11+**, единственная продуктовая зависимость: `pyyaml>=6.0`
- Сборка: `setuptools` (src-layout), точка входа: `worktrail = worktrail.cli.main:main`
- Лицензия: MIT

## Architecture & Data Flow

```
CLI (argparse + @command registry)
  ├── handlers/   — обработчики команд (task, journal, explore, initiative, report, …)
  ├── commands.py — реестр команд, общие хелперы
  ├── main.py     — точка входа, сборка парсера, диспетчеризация
  └── doctor.py   — диагностика (6 проверок)

Core (чистые данные, без CLI)
  ├── models.py   — dataclasses: Task, Session, Checkpoint, JournalEntry, Config
  ├── db.py       — SQLite schema (5 таблиц), get_connection(), init_db(), migrate_schema()
  ├── repository.py — CRUD через raw SQL + sqlite3.Row, возвращает dataclass-экземпляры
  └── config.py   — YAML-конфиг (.worktrail/config.yaml) с JSON-fallback

Domain modules
  ├── tracker/    — TrackerEngine (жизненный цикл сессии), IdleMonitor (авто-пауза по mtime)
  ├── reporter/   — ReportGenerator → ReportItem/Block → render_terminal() / render_markdown()
  ├── git_bridge/ — run_git() subprocess, извлечение task-id из ветки, git-хуки
  └── migrator/   — парсинг v1 task.md → импорт в SQLite (9-шаговый пайплайн)
```

**Поток данных**: CLI handler → TrackerEngine / ReportGenerator / Migrator → Repository (raw SQL) → SQLite. Все временные метки — ISO8601 UTC-строки. Никакого ORM, никакого кеширования (поиск project root — честный walk по директориям на каждый вызов).

**Принципы**:
- Локальный SQLite, zero external services
- Plain SQLite + YAML — никакого lock-in
- Git-native: живёт внутри репозитория, хакает хуки
- Только одна активная сессия в каждый момент
- Knowledge-first: journal (proposal/design/spec/decision/note/artifact) наравне с трекингом времени
- Русский CLI-вывод, английский код и docstrings

## Key Directories

| Путь | Назначение |
|------|-----------|
| `src/worktrail/` | Пакет проекта |
| `src/worktrail/core/` | Модели данных, БД, CRUD, конфиг — фундамент |
| `src/worktrail/cli/` | CLI-слой: парсер, реестр команд, handlers, диагностика |
| `src/worktrail/cli/handlers/` | По одному модулю на группу команд: `task.py`, `journal.py`, `explore.py`, `initiative.py`, `archive.py`, `report.py`, `migrate.py`, `system.py` |
| `src/worktrail/tracker/` | Движок сессии (start/stop/pause/resume) + idle-монитор |
| `src/worktrail/reporter/` | Генерация отчётов (терминал / Markdown) |
| `src/worktrail/git_bridge/` | Git-операции и управление хуками |
| `src/worktrail/migrator/` | Миграция из task-centric-knowledge v1 |
| `tests/` | Тесты (pytest), по файлу на модуль |
| `.worktrail/` | Runtime-данные (runtime.db, config.yaml, reports/) — НЕ коммитить |

## Development Commands

```bash
# Установка в dev-режиме
pip install -e ".[dev]"

# Запуск тестов
pytest                          # все тесты
pytest tests/test_core.py       # конкретный файл
pytest -k "test_create_task"    # по имени теста
pytest --cov=worktrail          # с покрытием

# Запуск CLI (после установки)
worktrail --help
worktrail init
worktrail start TEST-001 --name "Test task"

# Без установки
PYTHONPATH=src python -m worktrail --help
```

**Важно**: `pyproject.toml` настраивает `pythonpath = ["src"]` для pytest — тесты импортируют пакет напрямую.

## Code Conventions & Common Patterns

### Dataclasses как модели

Все доменные объекты — `@dataclass` с `field(default_factory=...)` для временных меток. Поля опциональные через `Optional[X] = None`. Никаких Python-перечислений — валидация значений через SQLite `CHECK` constraints.

```python
@dataclass
class Task:
    id: str
    name: str
    status: str = "draft"
    kind: str = "task"
    branch: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_id: Optional[str] = None
```

### Временные метки

**Всегда** ISO8601 UTC-строки: `datetime.now(timezone.utc).isoformat()`. Хранятся в SQLite как `TEXT`. Статический хелпер `Repository._now()` для консистентности.

### Raw SQL, без ORM

Repository пишет сырой SQL через `sqlite3.Row`-фабрику, возвращает экземпляры dataclass. Коннекты через context manager `get_connection()` из `db.py`. Каждая операция записи — auto-commit (отдельная транзакция).

```python
repo = Repository()  # авто-поиск runtime.db
with repo.conn() as conn:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
```

### Plugin-based CLI

Команды регистрируются декораторами `@command` / `@arg` из `worktrail.cli.commands`. Все handlers лежат в `cli/handlers/`, импортируются через `__init__.py` — сам факт импорта триггерит регистрацию. `main.py` строит argparse-парсер динамически из реестра.

```python
# cli/handlers/task.py
from worktrail.cli.commands import command, arg

@command("start", help="Начать учёт времени для задачи")
@arg("task_id", help="ID задачи")
@arg("--name", help="Название задачи")
def handle_start(args) -> int:
    ...
    return 0
```

Каждый handler возвращает `int` (код выхода): `0` — успех, `1` — ошибка. `main()` ловит `KeyboardInterrupt` → 130, `Exception` → 1.

### Обработка ошибок

- CLI: handler возвращает код выхода; `main()` ловит исключения → печатает в stderr и выходит с кодом 1
- Core/Repository: исключения пробрасываются наверх (нет подавления)
- TrackerEngine: возвращает `None` для no-op операций (например, `stop()` когда нет активной сессии)
- Migrator: собирает ошибки в отчёт, не прерывается на первом сбое
- Git bridge: `run_git()` возвращает `subprocess.CompletedProcess`, вызывающий код проверяет `returncode`

### Git-операции

Только через `subprocess.run(["git", "-C", repo_root, ...], capture_output=True, text=True)`. Никаких GitPython/libgit2. Ветка извлекается через `git rev-parse --abbrev-ref HEAD`, task-id — regex `^(?:task|du)/(\S+?)(?:-|$)` из имени ветки.

### Конфигурация

Два пути хранения:
1. **YAML-файл** (`.worktrail/config.yaml`) — для runtime-настроек: `idle_timeout: 900`, `git_hooks_enabled: true`. JSON-fallback если PyYAML недоступен.
2. **SQLite-таблица `config`** — key/value для per-project настроек (используется мигратором и т.п.)

### Локализация

- Весь пользовательский вывод — **на русском** (print, help-тексты)
- Код, docstrings, комментарии, имена переменных — **на английском**
- Хелперы: `fmt_seconds()` (русский формат времени: «1ч 15м 30с»), `pluralize()` (русское склонение), `_translate_status()` (статусы по-русски)

## Important Files

| Файл | Роль |
|------|------|
| `pyproject.toml` | Сборка, зависимости, точка входа, конфиг pytest |
| `src/worktrail/__init__.py` | `__version__ = "0.1.0"` |
| `src/worktrail/__main__.py` | `python -m worktrail` |
| `src/worktrail/cli/main.py` | Точка входа CLI (`worktrail`), сборка парсера |
| `src/worktrail/cli/commands.py` | Реестр команд, декораторы, общие хелперы |
| `src/worktrail/core/models.py` | 5 dataclass-моделей |
| `src/worktrail/core/db.py` | SQLite schema (5 таблиц), connection, миграции |
| `src/worktrail/core/repository.py` | CRUD для всех сущностей (~660 строк) |
| `src/worktrail/core/config.py` | YAML/JSON конфиг |
| `src/worktrail/tracker/engine.py` | TrackerEngine — жизненный цикл сессии |
| `src/worktrail/reporter/__init__.py` | ReportGenerator — точка входа для отчётов |
| `src/worktrail/git_bridge/parser.py` | Git-обёртки, парсинг веток |
| `src/worktrail/git_bridge/hooks.py` | Установка/удаление git-хуков |
| `src/worktrail/migrator/migrator.py` | Оркестратор миграции v1→v2 |
| `.worktrail/config.yaml` | Runtime-конфиг (не коммитится) |
| `.worktrail/runtime.db` | Основная БД (не коммитится) |

## Database Schema

5 таблиц в `.worktrail/runtime.db`:

```sql
tasks (id TEXT PK, name, status CHECK(8), kind CHECK(task|exploration|initiative),
       branch, created_at, updated_at, parent_id REFERENCES tasks)

sessions (id INTEGER PK, task_id REFERENCES tasks, started_at, ended_at,
          status CHECK(active|paused|ended), total_seconds)

checkpoints (id INTEGER PK, session_id REFERENCES sessions, message, timestamp,
             source CHECK(manual|hook|auto), commit_hash)

journal (id INTEGER PK, task_id REFERENCES tasks,
         kind CHECK(proposal|design|spec|decision|note|artifact),
         title, body, created_at)

config (key TEXT PK, value)
```

Миграции схемы — через `migrate_schema()` в `db.py`: проверяет наличие колонок (`kind`, `branch`, `parent_id`), добавляет `ALTER TABLE ADD COLUMN` при необходимости (forward-compat для проектов с v0.1).

## Runtime/Tooling Preferences

- **Рантайм**: Python 3.11+ (используются `from __future__ import annotations`, `X | None`-синтаксис)
- **Сборка**: setuptools (не poetry/hatch/flit), src-layout
- **Пакетный менеджер**: pip (нет lock-файла)
- **Зависимости**: минимум — `pyyaml` (production), `pytest` + `pytest-cov` (dev)
- **НЕ использовать**: ORM, Node.js, Markdown-файлы как хранилище, внешние БД/сервисы
- **Философия**: boring technology, no lock-in, git-native, single binary (`worktrail`)

## Testing & QA

### Структура

6 независимых тестовых файлов, каждый покрывает одну подсистему:

| Файл | Строк | Что тестирует |
|------|-------|--------------|
| `tests/test_core.py` | 721 | db, models, repository, config |
| `tests/test_cli.py` | 625 | commands registry, parser, main dispatch |
| `tests/test_tracker.py` | 388 | TrackerEngine сессии, IdleMonitor |
| `tests/test_reporter.py` | 532 | formatter (группировка чекпоинтов), writer (рендеринг) |
| `tests/test_git_bridge.py` | 426 | git parser, hooks install/remove/verify |
| `tests/test_migrator.py` | 795 | v1 parser, migrator pipeline, status normalization |

Всего ~180 тестов.

### Подход

- **Фреймворк**: чистый pytest (без unittest.TestCase)
- **Фикстуры**: function-scoped, определяются в файлах тестов (нет `conftest.py`)
- **БД**: реальный SQLite in-memory / tmp файл для core/tracker/reporter (без моков)
- **Git**: реальные git-подпроцессы во временных репозиториях для `git_bridge`
- **Мигратор**: моки git-операций, реальный парсинг v1-файлов из фикстур
- **freezegun**: используется в `test_tracker.py`, но **не объявлен** в dev-зависимостях — требует ручной установки

### Запуск

```bash
pytest                              # все тесты
pytest tests/test_core.py           # один модуль
pytest -k "test_start"              # фильтр по имени
pytest --cov=worktrail --cov-report=term-missing
```

### Конвенции

- Имена тестов: `test_<действие>[_<условие>]`
- Тесты сгруппированы в классы по тестируемой функции/модулю (`class TestCreateTask`)
- Параметризация через `@pytest.mark.parametrize` для edge-cases (особенно в migrator — 12 случаев статусов)
- Временные директории: микс `tmp_path` (pytest) и `tempfile.TemporaryDirectory` — предпочтительнее `tmp_path`

### Не покрыто

- SQLite error paths (блокировки, constraint violations)
- Конкурентные сессии
- detached HEAD в git
- Большие объёмы данных (performance)
- `--help` вывод для подкоманд
