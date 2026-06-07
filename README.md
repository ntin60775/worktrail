# worktrail

Система управления знаниями по задачам и учёта рабочего времени внутри
git-репозитория.

**What is worktrail.**  A task knowledge & time management system that lives
inside your git repo.  Beyond time tracking, it captures design decisions,
specifications, architecture rationale, and research notes — all linked to
task IDs (JIRA, ERP, ЗАКАЗ — anything).  Everything is stored in a local
SQLite database (`.worktrail/runtime.db`); no cloud service, no login,
no subscription.  Russian CLI output, English code.

```
┌─────────────────────────────────────────┐
│  git repo/                              │
│  ├── .git/                              │
│  ├── .worktrail/        ← runtime data  │
│  │   ├── runtime.db     ← SQLite        │
│  │   ├── config.yaml    ← settings      │
│  │   └── reports/       ← .md exports   │
│  └── src/                               │
└─────────────────────────────────────────┘
```

---

## Installation

```bash
git clone https://github.com/your-repo/worktrail.git
cd worktrail
pip install -e .
```

Requires **Python 3.11+**.  Only dependency: `pyyaml`.

---

## Quick Start

```bash
# 1. Inside an existing git repo, initialize worktrail
worktrail init
# → ✓ worktrail инициализирован в /path/to/repo/.worktrail

# 2. Start tracking a task
worktrail start ERP-4521 --name "Интеграция с бухгалтерией"
# → ▶ Сессия запущена: ERP-4521 — 0с

# 3. Record progress checkpoints (2-5 per task is normal)
worktrail checkpoint "Проектирование контракта API"
worktrail checkpoint "Реализовал endpoint /pay"
# → ✓ Чекпоинт записан: ...

# 4. Finish working
worktrail stop
# → ■ Сессия остановлена. Всего: 2ч 15м

# 5. View a report
worktrail report
# → Отчёт за 29.05.2026
# → ═══════════════════
# → Задача ERP-4521: Интеграция с бухгалтерией
# → ├── [2.2ч] Проектирование контракта API
# → └── [1.5ч] Реализовал endpoint /pay
# → Итого: 3.7ч | Статус: в работе
```

# 6. Capture design decisions and specs
worktrail journal ERP-4521 --kind decision --title "Chose gRPC" --body "Better streaming support than REST"
worktrail journal ERP-4521 --kind spec --title "API /pay" --body "ADDED: amount > 0 validation"
# → Запись добавлена в журнал задачи

# 7. Lightweight research (no time tracking)
worktrail explore "Investigate payment gateway API"
# → Исследование создано: EXPL-0001

# 8. Group tasks into an initiative
worktrail initiative "Payment System Migration"
worktrail start TASK-002 --parent "Payment System Migration" --name "New /refund endpoint"
# → Задача TASK-002 привязана к инициативе

# 9. Export a task with journal to Markdown
worktrail report --task ERP-4521 --save
# → .worktrail/reports/ERP-4521.md

---

## Commands

| Command | Description |
|---------|-------------|
| `worktrail init` | Initialize `.worktrail/` in the current git repo |
| `worktrail start <task-id> [--name "..."]` | Begin a tracking session for a task |
| `worktrail stop` | End the current session and accumulate time |
| `worktrail pause` | Pause the active session |
| `worktrail resume` | Resume a paused session |
| `worktrail checkpoint "<message>"` | Record a progress checkpoint |
| `worktrail status [<id> --set <s>]` | Show current session / change task status |
| `worktrail list [--status\|--kind\|--parent\|--archived]` | List tasks with filters |
| `worktrail report [--today\|--week\|--task\|--date]` | Generate a time report |
| `worktrail report --task <id> --save` | Export full task report (Markdown) |
| `worktrail journal <id> --kind ...` | Add a journal entry to a task |
| `worktrail journal list <id>` | List journal entries for a task |
| `worktrail journal show <id> <n>` | Show a specific journal entry |
| `worktrail archive <id> [--force]` | Archive a task |
| `worktrail explore "<desc>" [--parent]` | Create a lightweight exploration task |
| `worktrail initiative "<name>"` | Create an initiative |
| `worktrail initiative list` | List all initiatives |
| `worktrail initiative show <id>` | Show initiative details and subtasks |
| `worktrail migrate --from <path>` | Migrate from task-centric-knowledge v1 |
| `worktrail uninstall` | Remove worktrail from the repo (asks confirmation) |
| `worktrail doctor` | Diagnostics: hooks, schema, idle config |

### Task ID

Any identifier works.  Use IDs from your external system — no extra mapping
needed:

```bash
worktrail start ERP-4521
worktrail start JIRA-12345
worktrail start ЗАКАЗ-0042
worktrail start TASK-001 --name "API Integration"
```

Branch naming convention (optional): `task/TASK-001-slug` or `du/DU-042`.
Worktrail auto-detects the task ID when you switch branches.


### Task Status (8 states)

```
draft → active → review → delivery → done → archived
                ↘ blocked → active
                         ↘ cancelled
```

| Status | Meaning |
|--------|---------|
| `draft` | Task created, work not started |
| `active` | In progress (tracker running) |
| `blocked` | Blocked by external dependency |
| `review` | Under review |
| `delivery` | Delivering to customer |
| `done` | Completed |
| `archived` | Archived |
| `cancelled` | Cancelled |

Change status: `worktrail status TASK-001 --set review`

### Journal (task knowledge base)

Each task can have journal entries of six kinds:

| Kind | Purpose |
|------|---------|
| `proposal` | Why we do this task |
| `design` | How we do it — architecture approach |
| `spec` | Invariants (delta format: ADDED/MODIFIED/REMOVED) |
| `decision` | Key decision with rationale |
| `note` | Free-form observation |
| `artifact` | Reference to a file/screenshot/log |

```bash
worktrail journal TASK-0037 --kind decision --title "Chose GUI stack" --body "..."
worktrail journal list TASK-0037
worktrail journal show TASK-0037 5
```
---

## Reports

Reports are rendered in Russian, with tree-drawing characters, no git jargon.

```
$ worktrail report
Отчёт за 29.05.2026
═══════════════════

Задача ERP-4521: Интеграция с бухгалтерией
├── [2.5ч] Проектирование контракта и валидация входных данных
├── [3.0ч] Реализация endpoint'ов /pay и /refund
└── [1.5ч] Обработка ошибок и retry-логика
Итого: 7.0ч | Статус: в работе

Задача TASK-002: Bug fix
├── [1.0ч] Репродукция бага на staging
└── [3.0ч] Фикс и тесты
Итого: 4.0ч | Статус: в работе

────────────────────
День: 11.0ч
```

Save reports as Markdown:

```bash
worktrail report --today --save
# → ✓ Отчёт сохранён: .worktrail/reports/2026-05-29.md
```

---

## Migration

If your project uses the old `knowledge/tasks/` structure (task-centric-knowledge v1):

```bash
worktrail migrate --from knowledge/
```

What happens:
1. Creates a git branch `worktrail/migrate-v1`
2. Parses old `task.md` files
3. Imports tasks, sessions, and checkpoints into `.worktrail/runtime.db`
4. Removes `knowledge/` from the working tree

Rollback: `git revert <commit-migration>`.

---

## Global Skill (optional)

Install the skill file so AI agents automatically know about worktrail in any
repository:

```bash
SKILL_DIR="$HOME/.agents/skills/worktrail"
mkdir -p "$SKILL_DIR"
cp /path/to/worktrail/SKILL.md "$SKILL_DIR/SKILL.md"
```

After this, any AI agent with skill support will:
- Auto-detect `.worktrail/` directories
- Know to run `worktrail start` before tasks
- Record checkpoints and generate reports on request
- Capture design decisions, specs, and proposals in journal
- Create explorations for research tasks, initiatives for grouping
- Manage task status transitions (draft → active → review → done)

---

## Git Hooks

When you run `worktrail init`, two git hooks are installed:

| Hook | Trigger | Action |
|------|---------|--------|
| `post-commit` | After `git commit` | Auto-checkpoint with commit message |
| `post-checkout` | After `git checkout` | Suggest start/stop based on task branch |

Example — commit auto-checkpoint:

```bash
git commit -m "Add payment validation"
# [worktrail] ✓ Auto-checkpoint: Add payment validation
```

Example — branch switch auto-stop:

```bash
git checkout main
# [worktrail] Авто-остановка сессии ERP-4521. Всего: 2ч 15м
```

Disable hooks in `config.yaml`:

```yaml
git_hooks_enabled: false
```

---

## Architecture

```
src/worktrail/
├── __init__.py           ← version
├── __main__.py           ← python -m worktrail entry point
├── cli/
│   ├── commands.py       ← @command / @arg registry + shared helpers
│   ├── main.py           ← argparse builder + dispatch loop
│   ├── doctor.py         ← diagnostics (schema, hooks, idle)
│   └── handlers/
│       ├── task.py       ← start, stop, pause, resume, checkpoint, status
│       ├── journal.py    ← journal add, list, show
│       ├── explore.py    ← lightweight exploration tasks
│       ├── initiative.py ← initiative create, list, show
│       ├── archive.py    ← task archiving
│       ├── report.py     ← report generation
│       ├── migrate.py    ← v1 migration
│       └── system.py     ← list, uninstall
├── core/
│   ├── __init__.py       ← find_project_root() (generic path discovery)
│   ├── models.py         ← Task (kind, branch), Session, Checkpoint, JournalEntry, Config
│   ├── db.py             ← SQLite schema (tasks, sessions, checkpoints, journal) + migration
│   ├── repository.py     ← CRUD for tasks, sessions, checkpoints, journal
│   └── config.py         ← YAML config load/save
├── git_bridge/
│   ├── __init__.py       ← public API exports
│   ├── parser.py         ← branch parsing, get_repo_root(), run_git()
│   └── hooks.py          ← install_hooks(), remove_hooks(), are_hooks_installed()
├── tracker/
│   ├── engine.py         ← TrackerEngine (session lifecycle)
│   └── idle.py           ← IdleMonitor (auto-pause on inactivity)
├── reporter/
│   ├── formatter.py      ← Report, ReportItem, Block dataclasses
│   └── writer.py         ← render_terminal(), render_markdown()
└── migrator/
    ├── parser.py         ← v1 task.md parser
    └── migrator.py       ← migration orchestrator
```

**Design principles:**

- **Local SQLite** — all data in `.worktrail/runtime.db`, zero external services
- **No lock-in** — plain SQLite + YAML; read directly or export to Markdown
- **Git-native** — lives inside repos, follows branch switches, hooks into commits
- **Single active session** — only one session can be active at a time
- **Knowledge as first-class citizen** — journal captures decisions, specs, and rationale alongside time data
- **Russian CLI** — all user-facing text in Russian; code and docs in English

---

## License

MIT
