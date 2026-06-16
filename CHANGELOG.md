# Changelog


## [Unreleased] — 2026-06-16

### Added
- **TCK conflict resolution** (`install` step 0): detects and removes globally installed
  `task-centric-knowledge` skill, plus cleans TCK managed blocks from all project
  `AGENTS.md` files found under `~/dev/`.
- **Managed block injection** (`install` step 2b): injects `agents.md.block` into global
  agent rules for OMP (`~/.agents/AGENTS.md`), Pi (`~/.pi/agent/AGENTS.md`), and
  OpenCode (`~/.opencode/AGENTS.md`). Idempotent — repeat installs update the block,
  never duplicate.
- **`worktrail uninstall`**: removes hooks config, skill directory, binary, and managed
  blocks from all three agent global rules. Supports `--dry-run`.
- **Doctor managed-block checks**: `worktrail doctor` now reports managed block presence
  for each agent (`managed_block_omp`, `managed_block_pi`, `managed_block_opencode`)
  and TCK conflict status (`tck_conflict`).

## [0.2.0] — Unreleased

### Added
- **v2 Git hooks**: `prepare-commit-msg`, `post-commit`, `post-checkout` in `hooks/`
  - `prepare-commit-msg` — prepends `[task_id]` to commit message from current context
  - `post-commit` — auto-records progress with commit subject and hash (active/review tasks only)
  - `post-checkout` — prints task summary on branch switch (informational only)
- **Journal**: task knowledge base with 6 entry kinds (`proposal`, `design`, `spec`, `decision`, `note`, `artifact`)
  - `worktrail journal <id> --kind ...` — add entries
  - `worktrail journal list <id>` — list entries
  - `worktrail journal show <id> <n>` — show entry
- **7 task statuses** (was 4): `draft`, `active`, `blocked`, `review`, `done`, `archived`, `cancelled`
  - `worktrail status <id> --set <status>` — change task status
- **Task kinds**: `task`, `exploration`, `initiative`
  - `worktrail explore "<desc>" [--parent]` — lightweight research tasks
  - `worktrail initiative "<name>"` — create grouping initiative
  - `worktrail initiative list` / `initiative show <id>`
- **Subtask support**: `parent_id` now fully supported via CLI
  - `worktrail list --parent <id>` — show subtasks
  - `worktrail start <id> --parent <parent-id>` — create subtask
- **Archiving**: `worktrail archive <id> [--force]`
- **Enhanced list filters**: `--kind`, `--parent`, `--archived`
- **Full Markdown task export**: `worktrail report --task <id> --save` now includes journal entries and metadata
- **Schema auto-migration**: existing `.worktrail/runtime.db` databases are automatically upgraded
- **Journal import from knowledge/**: migrator now imports `sdd.md`, `decisions.md`, `plan.md` as journal entries

### Changed
- Task `status` default changed from `active` to `draft`
- `list` command shows kind column and supports new filters
- `_translate_status` now uses Russian labels for all 7 statuses
- **TrackerEngine.start()**: новые задачи сразу создаются в статусе `active`, существующие `draft`-задачи автоматически переводятся в `active` при старте сессии.
- **cmd_start**: если `--name` не указан, имя задачи автоматически выводится из git-ветки:
  - `task/TASK-001-fix-bug` → имя `"fix bug"`
  - `feature/oauth2` → имя `"oauth2"`
  - На `main`/`master` → fallback на `task_id`
- **cmd_status --set**: вывод теперь включает имя задачи (если оно отличается от ID).
- **initiative**: инициативы теперь создаются в статусе `active` (было `draft`).

### Fixed
- Удалён тестовый мусор из базы (TASK-001, TASK-002)
- OMP-001 и AUDIT-001 переведены из `draft` в `done`
- Migration report now counts journal entries imported
- `create_task` accepts `branch` from old task format during migration
- Migrator: `tasks_migrated` counter now increments correctly (was always 0)
- Migrator: `journal_entries_created` now shown in `MigrationReport.__str__`
- Migrator: backtick-wrapped values (`` `value` ``) from v1 passport tables now stripped
- Migrator: status map extended with missing v1 statuses (`черновик→draft`, `на проверке→review`, `заблокирована→blocked`, `отменена→cancelled`)
- Migrator: `"parent id"` (with space) now recognised alongside `"parent_id"`; empty markers (`—`, `-`, `нет`) treated as no parent
- Migrator: `"краткое имя"` now recognised as task name key
- Migrator: fallback status for unknown inputs changed from `active` to `draft`
- Migrator: rejects invalid task IDs (non-`TASK-*` format) with clear error instead of creating garbage tasks
- Migrator: `paused`/`on hold` v1 statuses now map to `blocked` (was `paused` — not in DB CHECK constraint)
- Migrator: missing English identity mappings (`draft`, `blocked`, `review`) added to status map
- Migrator: `_migrate_worklog`/`_migrate_journal` now wrapped in try/except — one task failure no longer crashes entire migration
- Migrator: `_migrate_journal` exceptions now logged (were silently swallowed)
- Migrator: `## Цель` and `## Итог` sections from task.md now imported as journal entries (previously only `## Описание` was searched — v1 files use `## Цель`)
- Reporter: `_translate_status` now covers all 7 statuses (was only 4)
- Parser: `_extract_task_id_from_path` now captures full ID including subtask suffix
- Parser: docstrings updated to reflect 7-status model
- Removed `delivery` status (unused in practice; v1 never had it)
