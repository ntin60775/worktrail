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
			if p.Commit != "" {
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

	// Review package
	if note.ReviewPackage != nil {
		rp := note.ReviewPackage
		fmt.Fprintf(&b, "## Review Package\n\n")
		fmt.Fprintf(&b, "- **Status:** %s\n", rp.Status)
		fmt.Fprintf(&b, "- **Verification Runs:** %d\n", rp.VerificationSummary.TotalRuns)
		if rp.Boundaries.ChangedFiles != nil && len(rp.Boundaries.ChangedFiles) > 0 {
			fmt.Fprintf(&b, "- **Changed Files:**\n")
			for _, f := range rp.Boundaries.ChangedFiles {
				fmt.Fprintf(&b, "  - `%s`\n", f)
			}
		}
		fmt.Fprintf(&b, "\n")
	}

	// Review result
	if note.ReviewResult != nil {
		rr := note.ReviewResult
		fmt.Fprintf(&b, "## Review Result\n\n")
		fmt.Fprintf(&b, "- **Verdict:** %s\n", rr.Verdict)
		fmt.Fprintf(&b, "- **Reviewed:** %s\n", rr.Timestamp.Format(time.RFC3339))
		for _, expert := range rr.Experts {
			fmt.Fprintf(&b, "\n### Expert: %s (%s)\n\n", expert.Expert, expert.Verdict)
			if len(expert.Blockers) > 0 {
				fmt.Fprintf(&b, "**Blockers:**\n\n")
				for _, bl := range expert.Blockers {
					fmt.Fprintf(&b, "- **%s:** %s", bl.Title, bl.Problem)
					if bl.Fix != "" {
						fmt.Fprintf(&b, " → Fix: %s", bl.Fix)
					}
					fmt.Fprintf(&b, "\n")
				}
			}
			if len(expert.Warnings) > 0 {
				fmt.Fprintf(&b, "**Warnings:**\n\n")
				for _, w := range expert.Warnings {
					fmt.Fprintf(&b, "- **%s:** %s\n", w.Title, w.Problem)
				}
			}
			if len(expert.Details) > 0 {
				fmt.Fprintf(&b, "**Details:**\n\n")
				for _, d := range expert.Details {
					fmt.Fprintf(&b, "- **[%s]** %s", d.CriteriaID, d.Status)
					if d.Evidence != "" {
						fmt.Fprintf(&b, " — %s", d.Evidence)
					}
					fmt.Fprintf(&b, "\n")
				}
			}
		}
		fmt.Fprintf(&b, "\n")
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
