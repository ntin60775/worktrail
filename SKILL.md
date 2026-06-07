---
name: worktrail
description: >
  v2 — универсальная knowledge-система задач в git-репозитории.
  Два режима: исполнение (context → contract → progress → decisions → verify → finalize)
  и ревью (review run → параллельные эксперты → review result).
  Данные в git-notes, установка одной командой, разработчик не оператор.
  Используй, когда в репозитории есть refs/notes/worktrail или когда
  пользователь просит начать/закончить задачу, записать прогресс,
  принять решение, зафиксировать спек, запустить верификацию или ревью.
---

# worktrail v2

## Когда использовать

- В репозитории настроен worktrail (есть `refs/notes/worktrail` или `git tag -l 'worktrail/*'` непусто)
- Пользователь просит: «начни задачу», «запиши что сделал», «сколько времени», «отчёт»
- Пользователь просит: «запиши решение», «зафиксируй спек», «проведи верификацию»
- Пользователь просит: «проведи ревью», «проверь задачу»
- Пользователь просит установить worktrail: «настрой учёт задач»

## Установка

Одна глобальная установка:

```bash
worktrail install
```

Устанавливает git-хуки глобально (`git config --global core.hooksPath`),
копирует SKILL.md и agents.md.block. После установки worktrail доступен
во всех репозиториях. Проверить: `worktrail doctor`.

## Режимы работы

worktrail v2 работает в двух режимах. Режим определяется по первому сообщению
пользователя в сессии. **Не смешивать:** если сессия началась как ревью —
не писать код.

### Режим исполнения

Разработчик говорит ЧТО делать, агент делает и фиксирует знания.
Агент — единственный оператор worktrail. Разработник не вызывает CLI вручную.

**Поток:** context → contract → progress → decisions → specs → verify → finalize

1. **`worktrail context --json`** — определить текущую задачу
   - Извлекает `task_id` из ветки (`task/<id>*`, `feature/<id>*`, `jira/<id>*`)
   - На `main`/`master` — ищет последнюю активную задачу
   - Если `has_task: false` — предложить пользователю создать
   - Если несколько задач — код выхода 2, уточнить у пользователя

2. **`worktrail contract init --task-id <id> --name "..."`** — создать контракт
   - Если контракт существует — `contract update` для изменений
   - Статус по умолчанию: `draft`
   - Контракт содержит: `task_id`, `summary`, `success_criteria`, `verification`

3. **`worktrail progress record --task-id <id> --summary "..."`** — фиксировать ход
   - Git-хук `post-commit` делает это автоматически с сообщением коммита
   - Для не-коммит-активности (чтение документации, анализ) — агент создаёт вручную
   - Без `--commit` привязывается к HEAD

4. **`worktrail decision record --task-id <id> --id <did> --title "..." --rationale "..."`**
   - Каждое ключевое архитектурное решение — одна запись
   - Обязательно: rationale (почему), alternatives (что рассматривали и почему нет)
   - Опционально: `--file <path> --lines <range>` — привязка к коду
   - Decisions иммутабельны. При ошибке создаётся новый decision со ссылкой на ошибочный

5. **`worktrail spec record --task-id <id> --id <sid> --scope "..." --invariants "..."`**
   - Инварианты модуля/API через `;`. Specs иммутабельны
   - Опционально: `--file <path> --lines <range>`
   - Отличие от criteria: criteria — «ЧТО должно быть истинно для завершения задачи»,
     spec — «инварианты КОНКРЕТНОГО модуля/API», может пережить задачу

6. **`worktrail verify run --method <method>`** — прогнать верификацию
   - Методы: `pytest`, `shell`, `manual`, `none`
   - Результат → VRR (Verification Run Record) → строка в JSONL-лог
   - VRR содержит: пройдено/упало тестов, регрессии, исправления с прошлого прогона

7. **`worktrail finalize [--skip-review]`** — завершить задачу
   - Собирает review_package: контракт, decisions, specs, progress, VRR, `boundaries` (git diff)
   - Без `--skip-review`: статус → `review`, задача ждёт ревью
   - С `--skip-review`: статус → `done` (для простых задач)
   - Вычисляет время через `derive_time()` из git-лога
   - Пушит git-notes и теги: `git push origin refs/notes/worktrail refs/tags/worktrail/*`

### Режим ревью

Разработчик просит проверить задачу. Агент запускает панель экспертов параллельно.

**Поток:** review run → параллельные эксперты → review result → отчёт

1. **`worktrail review run --task-id <id> --json`** — получить задания для экспертов
   - Возвращает массив заданий. Каждое задание содержит:
     - `expert` — тип эксперта (code-auditor, contract-auditor, ...)
     - `prompt` — инструкция на естественном языке
     - `artifacts` — релевантные данные из review_package
     - `expected_output` — схема ответа (verdict, blockers, warnings, details)

2. **Запустить экспертов параллельно** — саб-агенты
   - Каждый эксперт получает свой prompt и артефакты
   - Эксперт возвращает: `verdict` (pass/fail), `blockers` (блокирующие замечания),
     `warnings` (предупреждения), `details` (проверка criteria)

3. **Собрать заключения** в review_result JSON
   - Агрегирует вердикты всех экспертов
   - Итоговый `verdict`: `accepted` (все pass) или `rejected` (хотя бы один fail)

4. **`worktrail review result --task-id <id> --verdict <accepted|rejected> --file <result.json>`**
   - Валидирует по схеме, записывает в git-note

5. **Вывести итоговый отчёт** — вердикт, блокирующие замечания, предупреждения

**Профили ревью** (выбираются автоматически по типу проекта):

| Профиль | Эксперты | Когда |
|---------|---------|-------|
| `code` (по умолчанию) | contract-auditor, code-auditor, decisions-auditor, boundaries-auditor, vrr-auditor | Проекты с тестовыми фреймворками |
| `1c` | contract-auditor, code-auditor, metadata-auditor, decisions-auditor, boundaries-auditor | Проекты на 1С:Предприятие |
| `research` | contract-auditor, sources-auditor | Исследовательские проекты, статьи |
| `generic` | contract-auditor | Fallback: личные заметки, черновики |

При rejected ревью: `contract update --set status=active` — возврат на доработку.
При accepted: задача готова к `finalize`.

## Что НЕ делать

- **Не выдумывай ID задач.** Используй ID из внешней системы (Jira, 1С, ERP).
- **Не работай без контракта.** Первое действие — `worktrail context --json`.
- **Не смешивай режимы.** Если сессия началась как ревью — не пиши код.
- **Не редактируй git-notes напрямую.** Только через CLI.
- **Не пуши git-notes вручную.** Агент делает это при `finalize` и после `review result`.
- **Не дублируй progress в decisions/specs.** Progress = «что сделал», decision = «почему и как», spec = «инварианты».
- **Не запускай ревью без review_package.** Сначала `finalize` (без `--skip-review`), потом `review run`.
- **Не игнорируй blockers при ревью.** Даже один blocker = rejected.
- **Не завершай задачу в обход finalize.** Даже с `--skip-review` — через CLI.
- **Не редактируй decisions и specs** — они иммутабельны. При ошибке создавай новый decision/spec.
- **Не используй `worktrail init`** — в v2 только `worktrail install` (глобально).

## Команды

| Команда | Назначение |
|---------|-----------|
| `worktrail install` | Глобальная установка (хуки, навык, managed-блок) |
| `worktrail context [--json]` | Определить текущую задачу из git-контекста |
| `worktrail list [--status <s>] [--json]` | Список задач в репозитории |
| `worktrail contract init --task-id <id> --name "..." [--scope "..."]` | Создать контракт задачи |
| `worktrail contract show [--task-id <id>] [--json]` | Показать контракт |
| `worktrail contract update --task-id <id> [--set <k=v>] [--criteria-file <f>] [--verify-file <f>]` | Обновить контракт |
| `worktrail progress record --task-id <id> --summary "..." [--commit <h>]` | Зафиксировать ход работы |
| `worktrail progress list --task-id <id> [--last <n>]` | История хода работ |
| `worktrail decision record --task-id <id> --id <did> --title "..." --rationale "..." [--file <p>] [--lines <r>]` | Записать решение |
| `worktrail decision list --task-id <id>` | Список решений задачи |
| `worktrail spec record --task-id <id> --id <sid> --scope "..." --invariants "..." [--file <p>]` | Зафиксировать спек |
| `worktrail spec list --task-id <id>` | Список спеков задачи |
| `worktrail verify run --method <m> [--task-id <id>] [--scope "..."]` | Запустить верификацию |
| `worktrail verify log [--task-id <id>] [--last] [--run <n>]` | История прогонов |
| `worktrail finalize [--task-id <id>] [--skip-review]` | Собрать review_package, финализировать |
| `worktrail review run --task-id <id> [--profile <p>]` | Подготовить задания экспертов |
| `worktrail review result --task-id <id> --verdict <accepted\|rejected> --file <f>` | Сохранить вердикт ревью |
| `worktrail time [--task-id <id>]` | Вычислить время по git-логу |
| `worktrail report [--task-id <id>] [--save]` | Markdown-отчёт |
| `worktrail archive tck [--path <p>] [--task-id <id>]` | Просмотреть старую TCK-структуру (read-only) |
| `worktrail doctor` | Диагностика |

Все команды поддерживают `--json` для машиночитаемого вывода.
Коды выхода: `0` = успех, `1` = ошибка, `2` = неоднозначность.

## Статусы задач

```
draft → active → review → done
active → done          (прямое закрытие без ревью)
review → active        (возврат на доработку)
active → blocked → active
любой → cancelled
```

| Статус | Когда |
|--------|-------|
| `draft` | Контракт создан, работа не начата |
| `active` | В работе |
| `blocked` | Заблокирована внешней зависимостью |
| `review` | На ревью (после finalize без --skip-review) |
| `done` | Завершена (после accepted ревью или --skip-review) |
| `cancelled` | Отменена |

Изменение статуса: `worktrail contract update --task-id <id> --set status=<s>`

## Данные: git-notes

Все структурные знания хранятся в git-notes `refs/notes/worktrail`.
**SQLite больше не используется** (`.worktrail/runtime.db` не создаётся).

| Тип записи | Описание | Иммутабелен |
|-----------|----------|------------|
| `contract` | Что делаем, критерии успеха, как проверять | Нет |
| `progress` | Хроника хода работ (автоматически из коммитов + вручную) | Нет |
| `decision` | Архитектурное решение с обоснованием и альтернативами | Да |
| `spec` | Инварианты модуля/API | Да |
| `review_package` | Пакет для ревью (собирается при finalize) | Да* |
| `review_result` | Вердикт экспертной панели | Да* |

\* — перезаписывается при повторном finalize/review.

Каждая задача имеет **якорный коммит** (первый коммит task-ветки или коммит создания контракта)
и лёгкий тег `worktrail/<task_id>`. Все notes висят на якорном коммите.
Поиск задач: `git tag -l 'worktrail/*'`.

Оперативные VRR-логи — JSONL на диске (`<scope>/.worktrail/<task_id>/vrr.jsonl`).
Итоговый VRR попадает в git-notes при finalize. JSONL-лог может быть удалён
после завершения задачи.

## Git-хуки

Устанавливаются глобально при `worktrail install` (через `git config --global core.hooksPath`).

| Хук | Действие |
|-----|---------|
| `post-commit` | Автоматический `progress record` с сообщением коммита. Только если `has_task: true` и статус `active`/`review`. Без задачи — молча пропускает |
| `post-checkout` | Выводит сводку новой задачи при смене ветки. Информационный — не меняет состояние |
| `prepare-commit-msg` | Добавляет `[<task_id>]` в начало commit-сообщения, если его ещё нет |

Хуки НЕ стартуют и НЕ останавливают задачи — только информируют и автоматизируют progress.

## Протокол взаимодействия

- Агент вызывает CLI с `--json` → worktrail возвращает JSON на stdout
- Ошибки — на stderr + код выхода
- Worktrail читает/пишет git-notes напрямую, но **НЕ делает коммиты** — это делает агент
- Агент пушит git-notes и теги при `finalize` и после `review result`:
  ```bash
  git push origin refs/notes/worktrail refs/tags/worktrail/*
  ```

## Профили проекта

Профиль определяет состав экспертной панели при ревью. Всё остальное универсально.
Агент определяет профиль автоматически по типу проекта. Разработчик может указать явно:
«Проведи ревью по профилю code».

## Отчётность

Отчёт выводится на русском, без git-жаргона:

```
Отчёт: ERP-4521 — Интеграция с бухгалтерией
═══════════════════════════════════════════

Статус: в работе | Ветка: task/ERP-4521-grpc
Время: 7.0ч (оценка по git-логу)

Progress:
├── [2.5ч] Проектирование контракта и валидация входных данных
├── [3.0ч] Реализация endpoint'ов /pay и /refund
└── [1.5ч] Обработка ошибок и retry-логика

Decisions:
├── D01: Выбор протокола — gRPC (стриминг, типизация)
└── D02: БД — PostgreSQL (транзакции, триггеры)

Specs:
└── S01: API /pay — ADDED: amount > 0, currency is required

VRR (последний прогон):
Пройдено: 24/24 | Регрессий: 0 | Метод: pytest
```

Экспорт в Markdown: `worktrail report --task-id <id> --save`

## Старая TCK-структура (`knowledge/tasks/`)

**Не мигрируется.** Просмотрщик `worktrail archive tck` читает старые `task.md`
и `registry.md` в режиме read-only. Если агент обнаруживает `knowledge/`:
читает как дополнительный источник исторического контекста, но все новые данные
пишет в git-notes. Не модифицирует `knowledge/`.

Worktrail v1 (`.worktrail/runtime.db`) — **не читается и не мигрируется**.
Слишком разная модель данных.
