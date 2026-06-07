// Package list implements the List command — enumerating all tracked tasks
// with optional status filtering.
package list

import (
	"fmt"

	"worktrail/internal/gitnotes"
	"worktrail/internal/types"
)

// List returns summaries of all tasks tracked in git-notes, optionally
// filtered by contract status. An empty statusFilter matches all tasks.
func List(statusFilter string) ([]types.TaskSummary, error) {
	tags, err := gitnotes.ListTags()
	if err != nil {
		return nil, fmt.Errorf("list tags: %w", err)
	}
	if len(tags) == 0 {
		return nil, nil
	}

	var summaries []types.TaskSummary
	for _, tag := range tags {
		anchor, err := gitnotes.ResolveTag(tag)
		if err != nil {
			return nil, fmt.Errorf("resolve tag %s: %w", tag, err)
		}

		note, err := gitnotes.Read(anchor)
		if err != nil {
			return nil, fmt.Errorf("read note for %s: %w", tag, err)
		}

		if note.Contract == nil {
			continue
		}

		c := note.Contract
		if statusFilter != "" && c.Status != statusFilter {
			continue
		}

		name := c.Name
		if name == "" {
			name = c.Summary
		}

		summaries = append(summaries, types.TaskSummary{
			TaskID:       c.TaskID,
			Name:         name,
			Status:       c.Status,
			Branch:       c.Branch,
			AnchorCommit: anchor,
		})
	}

	return summaries, nil
}
