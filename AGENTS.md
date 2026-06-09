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
| VRR | `verify run/log` | Результаты прогонов тестов/проверок |
| Review Package | `finalize` | Сборка всех знаний для ревью |
| Review Result | `review run/result` | Вердикт экспертов |
| Time | `time` | Оценка времени по git-логу (4h gap heuristic) |
| Report | `report` | Markdown-агрегация всех знаний |
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

### Про домены

Домен — знание о том, **как верифицировать** и **что проверять при ревью** в конкретной экосистеме.
Описывается встроенным YAML-конфигом. Worktrail поставляется с доменами: `code`, `1c`, `research`.

Домен **не** создаёт код, структуру каталогов или конфиги экосистемы.

## Architecture

```
CLI (flag-based, 21 command)
  │
  ├── internal/gitnotes/  — git-notes CRUD + anchor tags
  ├── internal/context/   — resolve task from branch/notes
  ├── internal/contract/  — contract init/show/update
  ├── internal/executor/  — progress, decision, spec, finalize
  ├── internal/verify/    — adapter interface + runners
  ├── internal/reviewer/  — review run/result
  ├── internal/domain/    — domain detection, adapters, experts
  ├── internal/report/    — markdown generation
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
`{ contract, decisions, specs, progress, review_package, review_result }`.

Якорный коммит — уникальный пустой коммит на задачу. Тег `worktrail/<sanitized-id>` указывает на него.

## Key Directories

| Путь | Назначение |
|------|-----------|
| `cmd/worktrail/main.go` | CLI точка входа |
| `internal/gitnotes/` | git-notes + anchor commit management |
| `internal/contract/` | Контракт задачи |
| `internal/executor/` | Progress, decision, spec, finalize |
| `internal/verify/` | Adapter interface + pytest/go_test/shell/manual/none |
| `internal/reviewer/` | Review run/result + профили экспертов |
| `internal/domain/` | Доменная модель: detect, adapters, experts |
| `internal/report/` | Markdown-отчёты |
| `internal/time/` | Время по git-логу |
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

`time.Now()` — локальное время системы. Верификация использует `time.Now()` для VRR.
Контракт и решения — `time.Now()`.

### Статус-машина

Разрешённые переходы статусов в `contract.ValidateTransition()`:
`draft → active|cancelled`, `active → blocked|review|done|cancelled`,
`blocked → active|cancelled`, `review → done|active|cancelled`,
`done → active`, `cancelled → draft`.

### 1С

Домен `1c` ориентирован на **формат выгрузки конфигуратора**, не EDT.
Файлы: `*.bsl`, `*.mdo`, `*.os`, `MainModule.bsl`.
Адаптер: `1c_syntax_check` (синтаксис-контроль).
Эксперты ревью: `1c-code-auditor` (BSL-паттерны), `1c-metadata-auditor` (ссылочная целостность).

## Testing

```bash
go test ./...                    # все тесты
go test ./internal/gitnotes/     # конкретный пакет
go test -run TestSanitizeTag     # конкретный тест
```

Тесты — `*_test.go` рядом с кодом. Фикстуры — function-scoped. Без моков для git:
реальные подпроцессы в тестах пока не используются (только unit-тесты sanitizeTag).
