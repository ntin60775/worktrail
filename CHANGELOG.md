# Changelog

## [0.2.0] — Unreleased

### Added
- **Journal**: task knowledge base with 6 entry kinds (`proposal`, `design`, `spec`, `decision`, `note`, `artifact`)
  - `worktrail journal <id> --kind ...` — add entries
  - `worktrail journal list <id>` — list entries
  - `worktrail journal show <id> <n>` — show entry
- **8 task statuses** (was 4): `draft`, `active`, `blocked`, `review`, `delivery`, `done`, `archived`, `cancelled`
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
- `_translate_status` now uses Russian labels for all 8 statuses

### Fixed
- Migration report now counts journal entries imported
- `create_task` accepts `branch` from old task format during migration
