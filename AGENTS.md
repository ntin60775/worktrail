# Repository Guidelines

## Project Overview

**worktrail v2** — git-embedded task knowledge system. CLI-инструмент для агента, не разработчика.
Хранит знания о задаче в git-notes (`refs/notes/worktrail`). Вывод на русском, код на английском.

- **Go 1.21+**, **ноль внешних зависимостей** (stdlib only)
- Один бинарник: `worktrail`
- Лицензия: MIT

## System Boundaries

Worktrail — это **знания о задаче внутри git-репозитория**. Он отвечает на вопросы:
«над чем работаю?», «что сделано?», «почему так?», «работает ли?», «готово ли к ревью?».

### Что ДЕЛАЕТ worktrail (зона ответственности)

| Артефакт | Команда | Суть |
|----------|---------|------|
| Contract | `contract init/show/update` | Что делаем, критерии успеха, как проверять |
| Progress | `progress record/list` | Хроника: что и когда сделано |
| Decision | `decision record/list` | Архитектурный выбор и его обоснование |
| Spec | `spec record/list` | Инварианты модуля/API — переживают задачу |
| Time | `time` | Оценка времени по git-логу (4h gap heuristic) |
| Report | `report` | Markdown-агрегация всех знаний |
| Timesheet | `report --timesheet` | Отчёт для начальника (часы, хронология) |
| Context | `context` | Определение текущей задачи из ветки |
| Install | `install` | Глобальные хуки + бинарь |
| Doctor | `doctor` | Диагностика установки |

### Чего НЕ делает worktrail

| Не делает | Почему | Чья зона |
|-----------|--------|----------|
| Не создаёт структуру каталогов (`src/`, `internal/`, `Config/`) | Это артефакты задачи, не знание о ней | Разработчик / OMP-агент |
| Не инициализирует `go.mod`, `pyproject.toml`, `.golangci.yml` | Пакетные менеджеры и линтеры — внешние инструменты | Разработчик |
| Не управляет зависимостями | `go get`, `pip install`, `npm install` | Пакетный менеджер |
| Не навязывает git-флоу | Git-флоу — соглашение команды | Разработчик |
| Не создаёт OMP/Claude/Codex-агентов | Агенты — среда исполнения, не task knowledge | Разработчик / OMP-конфиг |
| Не хостит, не деплоит, не CI/CD | CI/CD — отдельная система | CI/CD |
| Не заменяет IDE/EDT/Конфигуратор | Линтинг, автодополнение, отладка | Внешние инструменты |
| Не мигрирует данные между проектами | Задача живёт внутри одного репо | Ручной перенос |
| Не заменяет таск-трекер | Нет досок, спринтов, эстимейтов | Таск-трекер |


## Architecture

```
CLI (flag-based, 11 commands)
  │
  ├── internal/gitnotes/  — git-notes CRUD + anchor tags
  ├── internal/context/   — resolve task from branch/notes
  ├── internal/contract/  — contract init/show/update
  ├── internal/executor/  — progress, decision, spec, finalize
  ├── internal/report/    — markdown + timesheet generation
  ├── internal/time/      — git-log time derivation
  ├── internal/list/      — task listing
  ├── internal/install/   — bootstrap: hooks, binary, skill
  ├── internal/archive/   — TCK v1 read-only viewer
  └── internal/doctor/    — health diagnostics

  hooks/                  — 3 git hooks (shell)
  SKILL.md                — agent skill definition
  agents.md.block         — managed block for AGENTS.md
```

Все данные — в `refs/notes/worktrail`. Одна заметка на якорный коммит, агрегатный JSON:
`{ contract, decisions, specs, progress }`.

## Key Directories

| Путь | Назначение |
|------|-----------|
| `cmd/worktrail/main.go` | CLI точка входа |
| `internal/gitnotes/` | git-notes + anchor commit management |
| `internal/context/` | Определение задачи из ветки |
| `internal/contract/` | Контракт задачи |
| `internal/executor/` | Progress, decision, spec, finalize |
| `internal/report/` | Markdown-отчёты + timesheet |
| `internal/time/` | Время по git-логу |
| `internal/list/` | Список задач |
| `internal/archive/` | TCK v1 read-only viewer |
| `internal/install/` | Глобальная установка |
| `internal/doctor/` | Диагностика |
| `hooks/` | post-commit, post-checkout, prepare-commit-msg |
| `references/` | Спецификация, дизайн, JSON-схемы |
| `SKILL.md` | Определение навыка для OMP |
| `agents.md.block` | Блок для вставки в AGENTS.md проекта |

## Development Commands

```bash
go build -o worktrail ./cmd/worktrail    # сборка
go vet ./...                             # статический анализ
go run ./cmd/worktrail <cmd>             # запуск без сборки

./worktrail install                      # глобальный бутстрап
./worktrail doctor                       # диагностика
./worktrail test                         # go test + vet (через адаптер)
```

## Code Conventions

### Go-пакеты

Каждый пакет в своём файле под `internal/`. Экспортируемые функции с заглавной, внутренние — строчной.

### Ошибки

Ошибки **никогда** не глотаются молча. `Read()` возвращает ошибку git, а не пустую заметку.
Каждый `if err != nil` либо пробрасывает, либо логирует осмысленно.

### git-notes

- Read — возвращает ошибку или пустую заметку (её нет, не ошибка)
- Write — принимает `*TaskNote`, возвращает ошибку
- AnchorCommit — READ-ONLY, без сайд-эффектов
- CreateAnchor — создаёт коммит + тег, вызывается только из contract.Init

### Временные метки

`time.Now()` — локальное время системы.
Контракт и решения — `time.Now()`.
### Статус-машина

Разрешённые переходы статусов в `contract.ValidateTransition()`:
`draft → active|cancelled`, `active → blocked|done|cancelled`,

### 1С

Формат выгрузки конфигуратора: `*.bsl`, `*.mdo`, `*.os`, `MainModule.bsl`.
Worktrail не предоставляет специализированных инструментов для 1С — все команды универсальны.


## Testing

```bash
go test ./...                    # все тесты
go test ./internal/gitnotes/     # конкретный пакет
go test -run TestSanitizeTag     # конкретный тест
```

Тесты — `*_test.go` рядом с кодом. Фикстуры — function-scoped. Без моков для git:
реальные подпроцессы в тестах пока не используются (только unit-тесты sanitizeTag).
