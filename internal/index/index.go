// Package index generates a TASKS.md index of all tracked tasks,
// grouped by status. Inspired by OKF index.md for progressive disclosure.
package index

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"worktrail/internal/gitnotes"
	"worktrail/internal/types"
)

// BuildIndex generates a Markdown index of all tasks tracked in git-notes,
// grouped by status. Tasks with an existing report file are linked to it.
func BuildIndex() (string, error) {
	tags, err := gitnotes.ListTags()
	if err != nil {
		return "", fmt.Errorf("list tags: %w", err)
	}

	var b strings.Builder
	fmt.Fprintf(&b, "# Tasks — %s\n\n", time.Now().Format("2006-01-02"))

	if len(tags) == 0 {
		fmt.Fprintf(&b, "*No tasks tracked.*\n")
		return b.String(), nil
	}

	type taskInfo struct {
		summary  types.TaskSummary
		relates  []string
		hasDraft bool
	}

	// Collect and group by status.
	groups := map[string][]taskInfo{}
	statusOrder := []string{"active", "blocked", "review", "draft", "done", "cancelled"}

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

		// Check if individual report exists.
		hasDraft := false
		if _, err := os.Stat(filepath.Join(".worktrail", "reports", c.TaskID+".md")); err == nil {
			hasDraft = true
		}

		info := taskInfo{
			summary: types.TaskSummary{
				TaskID:       c.TaskID,
				Name:         name,
				Status:       c.Status,
				Branch:       c.Branch,
				AnchorCommit: anchor,
			},
			relates:  c.RelatesTo,
			hasDraft: hasDraft,
		}
		groups[c.Status] = append(groups[c.Status], info)
	}


	// If no tasks have contracts, report empty.
	hasAny := false
	for _, tasks := range groups {
		if len(tasks) > 0 {
			hasAny = true
			break
		}
	}
	if !hasAny {
		fmt.Fprintf(&b, "*No tasks tracked.*\n")
		return b.String(), nil
	}
	for _, status := range statusOrder {
		tasks, ok := groups[status]
		if !ok || len(tasks) == 0 {
			continue
		}
		fmt.Fprintf(&b, "## %s (%d)\n\n", statusLabel(status), len(tasks))
		for _, t := range tasks {
			display := t.summary.Name
			if t.hasDraft {
				display = fmt.Sprintf("[%s](.worktrail/reports/%s.md)", display, t.summary.TaskID)
			}
			fmt.Fprintf(&b, "- **%s** — %s", t.summary.TaskID, display)
			if t.summary.Branch != "" {
				fmt.Fprintf(&b, " (branch: `%s`)", t.summary.Branch)
			}
			if len(t.relates) > 0 {
				fmt.Fprintf(&b, " → related: %s", strings.Join(t.relates, ", "))
			}
			fmt.Fprintf(&b, "\n")
		}
		fmt.Fprintf(&b, "\n")
	}

	return b.String(), nil
}

func statusLabel(status string) string {
	switch status {
	case "active":
		return "Active"
	case "blocked":
		return "Blocked"
	case "review":
		return "Review"
	case "draft":
		return "Draft"
	case "done":
		return "Done"
	case "cancelled":
		return "Cancelled"
	default:
		return status
	}
}
