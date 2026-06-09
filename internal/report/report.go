// Package report generates Markdown reports for worktrail tasks.
package report

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"worktrail/internal/context"
	"worktrail/internal/gitnotes"
	worktime "worktrail/internal/time"
	"worktrail/internal/types"
)

// BuildReport generates a Markdown report for the given task.
// If taskID is empty, the current task is resolved from git context.
func BuildReport(taskID string) (string, error) {
	if taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return "", fmt.Errorf("resolve context: %w", err)
		}
		if !ctx.HasTask {
			return "", fmt.Errorf("no task in current context")
		}
		taskID = ctx.TaskID
	}

	note, anchor, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return "", fmt.Errorf("read task %s: %w", taskID, err)
	}
	if note.Contract == nil {
		return "", fmt.Errorf("task %s has no contract", taskID)
	}

	c := note.Contract

	var b strings.Builder

	// Header
	title := c.Name
	if title == "" {
		title = c.Summary
	}
	if title == "" {
		title = taskID
	}
	fmt.Fprintf(&b, "# Task: %s\n\n", title)

	// Status
	fmt.Fprintf(&b, "## Status\n\n")
	fmt.Fprintf(&b, "- **Task ID:** %s\n", c.TaskID)
	fmt.Fprintf(&b, "- **Status:** %s\n", c.Status)
	if c.Branch != "" {
		fmt.Fprintf(&b, "- **Branch:** %s\n", c.Branch)
	}
	fmt.Fprintf(&b, "- **Anchor:** `%s`\n", anchor[:8])
	fmt.Fprintf(&b, "- **Created:** %s\n", c.CreatedAt.Format(time.RFC3339))
	if !c.UpdatedAt.IsZero() {
		fmt.Fprintf(&b, "- **Updated:** %s\n", c.UpdatedAt.Format(time.RFC3339))
	}
	fmt.Fprintf(&b, "\n")

	// Time tracking
	dur, err := worktime.Derive(taskID)
	if err == nil && dur != "" {
		fmt.Fprintf(&b, "## Time Tracking\n\n")
		fmt.Fprintf(&b, "**%s**\n\n", dur)
	}

	// Contract summary
	fmt.Fprintf(&b, "## Contract\n\n")
	if c.Scope != "" {
		fmt.Fprintf(&b, "**Scope:** %s\n\n", c.Scope)
	}
	if c.Summary != "" {
		fmt.Fprintf(&b, "%s\n\n", c.Summary)
	}

	// Success criteria
	if len(c.SuccessCriteria) > 0 {
		fmt.Fprintf(&b, "### Success Criteria\n\n")
		for _, sc := range c.SuccessCriteria {
			fmt.Fprintf(&b, "- **[%s]** %s", sc.ID, sc.Statement)
			if len(sc.CoveredBy) > 0 {
				fmt.Fprintf(&b, " (covered by: %s)", strings.Join(sc.CoveredBy, ", "))
			}
			fmt.Fprintf(&b, "\n")
		}
		fmt.Fprintf(&b, "\n")
	}

	// Verification methods
	if len(c.Verification) > 0 {
		fmt.Fprintf(&b, "### Verification\n\n")
		for _, vm := range c.Verification {
			label := vm.Label
			if label == "" {
				label = vm.Method
			}
			fmt.Fprintf(&b, "- **%s** (%s)", label, vm.Method)
			if vm.Scope != "" {
				fmt.Fprintf(&b, " — scope: `%s`", vm.Scope)
			}
			fmt.Fprintf(&b, "\n")
		}
		fmt.Fprintf(&b, "\n")
	}

	// Progress timeline
	if len(note.Progress) > 0 {
		fmt.Fprintf(&b, "## Progress Timeline\n\n")
		for _, p := range note.Progress {
			commit := ""
			if p.Commit != "" && len(p.Commit) >= 8 {
				commit = fmt.Sprintf(" [`%s`]", p.Commit[:8])
			}
			fmt.Fprintf(&b, "- %s — %s%s\n",
				p.Timestamp.Format("2006-01-02 15:04"),
				p.Summary,
				commit,
			)
		}
		fmt.Fprintf(&b, "\n")
	}

	// Decisions
	if len(note.Decisions) > 0 {
		fmt.Fprintf(&b, "## Decisions\n\n")
		for _, d := range note.Decisions {
			fmt.Fprintf(&b, "### %s\n\n", d.Title)
			fmt.Fprintf(&b, "- **ID:** %s\n", d.ID)
			if d.File != "" {
				loc := d.File
				if d.Lines != "" {
					loc += ":" + d.Lines
				}
				fmt.Fprintf(&b, "- **Location:** `%s`\n", loc)
			}
			fmt.Fprintf(&b, "- **Rationale:** %s\n", d.Rationale)
			if len(d.Alternatives) > 0 {
				fmt.Fprintf(&b, "- **Alternatives:** %s\n", strings.Join(d.Alternatives, ", "))
			}
			fmt.Fprintf(&b, "\n")
		}
	}

	// Specs
	if len(note.Specs) > 0 {
		fmt.Fprintf(&b, "## Specs\n\n")
		for _, s := range note.Specs {
			fmt.Fprintf(&b, "### %s\n\n", s.ID)
			fmt.Fprintf(&b, "- **Scope:** %s\n", s.Scope)
			if s.File != "" {
				loc := s.File
				if s.Lines != "" {
					loc += ":" + s.Lines
				}
				fmt.Fprintf(&b, "- **Location:** `%s`\n", loc)
			}
			fmt.Fprintf(&b, "- **Invariants:**\n")
			for _, inv := range s.Invariants {
				fmt.Fprintf(&b, "  - %s\n", inv)
			}
			fmt.Fprintf(&b, "\n")
		}
	}


	return b.String(), nil
}

// BuildReportAll generates a summary report for all tracked tasks.
func BuildReportAll() (string, error) {
	tags, err := gitnotes.ListTags()
	if err != nil {
		return "", fmt.Errorf("list tags: %w", err)
	}

	var b strings.Builder
	fmt.Fprintf(&b, "# Worktrail Report — All Tasks\n\n")
	fmt.Fprintf(&b, "**Generated:** %s\n\n", time.Now().Format(time.RFC3339))

	if len(tags) == 0 {
		fmt.Fprintf(&b, "*No tasks tracked.*\n")
		return b.String(), nil
	}

	// Collect summaries
	type taskInfo struct {
		summary types.TaskSummary
		note    *types.TaskNote
	}

	var tasks []taskInfo
	for _, tag := range tags {
		anchor, err := gitnotes.ResolveTag(tag)
		if err != nil {
			continue
		}
		note, err := gitnotes.Read(anchor)
		if err != nil || note.Contract == nil {
			continue
		}
		c := note.Contract
		name := c.Name
		if name == "" {
			name = c.Summary
		}
		tasks = append(tasks, taskInfo{
			summary: types.TaskSummary{
				TaskID:       c.TaskID,
				Name:         name,
				Status:       c.Status,
				Branch:       c.Branch,
				AnchorCommit: anchor,
			},
			note: note,
		})
	}

	// Stats
	statusCounts := map[string]int{}
	for _, t := range tasks {
		statusCounts[t.summary.Status]++
	}
	fmt.Fprintf(&b, "## Summary\n\n")
	fmt.Fprintf(&b, "- **Total tasks:** %d\n", len(tasks))
	for status, count := range statusCounts {
		fmt.Fprintf(&b, "- **%s:** %d\n", status, count)
	}
	fmt.Fprintf(&b, "\n")

	// Table
	fmt.Fprintf(&b, "## Tasks\n\n")
	fmt.Fprintf(&b, "| Task ID | Name | Status | Branch |\n")
	fmt.Fprintf(&b, "|---------|------|--------|--------|\n")
	for _, t := range tasks {
		name := t.summary.Name
		if len(name) > 50 {
			name = name[:47] + "..."
		}
		fmt.Fprintf(&b, "| %s | %s | %s | %s |\n",
			t.summary.TaskID,
			name,
			t.summary.Status,
			t.summary.Branch,
		)
	}
	fmt.Fprintf(&b, "\n")

	return b.String(), nil
}

// ─── Timesheet ───────────────────────────────────────────────────────────────

// BuildTimesheet generates a human-readable markdown timesheet for the given task.
// If taskID is empty, the current task is resolved from git context.
// from and to are optional date filters in "YYYY-MM-DD" format.
func BuildTimesheet(taskID, from, to string) (string, error) {
	if taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return "", fmt.Errorf("resolve context: %w", err)
		}
		if !ctx.HasTask {
			return "", fmt.Errorf("no task in current context")
		}
		taskID = ctx.TaskID
	}

	note, _, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return "", fmt.Errorf("read task %s: %w", taskID, err)
	}
	if note.Contract == nil {
		return "", fmt.Errorf("task %s has no contract", taskID)
	}

	c := note.Contract
	title := c.Name
	if title == "" {
		title = taskID
	}

	var b strings.Builder
	fmt.Fprintf(&b, "# %s: %s\n\n", taskID, title)
	fmt.Fprintf(&b, "## Итого\n\n")

	// Filter progress by date range
	entries := filterProgress(note.Progress, from, to)

	// Calculate hours from progress entries
	hours := deriveHours(entries)
	fmt.Fprintf(&b, "**%.1fч**, %s\n\n", hours, c.Status)

	// Chronology
	if len(entries) > 0 {
		fmt.Fprintf(&b, "## Хронология\n\n")
		fmt.Fprintf(&b, "| Когда | Что сделано |\n")
		fmt.Fprintf(&b, "|-------|------------|\n")
		for _, p := range entries {
			fmt.Fprintf(&b, "| %s | %s |\n",
				p.Timestamp.Format("15:04 02.01.2006"),
				p.Summary,
			)
		}
		fmt.Fprintf(&b, "\n")
	}

	// Key decisions
	if len(note.Decisions) > 0 {
		fmt.Fprintf(&b, "## Ключевые решения\n\n")
		for _, d := range note.Decisions {
			fmt.Fprintf(&b, "- **%s:** %s\n", d.Title, d.Rationale)
		}
		fmt.Fprintf(&b, "\n")
	}

	return b.String(), nil
}

// BuildTimesheetAll generates a timesheet covering all tasks.
// from and to are optional date filters in "YYYY-MM-DD" format.
func BuildTimesheetAll(from, to string) (string, error) {
	tags, err := gitnotes.ListTags()
	if err != nil {
		return "", fmt.Errorf("list tags: %w", err)
	}

	var b strings.Builder

	// Period header
	periodLabel := "весь период"
	if from != "" || to != "" {
		periodLabel = ""
		if from != "" {
			periodLabel = "с " + from
		}
		if to != "" {
			if periodLabel != "" {
				periodLabel += " "
			}
			periodLabel += "по " + to
		}
	}
	fmt.Fprintf(&b, "# Отчёт о работе: %s\n\n", periodLabel)

	if len(tags) == 0 {
		fmt.Fprintf(&b, "*Нет отслеживаемых задач.*\n")
		return b.String(), nil
	}

	// Collect task data
	type taskData struct {
		id       string
		name     string
		status   string
		hours    float64
		progress []types.Progress
		decisions []types.Decision
	}

	var doneTasks []taskData
	var activeTasks []taskData
	var totalHours float64

	for _, tag := range tags {
		anchor, err := gitnotes.ResolveTag(tag)
		if err != nil {
			continue
		}
		note, err := gitnotes.Read(anchor)
		if err != nil || note.Contract == nil {
			continue
		}
		c := note.Contract
		name := c.Name
		if name == "" {
			name = c.Summary
		}
		if name == "" {
			name = c.TaskID
		}

		entries := filterProgress(note.Progress, from, to)
		h := deriveHours(entries)

		td := taskData{
			id:        c.TaskID,
			name:      name,
			status:    c.Status,
			hours:     h,
			progress:  entries,
			decisions: note.Decisions,
		}

		totalHours += h

		switch c.Status {
		case "done", "cancelled":
			doneTasks = append(doneTasks, td)
		default:
			activeTasks = append(activeTasks, td)
		}
	}

	// Summary
	fmt.Fprintf(&b, "## Итого\n\n")
	fmt.Fprintf(&b, "| Показатель | Значение |\n")
	fmt.Fprintf(&b, "|-----------|---------|\n")
	fmt.Fprintf(&b, "| Всего часов | %.1f |\n", totalHours)
	fmt.Fprintf(&b, "| Задач выполнено | %d |\n", len(doneTasks))
	fmt.Fprintf(&b, "| Задач в работе | %d |\n\n", len(activeTasks))

	// Done tasks
	if len(doneTasks) > 0 {
		fmt.Fprintf(&b, "## Выполненные задачи\n\n")
		for _, td := range doneTasks {
			fmt.Fprintf(&b, "### %s: %s — %.1fч\n\n", td.id, td.name, td.hours)
			if td.progress != nil && len(td.progress) > 0 {
				fmt.Fprintf(&b, "| Когда | Что сделано |\n")
				fmt.Fprintf(&b, "|-------|------------|\n")
				for _, p := range td.progress {
					fmt.Fprintf(&b, "| %s | %s |\n",
						p.Timestamp.Format("15:04"),
						p.Summary,
					)
				}
				fmt.Fprintf(&b, "\n")
			}
			if td.decisions != nil && len(td.decisions) > 0 {
				for _, d := range td.decisions {
					fmt.Fprintf(&b, "- **%s:** %s\n", d.Title, d.Rationale)
				}
				fmt.Fprintf(&b, "\n")
			}
		}
	}

	// Active tasks
	if len(activeTasks) > 0 {
		fmt.Fprintf(&b, "## В работе\n\n")
		fmt.Fprintf(&b, "| Задача | Часов | Статус |\n")
		fmt.Fprintf(&b, "|--------|-------|--------|\n")
		for _, td := range activeTasks {
			fmt.Fprintf(&b, "| %s: %s | %.1f | %s |\n",
				td.id, td.name, td.hours, td.status,
			)
		}
		fmt.Fprintf(&b, "\n")
	}

	// Daily chronology
	if totalHours > 0 {
		fmt.Fprintf(&b, "## Хронология по дням\n\n")
		daily := groupByDay(tags, from, to)
		for _, d := range daily {
			fmt.Fprint(&b, d)
		}
	}

	return b.String(), nil
}

// ─── Timesheet helpers ───────────────────────────────────────────────────────

// filterProgress returns progress entries within the given date range.
func filterProgress(entries []types.Progress, from, to string) []types.Progress {
	if from == "" && to == "" {
		return entries
	}
	var fromT, toT time.Time
	if from != "" {
		t, err := time.Parse("2006-01-02", from)
		if err == nil {
			fromT = t
		}
	}
	if to != "" {
		t, err := time.Parse("2006-01-02", to)
		if err == nil {
			toT = t.Add(24*time.Hour - time.Second)
		}
	}
	out := make([]types.Progress, 0, len(entries))
	for _, e := range entries {
		if !fromT.IsZero() && e.Timestamp.Before(fromT) {
			continue
		}
		if !toT.IsZero() && e.Timestamp.After(toT) {
			continue
		}
		out = append(out, e)
	}
	return out
}

// deriveHours estimates hours from progress entries using a 4h gap heuristic.
func deriveHours(entries []types.Progress) float64 {
	if len(entries) < 2 {
		return 0
	}
	var total time.Duration
	for i := 1; i < len(entries); i++ {
		d := entries[i].Timestamp.Sub(entries[i-1].Timestamp)
		if d > 0 && d <= 4*time.Hour {
			total += d
		}
	}
	return total.Hours()
}

// groupByDay collects all progress entries across tasks and groups by day.
func groupByDay(tags []string, from, to string) []string {
	type entry struct {
		ts      time.Time
		task    string
		summary string
	}
	var all []entry

	for _, tag := range tags {
		anchor, err := gitnotes.ResolveTag(tag)
		if err != nil {
			continue
		}
		note, err := gitnotes.Read(anchor)
		if err != nil || note.Contract == nil {
			continue
		}
		for _, p := range note.Progress {
			if from != "" {
				ft, err := time.Parse("2006-01-02", from)
				if err == nil && p.Timestamp.Before(ft) {
					continue
				}
			}
			if to != "" {
				tt, err := time.Parse("2006-01-02", to)
				if err == nil && p.Timestamp.After(tt.Add(24*time.Hour-time.Second)) {
					continue
				}
			}
			all = append(all, entry{
				ts:      p.Timestamp,
				task:    note.Contract.TaskID,
				summary: p.Summary,
			})
		}
	}

	// Sort by timestamp
	for i := 0; i < len(all); i++ {
		for j := i + 1; j < len(all); j++ {
			if all[j].ts.Before(all[i].ts) {
				all[i], all[j] = all[j], all[i]
			}
		}
	}

	// Group by day
	var days []string
	type dayGroup struct {
		date    string
		entries []entry
	}
	var groups []dayGroup
	for _, e := range all {
		dateKey := e.ts.Format("2006-01-02")
		if len(groups) == 0 || groups[len(groups)-1].date != dateKey {
			groups = append(groups, dayGroup{date: dateKey})
		}
		groups[len(groups)-1].entries = append(groups[len(groups)-1].entries, e)
	}

	weekdays := []string{"Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"}
	for _, g := range groups {
		first := g.entries[0].ts
		wd := weekdays[first.Weekday()]

		var total time.Duration
		for i := 1; i < len(g.entries); i++ {
			d := g.entries[i].ts.Sub(g.entries[i-1].ts)
			if d > 0 && d <= 4*time.Hour {
				total += d
			}
		}

		var b strings.Builder
		fmt.Fprintf(&b, "### %s, %s — %.1fч\n\n",
			g.date, wd, total.Hours())
		for _, e := range g.entries {
			fmt.Fprintf(&b, "- %s — [%s] %s\n",
				e.ts.Format("15:04"),
				e.task,
				e.summary,
			)
		}
		fmt.Fprintf(&b, "\n")
		days = append(days, b.String())
	}

	return days
}

// SaveReport writes the report content to .worktrail/reports/<taskID>.md.
func SaveReport(taskID string, content string) error {
	dir := filepath.Join(gitnotes.WorktrailDir, "reports")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("create reports dir: %w", err)
	}
	path := filepath.Join(dir, taskID+".md")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		return fmt.Errorf("write report: %w", err)
	}
	return nil
}
