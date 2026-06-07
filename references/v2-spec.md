# worktrail v2 — Спецификация

## 1. Обзор

worktrail v2 — универсальная knowledge-система задач внутри git-репозитория,
построенная вокруг агента как единственного оператора. Не привязана к языку,
стеку или типу проекта.

### Принципы

- **Разработчик не оператор.** Все операции с системой выполняет AI-агент.
  Разработчик только подтверждает или корректирует.
- **Git — каноническое хранилище структурных знаний.** Контракты, решения,
  спеки, результаты ревью — в git-notes. Оперативные VRR-логи — JSONL
  на диске с переносом итогового VRR в git-notes при finalize.
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
| Progress | `progress.json` | git-note `refs/notes/worktrail` |
| Decision | `decision.json` | git-note `refs/notes/worktrail` |
| Spec | `spec.json` | git-note `refs/notes/worktrail` |
| VRR | `vrr.json` | JSONL-лог (оперативный) + git-note (итоговый) |
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

### 2.2 Progress (запись о ходе работ)

Лёгкая хронологическая запись. Не решение (нет rationale), не спек
(нет инвариантов), не VRR (не прогон тестов). Просто «что произошло».

Обязательные поля: `task_id`, `timestamp`, `summary`.
Опционально: `commit` — хеш коммита, к которому относится запись.

Создаётся автоматически хуком `post-commit` из commit-сообщения.
Агент может создать вручную для не-коммит-активности
(«2 часа читал документацию API»).

### 2.3 Decision (решение)

Фиксирует архитектурное или проектное решение. Обязательно: `id`, `task_id`,
`title`, `rationale`, `created_at`. Опционально: `file` + `lines` для привязки
к конкретному месту в проекте.

Отличие от Progress: Decision имеет rationale и alternatives. Это осознанный
выбор, а не хроника.

### 2.4 Spec (спек)

Набор инвариантов, привязанных к scope или файлу. Обязательно: `id`, `task_id`,
`scope`, `invariants` (минимум 1), `created_at`.

Отличие от success_criteria в Contract:
- Criteria — «ЧТО должно быть истинно для завершения задачи». Живут в контракте,
  умирают с задачей.
- Spec — «инварианты КОНКРЕТНОГО модуля/API». Может пережить задачу и остаться
  в git-notes как документация модуля.

### 2.5 VRR (Verification Run Record)

Запись одного прогона верификации.

**Оперативное хранение**: JSONL-файл в `<scope>/.worktrail/<task_id>/vrr.jsonl`.
Каждый прогон — одна строка JSON.

**Каноническое хранение**: при `finalize` итоговый VRR копируется в git-note
как часть review_package. JSONL-лог может быть удалён после завершения задачи.

Обязательные поля: `run`, `method`, `timestamp`, `task_id`, `summary`.
Поля `regressions` и `fixed_since_last` — вычисляемые дельты относительно
предыдущего прогона.

### 2.6 Review Package

Собирается при `finalize`. Содержит всё для ревью: контракт, итоговый VRR,
все decisions, specs, progress-записи, границы изменений.

### 2.7 Review Result

Вердикт команды экспертов. `verdict`: `accepted` или `rejected`. Массив
`experts` — заключения по осям. Каждый эксперт: `pass`/`fail`, `blockers`,
`warnings`, `details`.

## 3. Протокол git-notes

### Namespace'ы

| Ref | Содержимое |
|-----|-----------|
| `refs/notes/worktrail` | Все записи: contract, progress, decision, spec, review_package, review_result |

### Якорный коммит

Каждая задача имеет **один якорный коммит** — это коммит, на который
вешаются все git-notes задачи. Якорь вычисляется так:

1. Если задача на ветке `task/<id>*` — якорь = первый коммит этой ветки
   (точка ветвления от base)
2. Если задача без ветки (main, research) — якорь = коммит, на котором
   создан контракт
3. Если контракт ещё не создан — якорь = HEAD

Все notes для задачи (contract, decisions, specs, progress, review_package,
review_result) висят на этом одном коммите. Это решает проблему поиска:
`git notes --ref=worktrail show <anchor>` возвращает все записи задачи.

**Обновление notes**: каждая новая запись перезаписывает note на якорном
коммите, добавляя новую запись к уже существующим. Формат хранения —
JSON-объект с ключами-типами, содержащими массивы записей:

```json
{
  "contract": { ... },
  "decisions": [ { ... }, { ... } ],
  "specs": [ { ... } ],
  "progress": [ { ... }, { ... } ],
  "review_package": { ... },
  "review_result": { ... }
}
```

### Push/fetch

Git-notes не пушатся автоматически. Агент явно выполняет:

```bash
git push origin refs/notes/worktrail
```

Агент делает это при `finalize` и после `review result`.

### Разрешение конфликтов

В рамках одной задачи работает один агент — конфликтов notes не возникает.
При параллельной работе над разными задачами notes висят на разных коммитах —
конфликтов нет.

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

**Логика определения задачи** (в порядке приоритета):
1. Ветка соответствует `task/<id>*` → извлечь id из имени
2. Ветка соответствует `feature/<id>*`, `bugfix/<id>*`, `jira/<id>*` → извлечь id
3. Найти git-note с `branch = текущая_ветка` на любом якорном коммите
4. Если ветка `main`/`master` → найти последнюю активную задачу (status != done/cancelled)
5. Ничего не найдено → `has_task: false`, агент предлагает создать

**JSON-выход**:
```json
{
  "task_id": "ERP-4521",
  "name": "Интеграция с бухгалтерией",
  "status": "active",
  "branch": "task/ERP-4521-grpc",
  "anchor_commit": "abc1234",
  "contract": { ... },
  "has_contract": true,
  "has_task": true
}
```

### 4.2 `worktrail list`

Список задач в репозитории.

```
worktrail list [--status <s>] [--json]
```

Без `--status` — все задачи. С `--status active` — только активные.
С `--status review` — ожидающие ревью.

**Логика**: сканирует все git-notes в `refs/notes/worktrail`, извлекает
contract из каждого якорного коммита, фильтрует по статусу.

**JSON-выход**: массив сводок `[{task_id, name, status, branch, anchor_commit}]`.

### 4.3 `worktrail contract init`

Создаёт контракт задачи.

```
worktrail contract init --task-id <id> --name "..." [--scope "..."] [--json]
```

Создаёт якорный коммит (если ещё нет), записывает contract в git-note.
Статус: `draft`. `created_at` = сейчас (UTC). `branch` = текущая ветка.

### 4.4 `worktrail contract show`

Показывает контракт задачи.

```
worktrail contract show [--task-id <id>] [--json]
```

Без `--task-id` — текущая задача из контекста.

### 4.5 `worktrail contract update`

Обновляет контракт.

```
worktrail contract update --task-id <id> [--set <key=value>] \
    [--criteria-file <path>] [--verify-file <path>] [--json]
```

Поддерживаемые ключи `--set`: `status`, `name`, `summary`, `scope`.

`--criteria-file <path>` — путь к JSON-файлу с массивом success_criteria.
Заменяет весь массив criteria в контракте.

`--verify-file <path>` — путь к JSON-файлу с массивом verification methods.
Заменяет весь массив verification в контракте.

### 4.6 `worktrail decision record`

Записывает решение.

```
worktrail decision record --task-id <id> --id <did> --title "..." --rationale "..." \
    [--file <path>] [--lines <range>] [--alternatives "alt1; alt2 — почему нет"] [--json]
```

### 4.7 `worktrail decision list`

Список решений задачи.

```
worktrail decision list --task-id <id> [--json]
```

### 4.8 `worktrail spec record`

Фиксирует спек.

```
worktrail spec record --task-id <id> --id <sid> --scope "..." \
    --invariants "инв1; инв2; ..." [--file <path>] [--lines <range>] [--json]
```

### 4.9 `worktrail progress record`

Записывает отметку о ходе работ.

```
worktrail progress record --task-id <id> --summary "..." [--commit <hash>] [--json]
```

Без `--commit` — привязывается к HEAD.

### 4.10 `worktrail progress list`

Хронология хода работ по задаче.

```
worktrail progress list --task-id <id> [--last <n>] [--json]
```

### 4.11 `worktrail verify run`

Запускает верификацию.

```
worktrail verify run --method <method> [--task-id <id>] [--scope "..."] [--json]
```

Загружает адаптер → запускает → формирует VRR → дописывает строку в JSONL-лог.

### 4.12 `worktrail verify log`

История прогонов.

```
worktrail verify log --task-id <id> [--last] [--run <n>] [--json]
```

### 4.13 `worktrail finalize`

Собирает review_package и финализирует задачу.

```
worktrail finalize [--task-id <id>] [--json]
```

**Что делает**:
1. Читает контракт
2. Собирает все decisions, specs, progress из git-notes задачи
3. Читает последний VRR из JSONL-лога
4. Вычисляет `boundaries` (`git diff` от якорного коммита до HEAD)
5. Формирует review_package → git-note
6. Статус контракта → `review`
7. `derive_time()` → добавляет время в контракт

### 4.14 `worktrail review run`

Подготавливает задания для экспертов.

```
worktrail review run --task-id <id> [--profile <profile>] [--json]
```

Читает review_package → определяет профиль → возвращает массив заданий
для параллельного запуска саб-агентов. **Не запускает экспертов сама.**

### 4.15 `worktrail review result`

Сохраняет вердикт ревью.

```
worktrail review result --task-id <id> --verdict <accepted|rejected> \
    --file <result.json> [--json]
```

Принимает готовый JSON в формате review_result (собранный агентом из
заключений экспертов), валидирует по схеме, записывает в git-note.

### 4.16 `worktrail time`

Вычисляет время по git-логу.

```
worktrail time [--task-id <id>] [--json]
```

Логика: `git log --after=<contract.created_at> --before=<now>` →
суммирует время между коммитами. Промежуток > 4ч = граница сессии.

### 4.17 `worktrail report`

Генерирует Markdown-отчёт.

```
worktrail report [--task-id <id>] [--save] [--json]
```

Без `--task-id` — отчёт по всем задачам. С `--save` — в файл.

### 4.18 `worktrail archive tck`

Читает старую TCK-структуру `knowledge/tasks/`.

```
worktrail archive tck [--path <path>] [--task-id <id>] [--json]
```

### 4.19 `worktrail install`

Глобальная установка.

```
worktrail install [--dry-run] [--json]
```

### 4.20 `worktrail doctor`

Диагностика.

```
worktrail doctor [--json]
```

## 5. Интеграция с агентом

### 5.1 SKILL.md

Навык описывает два режима: исполнение и ревью. Полный текст — в `skill.md`.

### 5.2 Managed-блок для AGENTS.md

```markdown
## worktrail

Во всех git-репозиториях активируй навык `worktrail`.

### Режим исполнения
Когда пользователь просит начать / сделать / продолжить задачу:
1. `worktrail context --json` — определить текущую задачу
2. Если контракта нет: `worktrail contract init ...` — создать
3. В процессе: `worktrail progress record ...` — фиксировать ход
4. Для важных выборов: `worktrail decision record ...`
5. После смыслового блока: `worktrail verify run ...` — прогонять проверки
6. По завершении: `worktrail finalize` — собрать review_package

### Режим ревью
Когда пользователь просит провести ревью / проверить задачу:
1. `worktrail review run --task-id <id>` — получить задания экспертов
2. Запустить экспертов параллельно (саб-агенты)
3. Собрать заключения в review_result JSON
4. `worktrail review result --task-id <id> --verdict <...> --file <result.json>`
5. Вывести итоговый отчёт

Режим определяется по первому сообщению пользователя в сессии.
Не смешивать: если сессия началась как ревью — не писать код.
```

Точный текст managed-блока — в файле `agents.md.block`.

### 5.3 Протокол взаимодействия

Агент ↔ worktrail:
- Агент вызывает CLI-команды с `--json`
- Worktrail возвращает JSON на stdout
- Ошибки — на stderr + код выхода

Worktrail ↔ git:
- Worktrail читает/пишет git-notes напрямую
- Worktrail читает git-лог для `derive_time()`
- Worktrail НЕ делает commit'ы (это делает агент)

## 6. Профили проекта

Профиль определяет **состав экспертной панели при ревью**. Всё остальное —
универсально.

### 6.1 `code` (по умолчанию)

Для проектов разработки с тестовыми фреймворками: Python, Rust, Go,
JavaScript, Java, C# и т.д.

Эксперты:
- `contract-auditor` — выполнение success_criteria по VRR
- `code-auditor` — инварианты спеков в коде, утечки абстракций
- `decisions-auditor` — полнота rationale и альтернатив
- `boundaries-auditor` — scope и неожиданные изменения
- `vrr-auditor` — честность VRR

### 6.2 `1c`

Для проектов на платформе 1С:Предприятие.

Эксперты:
- `contract-auditor` — success_criteria
- `code-auditor` — инварианты в .bsl модулях, обработчики, права
- `metadata-auditor` — реквизиты, формы, роли, подсистемы
- `decisions-auditor` — rationale
- `boundaries-auditor` — scope + метаданные

### 6.3 `research`

Для исследовательских проектов, статей, обзоров.

Эксперты:
- `contract-auditor` — success_criteria
- `sources-auditor` — источники, ссылки, полнота покрытия

### 6.4 `minimal`

Универсальный fallback. Используется когда ни один профиль не подходит,
или когда проект не требует глубокого ревью (личные заметки, дневник,
черновики).

Эксперты:
- `contract-auditor` — только проверка success_criteria

### 6.5 Выбор профиля

1. Агент определяет профиль по типу проекта (наличие кода, тестового
   фреймворка, 1С-метаданных)
2. Если профиль не удалось определить однозначно — используется `minimal`
3. Агент может дополнить structured review ручной проверкой по другим осям
4. Разработчик может явно указать профиль: «Проведи ревью по профилю code»

## 7. Миграция и архив

### 7.1 Старая TCK-структура (`knowledge/tasks/`)

**Не мигрируется.** Read-only просмотрщик `worktrail archive tck` читает
`task.md` и `registry.md` по запросу.

Если агент обнаруживает `knowledge/` при `resolve_context()`:
- Читает как дополнительный источник исторического контекста
- Все новые данные пишет в git-notes
- Не модифицирует `knowledge/`

### 7.2 Worktrail v1 (`.worktrail/runtime.db`)

**Не мигрируется и не читается.** Слишком разная модель данных.

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
│       ├── progress.json
│       ├── decision.json
│       ├── spec.json
│       ├── vrr.json
│       ├── review_package.json
│       └── review_result.json
├── cmd/worktrail/
│   └── main.go
├── internal/
│   ├── contract/               ← работа с контрактом
│   ├── gitnotes/               ← read/write/list + якорный коммит
│   ├── time/                   ← derive_time
│   ├── report/                 ← build_report
│   ├── context/                ← resolve_context (умный)
│   ├── list/                   ← list tasks
│   ├── verify/                 ← адаптеры верификации
│   │   ├── adapter.go          ← интерфейс
│   │   ├── pytest.go
│   │   ├── manual.go
│   │   ├── shell.go
│   │   └── none.go
│   ├── executor/
│   │   └── workflow.go         ← progress, decision, spec, finalize
│   ├── reviewer/
│   │   └── audit.go            ← review run/result
│   └── archive/
│       └── tck_reader.go
├── hooks/                      ← git-хуки (исходники Go)
│   ├── prepare-commit-msg/
│   ├── post-commit/            ← auto progress record
│   └── post-checkout/
├── go.mod
├── go.sum
└── Makefile
```

### Фазы реализации

**Фаза 1: Ядро**
- `internal/gitnotes/` — read/write/list, якорный коммит
- `internal/context/` — resolve_context (ветка → задача)
- `internal/list/` — list tasks
- `internal/contract/` — CRUD контракта
- `internal/time/` — derive_time
- CLI: `context`, `list`, `contract init/show/update`, `time`

**Фаза 2: Верификация и ход работ**
- `internal/verify/` — adapter interface + pytest, manual, shell, none
- CLI: `verify run`, `verify log`
- `internal/executor/workflow.go` — progress, decision, spec, finalize
- CLI: `progress record/list`, `decision record/list`, `spec record`, `finalize`

**Фаза 3: Ревью**
- `internal/reviewer/audit.go` — review run/result
- CLI: `review run`, `review result`
- Профили: code, 1c, research, minimal

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
