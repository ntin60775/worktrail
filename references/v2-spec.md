# worktrail v2 — Спецификация

## 1. Обзор

worktrail v2 — универсальная knowledge-система задач внутри git-репозитория,
построенная вокруг агента как единственного оператора. Не привязана к языку,
стеку или типу проекта.

### Принципы

- **Разработчик не оператор.** Все операции с системой выполняет AI-агент.
  Разработчик только подтверждает или корректирует.
- **Git — единственное хранилище.** Данные в git-notes, а не в SQLite или
  файловой структуре.
- **Универсальное ядро, pluggable адаптеры.** Верификация, аннотации —
  через адаптеры под конкретный стек.
- **Нулевая проектная установка.** Одна глобальная установка навыка.
- **JSON-контракт CLI.** Каждая команда имеет `--json` режим для агента
  и текстовый режим для человека.

### Область действия

Спецификация определяет:
- Схемы данных (раздел 2)
- Протокол git-notes (раздел 3)
- CLI-контракт (раздел 4)
- Интеграцию с агентом (раздел 5)
- Профили проекта (раздел 6)
- Миграцию и архив (раздел 7)

## 2. Схемы данных

Канонические JSON Schema в `references/schemas/`.

| Схема | Файл | Где хранится |
|-------|------|-------------|
| Contract | `contract.json` | git-note `refs/notes/worktrail` |
| Decision | `decision.json` | git-note `refs/notes/worktrail` |
| Spec | `spec.json` | git-note `refs/notes/worktrail` |
| VRR | `vrr.json` | JSONL-лог + git-note (итоговый) |
| Review Package | `review_package.json` | git-note `refs/notes/worktrail` |
| Review Result | `review_result.json` | git-note `refs/notes/worktrail` |

### 2.1 Contract (контракт задачи)

Определяет: что делаем, в каких границах, какие критерии успеха, как проверять.

Обязательные поля: `task_id`, `summary`, `created_at`.

Статусы и переходы:
```
draft → active → review → done
active → blocked → active
любой → cancelled
```

### 2.2 Decision (решение)

Фиксирует архитектурное или проектное решение. Обязательно: `id`, `task_id`,
`title`, `rationale`, `created_at`. Опционально: `file` + `lines` для привязки
к конкретному месту в проекте.

### 2.3 Spec (спек)

Набор инвариантов, привязанных к scope или файлу. Обязательно: `id`, `task_id`,
`scope`, `invariants` (минимум 1), `created_at`.

### 2.4 VRR (Verification Run Record)

Запись одного прогона верификации. Хранится в JSONL-файле в затронутой области
задачи (путь относительно корня репозитория). После `finalize` итоговый VRR
попадает в review_package.

Обязательные поля: `run`, `method`, `timestamp`, `task_id`, `summary`.
Поля `regressions` и `fixed_since_last` — вычисляемые дельты относительно
предыдущего прогона.

### 2.5 Review Package

Собирается при `finalize`. Содержит всё для ревью: контракт, итоговый VRR,
все decisions и specs, границы изменений.

### 2.6 Review Result

Вердикт команды экспертов. `verdict`: `accepted` или `rejected`. Массив
`experts` — заключения по осям. Каждый эксперт: `pass`/`fail`, `blockers`,
`warnings`, `details`.

## 3. Протокол git-notes

### Namespace'ы

| Ref | Содержимое |
|-----|-----------|
| `refs/notes/worktrail` | Все записи: contract, decision, spec, review_package, review_result |
| `refs/notes/worktrail-vrr` | Зарезервировано для будущих VRR (v1 не используется) |

### Формат аннотаций

Каждая git-note — один JSON-объект, соответствующий одной из схем. Тип
определяется по наличию обязательных полей (`task_id` + `summary` → contract,
`rationale` → decision, и т.д.).

Аннотация привязывается к коммиту, на котором она создана. При `finalize`
review_package привязывается к HEAD коммиту задачи.

### Push/fetch

Git-notes не пушатся автоматически. Используется хук `post-push` или агент
явно выполняет:

```bash
git push origin refs/notes/worktrail
```

Агент делает это при `finalize` и после `review run`.

### Разрешение конфликтов

При конфликте notes (два агента записали заметку на один коммит) —
последняя запись перезаписывает предыдущую. Git-notes не поддерживает
слияние; это приемлемо, так как в рамках одной задачи работает один агент.

## 4. CLI-контракт

Все команды поддерживают `--json` для машиночитаемого вывода.
Текстовый вывод — для человека.

Коды выхода:
- `0` — успех
- `1` — ошибка (не в репозитории, нет задачи, неверный ввод)
- `2` — неоднозначность (несколько задач на ветке, требует уточнения)

### 4.1 `worktrail context`

Определяет текущую задачу из git-контекста.

```
worktrail context [--json]
```

**Логика**: читает имя ветки → ищет task_id в формате `task/<id>` или
`task/<id>-<slug>` → читает git-note contract для этого id → возвращает сводку.

**JSON-выход**:
```json
{
  "task_id": "ERP-4521",
  "name": "Интеграция с бухгалтерией",
  "status": "active",
  "branch": "task/ERP-4521-grpc",
  "contract": { ... },
  "has_contract": true
}
```

Если контракт не найден: `has_contract: false`, `contract: null`.

**Текстовый выход**:
```
Задача: ERP-4521 — Интеграция с бухгалтерией
Статус: active
Ветка:  task/ERP-4521-grpc
```

**Ошибки**:
- Не в git-репозитории → exit 1
- Не на task-ветке → exit 1, подсказка
- Несколько задач ссылаются на эту ветку → exit 2

### 4.2 `worktrail contract init`

Создаёт контракт задачи и записывает в git-note.

```
worktrail contract init --task-id <id> --name "..." [--scope "..."] [--json]
```

**Обязательные**: `--task-id`, `--name`.
**Опциональные**: `--scope`.

Контракт создаётся в статусе `draft`. `created_at` = сейчас (UTC).
`branch` = текущая git-ветка.

**JSON-выход**: полный объект Contract.
**Текстовый выход**: «✓ Контракт ERP-4521 создан (draft)»

### 4.3 `worktrail contract show`

Показывает контракт задачи.

```
worktrail contract show [--task-id <id>] [--json]
```

Без `--task-id` — используется текущая задача из контекста.

### 4.4 `worktrail contract update`

Обновляет поля контракта.

```
worktrail contract update --task-id <id> --set <key=value> [--json]
```

Поддерживаемые ключи: `status`, `name`, `summary`, `scope`.
Для добавления success_criteria и verification — отдельные подкоманды.

```
worktrail contract criteria add --task-id <id> --id <cid> --statement "..."
worktrail contract criteria remove --task-id <id> --id <cid>
worktrail contract verify add --task-id <id> --method <m> [--label "..."] [--scope "..."] [--maps-to "C1,C2"]
```

### 4.5 `worktrail decision record`

Записывает решение.

```
worktrail decision record --task-id <id> --id <did> --title "..." --rationale "..." \
    [--file <path>] [--lines <range>] [--alternatives "alt1; alt2 — почему нет"] [--json]
```

### 4.6 `worktrail decision list`

Список решений задачи.

```
worktrail decision list --task-id <id> [--json]
```

### 4.7 `worktrail spec record`

Фиксирует спек.

```
worktrail spec record --task-id <id> --id <sid> --scope "..." --invariants "инв1; инв2; ..." \
    [--file <path>] [--lines <range>] [--json]
```

### 4.8 `worktrail verify run`

Запускает верификацию указанным методом.

```
worktrail verify run --method <method> [--task-id <id>] [--scope "..."] [--json]
```

**Логика**: загружает адаптер для `method` → запускает → формирует VRR →
дописывает строку в JSONL-лог → возвращает VRR.

Путь к JSONL-логу: `<scope>/.worktrail/<task_id>/vrr.jsonl`.

**JSON-выход**: полный объект VRR.

### 4.9 `worktrail verify log`

Просмотр истории прогонов.

```
worktrail verify log --task-id <id> [--last] [--run <n>] [--json]
```

`--last` — только последний прогон. `--run <n>` — конкретный прогон.
Без флагов — сводка по всем прогонам.

### 4.10 `worktrail finalize`

Собирает review_package и финализирует задачу.

```
worktrail finalize [--task-id <id>] [--json]
```

**Что делает**:
1. Читает контракт задачи
2. Собирает все decisions и specs из git-notes
3. Читает последний VRR из JSONL-лога
4. Вычисляет `boundaries` (изменённые файлы через `git diff`)
5. Формирует review_package
6. Записывает в git-note на HEAD коммит
7. Обновляет статус контракта → `review`
8. Вычисляет время через `derive_time()` и добавляет в контракт

### 4.11 `worktrail review run`

Запускает ревью (вызывается агентом-ревьюером).

```
worktrail review run --task-id <id> [--profile <profile>] [--json]
```

**Что делает**:
1. Читает review_package из git-notes
2. Определяет профиль → набор экспертов
3. Для каждого эксперта формирует задание (контракт + релевантные артефакты)
4. Возвращает структуру для параллельного запуска саб-агентов

**Важно**: эта команда НЕ запускает экспертов сама. Она подготавливает
задания. Фактический параллельный запуск делает агент через свой механизм
саб-агентов. Команда возвращает массив экспертных заданий.

**JSON-выход**:
```json
{
  "task_id": "ERP-4521",
  "profile": "generic",
  "experts": [
    {
      "expert": "contract-auditor",
      "prompt": "Проверь контракт задачи ERP-4521...",
      "artifacts": ["contract", "vrr_log"]
    }
    // ...
  ]
}
```

`worktrail review collect` — собирает заключения экспертов в review_result:
```
worktrail review collect --task-id <id> --expert <name> --verdict pass|fail \
    [--blockers-file <path>] [--warnings-file <path>] [--json]
```

### 4.12 `worktrail report`

Генерирует Markdown-отчёт.

```
worktrail report [--task-id <id>] [--save] [--json]
```

Без `--task-id` — отчёт по всем задачам. С `--save` — сохраняет в файл.

### 4.13 `worktrail time`

Вычисляет время по git-логу.

```
worktrail time [--task-id <id>] [--json]
```

**Логика**: `git log --author=<current> --after=<contract.created_at> --before=<now>` →
суммирует время между коммитами. Эвристика: промежуток > 4ч между коммитами
считается границей сессии.

### 4.14 `worktrail archive tck`

Читает старую TCK-структуру `knowledge/tasks/`.

```
worktrail archive tck [--path <path>] [--task-id <id>] [--json]
```

Без `--task-id` — список всех задач из `registry.md`. С `--task-id` —
сводка по задаче из `task.md` + worklog.

### 4.15 `worktrail install`

Устанавливает worktrail глобально.

```
worktrail install [--dry-run] [--json]
```

**Что делает**:
1. Копирует skill.md → `~/.agents/skills/worktrail/SKILL.md`
2. Устанавливает git-хуки: `git config --global core.hooksPath <path-to-hooks>`
3. Прописывает managed-блок в `~/.agents/AGENTS.md` (или другой глобальный файл правил)
4. Проверяет доступность команд

`--dry-run` — показывает что будет сделано, не применяя.

### 4.16 `worktrail doctor`

Диагностика.

```
worktrail doctor [--json]
```

Проверяет: git, hooks, skill, доступность команд, целостность git-notes.

## 5. Интеграция с агентом

### 5.1 SKILL.md

Навык описывает два режима: исполнение и ревью. Полный текст — в корне
репозитория `skill.md`.

### 5.2 Managed-блок для AGENTS.md

```markdown
## worktrail

Во всех git-репозиториях активируй навык `worktrail`.

### Режим исполнения
Когда пользователь просит начать / сделать / продолжить задачу:
1. `worktrail context --json` — определить текущую задачу
2. Если контракта нет: `worktrail contract init ...` — создать
3. В процессе: `worktrail decision record ...` — фиксировать решения
4. После смыслового блока: `worktrail verify run ...` — прогонять проверки
5. По завершении: `worktrail finalize` — собрать review_package

### Режим ревью
Когда пользователь просит провести ревью / проверить задачу:
1. `worktrail review run --task-id <id>` — получить задания экспертов
2. Запустить экспертов параллельно (саб-агенты)
3. `worktrail review collect ...` — собрать вердикты
4. Вывести итоговый отчёт

Режим определяется по первому сообщению пользователя в сессии.
Не смешивать: если сессия началась как ревью — не писать код.
```

Точный текст managed-блока — в файле `agents.md.block`.

### 5.3 Протокол взаимодействия

Агент ↔ worktrail:
- Агент вызывает CLI-команды с `--json`
- Worktrail возвращает JSON на stdout
- Ошибки — на stderr + код выхода
- Агент не парсит текстовый вывод (кроме случаев когда `--json` недоступен)

Worktrail ↔ git:
- Worktrail читает/пишет git-notes напрямую
- Worktrail читает git-лог для `derive_time()`
- Worktrail НЕ делает commit'ы (это делает агент)

## 6. Профили проекта

Профиль определяет **состав экспертной панели при ревью**. Всё остальное —
универсально.

### 6.1 `generic` (по умолчанию)

Для Python, Rust, Go, JavaScript и других языков с тестовыми фреймворками.

Эксперты:
- `contract-auditor` — проверяет выполнение success_criteria по VRR
- `code-auditor` — проверяет инварианты спеков в коде, отсутствие утечек абстракций
- `decisions-auditor` — проверяет полноту rationale и альтернатив
- `boundaries-auditor` — проверяет scope и отсутствие неожиданных изменений
- `vrr-auditor` — проверяет честность VRR (нет подозрительных паттернов)

### 6.2 `1c`

Для проектов на платформе 1С:Предприятие.

Эксперты:
- `contract-auditor` — success_criteria
- `code-auditor` — инварианты в .bsl модулях, обработчики, права
- `metadata-auditor` — реквизиты, формы, роли, подсистемы
- `decisions-auditor` — rationale
- `boundaries-auditor` — scope + проверка метаданных

### 6.3 `diary`

Для личных дневников и нетехнических проектов.

Эксперты:
- `contract-auditor` — success_criteria (обычно manual VRR)
- `content-auditor` — связность, полнота, нет ли противоречий

### 6.4 `research`

Для исследовательских проектов.

Эксперты:
- `contract-auditor` — success_criteria
- `sources-auditor` — источники, ссылки, полнота покрытия темы

## 7. Миграция и архив

### 7.1 Старая TCK-структура (`knowledge/tasks/`)

**Не мигрируется.** Read-only просмотрщик `worktrail archive tck` читает
`task.md` и `registry.md` по запросу.

Если агент обнаруживает `knowledge/` при `resolve_context()`:
- Читает как дополнительный источник исторического контекста
- Все новые данные пишет в git-notes
- Не модифицирует `knowledge/`

### 7.2 Worktrail v1 (`.worktrail/runtime.db`)

**Не мигрируется и не читается.** Слишком разная модель данных (SQLite vs
git-notes). Старые проекты начинают с чистого листа в git-notes.

## 8. Реализация

Язык: **Go**. Один бинарник на выходе.

### Структура проекта

```
worktrail/
├── v1/                         ← legacy Python (read-only)
├── README.md
├── skill.md                    ← контракт навыка
├── agents.md.block             ← managed-блок для AGENTS.md
├── references/
│   ├── v2-design.md            ← дизайн (утверждён)
│   ├── v2-spec.md              ← эта спецификация
│   └── schemas/                ← JSON Schema
│       ├── contract.json
│       ├── decision.json
│       ├── spec.json
│       ├── vrr.json
│       ├── review_package.json
│       └── review_result.json
├── cmd/worktrail/
│   └── main.go
├── internal/
│   ├── contract/               ← работа с контрактом
│   ├── gitnotes/               ← read/write/list git-notes
│   ├── time/                   ← derive_time
│   ├── report/                 ← build_report
│   ├── context/                ← resolve_context
│   ├── verify/                 ← адаптеры верификации
│   │   ├── adapter.go          ← интерфейс
│   │   ├── pytest.go
│   │   ├── manual.go
│   │   ├── shell.go
│   │   └── none.go
│   ├── executor/
│   │   └── workflow.go         ← record_decision, finalize
│   ├── reviewer/
│   │   └── audit.go            ← review run/collect
│   └── archive/
│       └── tck_reader.go
├── hooks/                      ← git-хуки (исходники Go)
│   ├── prepare-commit-msg/
│   ├── post-commit/
│   └── post-checkout/
├── go.mod
├── go.sum
└── Makefile
```

### Фазы реализации

**Фаза 1: Ядро**
- `internal/gitnotes/` — read/write/list
- `internal/context/` — resolve_context
- `internal/contract/` — CRUD контракта
- `internal/time/` — derive_time
- CLI: `context`, `contract init/show/update`, `time`

**Фаза 2: Верификация**
- `internal/verify/` — adapter interface + pytest, manual, shell, none
- CLI: `verify run`, `verify log`
- `internal/executor/workflow.go` — VRR-цикл, finalize
- CLI: `finalize`

**Фаза 3: Ревью**
- `internal/reviewer/audit.go` — review run/collect
- CLI: `review run`, `review collect`
- Профили: generic, 1c, diary, research

**Фаза 4: Инфраструктура**
- `internal/report/` — Markdown-отчёты
- `internal/archive/tck_reader.go` — просмотрщик TCK
- CLI: `report`, `archive tck`, `install`, `doctor`
- Git-хуки
- `skill.md`, `agents.md.block`

## 9. Что осознанно исключено

- **SQLite-хранилище** — заменено на git-notes
- **Файловая структура `knowledge/`** — заменена на git-notes
- **Ручной трекинг времени (start/stop)** — заменён на `derive_time` из git-лога
- **Собственный формат ID задач** — любые внешние ID
- **Проектная установка** — только глобальная
- **Inline-маркеры в коде** — заменены на git-notes с привязкой file:lines
