# Domain Model

Домен — знание о том, **как верифицировать** и **что проверять при ревью** в конкретной экосистеме.

Домен **не** создаёт код, структуру каталогов, конфиги инструментов или другие артефакты задачи.
Его зона ответственности: ответить на вопрос «этот проект из моего мира?» и «как проверить качество?».

## Interface

```go
type Domain interface {
    Name() string
    Detect(root string) bool
    Adapters() []verify.Adapter
    ExpertPrompts() map[string]string  // expertName → prompt
}
```

Core вызывает `Detect()` при `worktrail install` и `worktrail review run`.
Если домен обнаружен:
- адаптеры регистрируются в глобальном реестре `verify.Adapters`
- промпты экспертов добавляются в реестр `reviewer.ExpertPrompts`

## Domain config file

Каждый домен описывается YAML-файлом. Встроенные домены — в коде.
Кастомные — в `.worktrail/domain/<name>.yaml` (проект) или `~/.config/worktrail/<name>.yaml` (глобально).

### Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DomainConfig",
  "type": "object",
  "required": ["name", "detect"],
  "properties": {
    "name": {
      "type": "string",
      "description": "Domain identifier (code, 1c, research, ...)"
    },
    "label": {
      "type": "string",
      "description": "Human-readable name"
    },
    "detect": {
      "type": "object",
      "required": ["extensions"],
      "properties": {
        "extensions": {
          "type": "array",
          "items": { "type": "string" },
          "description": "File extensions that signal this domain (.go, .bsl, .py, ...)"
        },
        "files": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Specific files that signal this domain (MainModule.bsl, go.mod, pyproject.toml, ...)"
        },
        "directories": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Directory names that signal this domain (Config/, internal/, src/, ...)"
        }
      }
    },
    "adapters": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["method", "label"],
        "properties": {
          "method": {
            "type": "string",
            "description": "Adapter method name (go_test, pytest, 1c_syntax_check, ...)"
          },
          "label": {
            "type": "string",
            "description": "Human-readable label"
          },
          "run": {
            "type": "string",
            "description": "Shell command template. ${WORKTRAIL_SCOPE} = scope parameter. Falls back to built-in runner."
          },
          "scope": {
            "type": "string",
            "description": "Default scope for this adapter (./..., tests/, src/, ...)"
          }
        }
      }
    },
    "experts": {
      "type": "object",
      "description": "Review experts for this domain. Key = expert name, value = expert config.",
      "additionalProperties": {
        "type": "object",
        "required": ["prompt"],
        "properties": {
          "prompt": {
            "type": "string",
            "description": "Prompt template for the expert reviewer"
          },
          "blockers": {
            "type": "boolean",
            "default": true,
            "description": "Can this expert issue blockers? (false = warnings only)"
          }
        }
      }
    }
  }
}
```

### Example: domain `1c` (конфигуратор)

```yaml
name: 1c
label: "1С:Предприятие (конфигуратор)"
detect:
  extensions: [.bsl, .mdo, .os]
  files: [MainModule.bsl]
  directories: [Config]

adapters:
  - method: 1c_syntax_check
    label: "Синтаксис-контроль BSL"
    run: "oscript -check ${WORKTRAIL_SCOPE:-src/}"
    scope: src/
  - method: manual
    label: "Ручное тестирование 1С"

experts:
  1c-code-auditor:
    prompt: |
      Проверь BSL-код (только файлы .bsl из выгрузки конфигуратора):
      1. Именование: процедуры и функции — глагол (РассчитатьСумму), переменные — существительное.
         Префиксы модулей соответствуют типу объекта.
      2. Запросы: нет WHERE ИСТИНА / WHERE 1=1. Используются временные таблицы где уместно.
         Индексы соответствуют условиям запросов.
      3. Блокировки: явные ПоменятьРегистр/Заблокировать с правильным отбором.
         Нет ПоместитьВоВременнуюТаблицу внутри цикла.
      4. Исключения: Попытка/Исключение обрамляют ВСЕ опасные операции (запись в БД, HTTP, файлы).
         Текст исключения информативный.
      5. Транзакции: НачатьТранзакцию/ЗафиксироватьТранзакцию вокруг пакетных изменений.
         ОткатТранзакции в обработчиках ошибок.
    blockers: true

  1c-metadata-auditor:
    prompt: |
      Проверь метаданные из выгрузки конфигуратора (.mdo, Configuration.xml):
      1. Реквизиты: типы соответствуют ссылочным объектам (СправочникСсылка.Имя, а не Строка).
         Измерения регистров накопления/сведений соответствуют реквизитам документов.
      2. Регистры: нет потерянных измерений (каждое измерение регистра участвует в движениях).
         Периодичность регистра сведений соответствует бизнес-логике.
      3. Роли: права не избыточны. RLS-ограничения покрывают все чтения/записи.
         Нет назначенных прав на неиспользуемые объекты.
      4. Подсистемы: иерархия плоская, состав соответствует функциональным блокам.
         Каждый объект конфигурации входит ровно в одну подсистему.
      5. Планы обмена: если есть распределённая ИБ — состав узлов корректен,
         авторегистрация настроена, планы видов характеристик покрыты.
    blockers: true
```

### Example: domain `code` (общая разработка)

```yaml
name: code
label: "Software development"
detect:
  extensions: [.go, .py, .ts, .js, .rs, .java, .c, .cpp, .h]
  files: [go.mod, pyproject.toml, package.json, Cargo.toml]
  directories: [tests, test, spec]

adapters:
  - method: go_test
    label: "go test"
    scope: ./...
  - method: pytest
    label: "pytest"
    scope: tests/
  - method: shell
    label: "Shell command"
  - method: manual
    label: "Manual verification"

experts:
  code-auditor:
    prompt: |
      Проверь код:
      1. Именование соответствует конвенциям языка.
      2. Нет утечек абстракций между слоями.
      3. Обработка ошибок: нет подавленных исключений, ошибки пробрасываются осмысленно.
      4. Ресурсы освобождаются (defer/close/with).
      5. Нет гонок данных в конкурентном коде.
    blockers: true

  codeboundaries-auditor:
    prompt: |
      Проверь границы изменений:
      1. Все изменённые файлы входят в scope задачи.
      2. Нет неожиданных изменений в несвязанных модулях.
      3. Публичные API не сломаны без явного решения.
    blockers: true
```

## Built-in domains

Worktrail поставляется со встроенными доменами в коде. Они не требуют YAML-файлов:

| Домен | Детект | Адаптеры | Эксперты |
|-------|--------|----------|----------|
| `code` | `.go`, `.py`, `.ts`, `.js`, `.rs`, `go.mod`, `tests/`… | go_test, pytest, shell, manual | code-auditor, boundaries-auditor |
| `1c` | `.bsl`, `.mdo`, `.os`, `MainModule.bsl`, `Config/` | 1c_syntax_check, manual | 1c-code-auditor, 1c-metadata-auditor |
| `research` | `paper.md`, `references.bib`, `data/`, `notebooks/` | manual | sources-auditor |
| `core` | всегда активен | manual, none | contract-auditor, decisions-auditor |

## Custom domains

Разработчик может добавить `.worktrail/domain/mydomain.yaml`. Приоритет: проектный → глобальный → встроенный.
Custom domain может переопределить встроенный с тем же именем.

## Execution flow

```
worktrail install
  ├─ core: хуки, бинарь, SKILL.md
  └─ для каждого обнаруженного домена:
       └─ регистрация адаптеров в verify.Adapters

worktrail review run --task-id X
  ├─ detect domains
  ├─ для каждого домена:
  │    └─ добавить экспертов в review jobs
  └─ возвращает массив ReviewJob
```
