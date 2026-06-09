---
name: worktrail
description: >
  v2 — универсальная knowledge-система задач в git-репозитории.
  Режим исполнения: context → contract → progress → decisions → specs → finalize → report.
  Данные в git-notes, установка одной командой, разработчик не оператор.
  Используй, когда в репозитории есть refs/notes/worktrail или когда
  пользователь просит начать/закончить задачу, записать прогресс,
  принять решение, зафиксировать спек или сгенерировать отчёт.
---

# worktrail v2

## Когда использовать

- В репозитории настроен worktrail (есть `refs/notes/worktrail` или `git tag -l 'worktrail/*'` непусто)
- Пользователь просит: «начни задачу», «запиши что сделал», «сколько времени», «отчёт»
- Пользователь просит: «запиши решение», «зафиксируй спек»
- Пользователь просит установить worktrail: «настрой учёт задач»

## Установка

Одна глобальная установка:

```bash
worktrail install
```

Устанавливает git-хуки глобально (`git config --global core.hooksPath`),
копирует SKILL.md и agents.md.block. После установки worktrail доступен
во всех репозиториях. Проверить: `worktrail doctor`.

## Границы системы

Worktrail управляет **знаниями о задачах** (контракт, прогресс, решения, спеки, отчёты).
Он **НЕ управляет**:
- Тестовым контуром (агент сам запускает `go test`, `pytest`, `oscript -check`)
- Ревью (агент сам читает git diff, сверяет с критериями контракта и спеками)
- Артефактами задачи (код, конфиги, структура каталогов)
- CI/CD, деплоем, проектными инструментами

## Поток работы

Разработчик говорит ЧТО делать, агент делает и фиксирует знания.
Агент — единственный оператор worktrail. Разработник не вызывает CLI вручную.

**Поток:** context → contract → progress → decisions → specs → finalize → report

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

6. **`worktrail finalize [--task-id <id>]`** — завершить задачу
   - Статус → `done`
   - Сохраняет обновлённый контракт в git-note
   - Агент после finalize **сам** запускает тесты и проводит ревью:
     - Тестовый прогон: `go test ./...`, `pytest`, `oscript -check` — любая команда
     - Ревью: читает `git diff`, сверяет с критериями контракта и спеками
     - Вердикт и результаты ревью — в `progress record --summary "Ревью: ..."`

7. **`worktrail report [--task-id <id>] [--save]`** — markdown-отчёт
8. **`worktrail report --timesheet`** — отчёт для начальника (часы, хронология, решения)
9. **`worktrail time [--task-id <id>]`** — оценка времени по git-логу

## Что НЕ делать

- **Не выдумывай ID задач.** Используй ID из внешней системы (Jira, 1С, ERP).
- **Не работай без контракта.** Первое действие — `worktrail context --json`.
- **Не редактируй git-notes напрямую.** Только через CLI.
- **Не дублируй progress в decisions/specs.** Progress = «что сделал», decision = «почему и как», spec = «инварианты».
- **Не завершай задачу в обход finalize.** Всегда через CLI.
- **Не редактируй decisions и specs** — они иммутабельны. При ошибке создавай новый decision/spec.
- **Не используй `worktrail init`** — в v2 только `worktrail install` (глобально).
- **Worktrail не запускает тесты.** Агент делает это сам (`go test`, `pytest`, `oscript -check`, ...).
- **Worktrail не оркестрирует ревью.** Агент сам читает git diff и сверяет с контрактом и спеками.

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
| `worktrail finalize [--task-id <id>]` | Завершить задачу (статус → done) |
| `worktrail time [--task-id <id>]` | Вычислить время по git-логу |
| `worktrail report [--task-id <id>] [--save]` | Markdown-отчёт |
| `worktrail report --timesheet [--task-id <id>] [--from <d>] [--to <d>]` | Отчёт для начальника |
| `worktrail archive tck [--path <p>] [--task-id <id>]` | Просмотреть старую TCK-структуру (read-only) |
| `worktrail doctor` | Диагностика |

Все команды поддерживают `--json` для машиночитаемого вывода.
Коды выхода: `0` = успех, `1` = ошибка, `2` = неоднозначность.

## Статусы задач

```
draft → active → done
active → blocked → active
active → cancelled
blocked → cancelled
done → active     (переоткрытие)
cancelled → draft (реактивация)
```

| Статус | Когда |
|--------|-------|
| `draft` | Контракт создан, работа не начата |
| `active` | В работе |
| `blocked` | Заблокирована внешней зависимостью |
| `done` | Завершена (после `finalize`) |
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

Каждая задача имеет **якорный коммит** (первый коммит task-ветки или коммит создания контракта)
и лёгкий тег `worktrail/<task_id>`. Все notes висят на якорном коммите.
Поиск задач: `git tag -l 'worktrail/*'`.

## Git-хуки

Устанавливаются глобально при `worktrail install` (через `git config --global core.hooksPath`).

| Хук | Действие |
|-----|---------|
| `post-commit` | Автоматический `progress record` с сообщением коммита. Только если `has_task: true` и статус `active`. Без задачи — молча пропускает |
| `post-checkout` | Выводит сводку новой задачи при смене ветки. Информационный — не меняет состояние |
| `prepare-commit-msg` | Добавляет `[<task_id>]` в начало commit-сообщения, если его ещё нет |

Хуки НЕ стартуют и НЕ останавливают задачи — только информируют и автоматизируют progress.

## Протокол взаимодействия

- Агент вызывает CLI с `--json` → worktrail возвращает JSON на stdout
- Ошибки — на stderr + код выхода
- Worktrail читает/пишет git-notes напрямую, но **НЕ делает коммиты** — это делает агент
- Агент пушит git-notes и теги при `finalize`:
  ```bash
  git push origin refs/notes/worktrail refs/tags/worktrail/*
  ```

## Отчётность

Отчёт выводится на русском, без git-жаргона.

**Обычный отчёт** (`worktrail report --task-id <id>`):
```
# Task: ERP-4521 — Интеграция с бухгалтерией

## Status
- Task ID: ERP-4521
- Status: active
- Branch: task/ERP-4521-grpc

## Time Tracking
7.0ч

## Contract
Scope: integration/gateway
Интеграция с бухгалтерией через gRPC

## Progress Timeline
- 2026-06-01 10:15 — Проектирование контракта и валидация
- 2026-06-01 13:30 — Реализация endpoint'ов /pay и /refund
- 2026-06-01 15:00 — Обработка ошибок и retry-логика

## Decisions
### D01: Выбор протокола
- Rationale: gRPC (стриминг, типизация)
- Alternatives: REST, GraphQL

## Specs
### S01
- Scope: integration/gateway
- Invariants:
  - amount > 0
  - currency is required
```

**Timesheet** (`worktrail report --timesheet`):
```
# Отчёт о работе: 1–8 июня 2026

## Итого
| Показатель | Значение |
| Всего часов | 18.5 |
| Задач выполнено | 3 |
| Задач в работе | 2 |

## Выполненные задачи
### WT-001: Переход на worktrail v2 — 8.5ч
| Когда | Что сделано |
| 02:54 | Спецификация: 5 раундов рецензирования |
...

## Хронология по дням
### 2026-06-01, Пн — 4.5ч
- 10:15 — [ERP-4521] Проектирование контракта
...
```

## Старая TCK-структура (`knowledge/tasks/`)

**Не мигрируется.** Просмотрщик `worktrail archive tck` читает старые `task.md`
и `registry.md` в режиме read-only. Если агент обнаруживает `knowledge/`:
читает как дополнительный источник исторического контекста, но все новые данные
пишет в git-notes. Не модифицирует `knowledge/`.

Worktrail v1 (`.worktrail/runtime.db`) — **не читается и не мигрируется**.
Слишком разная модель данных.
