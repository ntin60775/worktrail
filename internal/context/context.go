// Package context resolves the current task from git context (branch, notes, tags).
package context

import (
	"fmt"
	"os/exec"
	"regexp"
	"strings"

	"worktrail/internal/gitnotes"
	"worktrail/internal/types"
)

// branchPatterns extracts task IDs from branch names.
var branchPatterns = []*regexp.Regexp{
	regexp.MustCompile(`^(task|feature|bugfix|jira)/([^/]+)`),
	regexp.MustCompile(`^([A-Z]+-\d+)`),
}

// Resolve determines the current task from git context.
// Priority:
// 1. Branch name matches task/<id>* or feature/<id>*/bugfix/<id>*/jira/<id>*
// 2. Git-note with branch = current branch on any anchor commit
// 3. If on main/master: find latest active task
// 4. Nothing found → has_task: false
func Resolve() (*types.ContextOutput, error) {
	branch, err := gitnotes.CurrentBranch()
	if err != nil {
		return nil, err
	}

	// 1. Try branch name extraction
	if taskID := extractTaskID(branch); taskID != "" {
		return resolveByTaskID(taskID, branch)
	}

	// 2. Search git-notes for branch match
	tags, err := gitnotes.ListTags()
	if err != nil {
		return nil, err
	}
	for _, tag := range tags {
		anchor, err := gitnotes.ResolveTag(tag)
		if err != nil {
			continue
		}
		note, err := gitnotes.Read(anchor)
		if err != nil || note.Contract == nil {
			continue
		}
		if note.Contract.Branch == branch {
			return ctxOutput(note.Contract, anchor, branch), nil
		}
	}

	// 3. Main/master — find latest active task
	if branch == "main" || branch == "master" {
		return resolveLatestActive(branch)
	}

	// 4. Nothing found
	return &types.ContextOutput{
		Branch:  branch,
		HasTask: false,
	}, nil
}

func extractTaskID(branch string) string {
	for _, re := range branchPatterns {
		m := re.FindStringSubmatch(branch)
		if m != nil {
			if len(m) > 2 {
				return m[2]
			}
			return m[1]
		}
	}
	return ""
}

func resolveByTaskID(taskID, branch string) (*types.ContextOutput, error) {
	note, anchor, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return &types.ContextOutput{
			TaskID:  taskID,
			Branch:  branch,
			HasTask: false,
		}, nil
	}
	if note.Contract == nil {
		return &types.ContextOutput{
			TaskID:  taskID,
			Branch:  branch,
			HasTask: false,
		}, nil
	}
	return ctxOutput(note.Contract, anchor, branch), nil
}

func resolveLatestActive(branch string) (*types.ContextOutput, error) {
	tags, err := gitnotes.ListTags()
	if err != nil {
		return nil, err
	}

	var latest *types.Contract
	var latestAnchor string
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
		if c.Status == "done" || c.Status == "cancelled" {
			continue
		}
		if latest == nil || c.UpdatedAt.After(latest.UpdatedAt) {
			latest = c
			latestAnchor = anchor
		}
	}

	if latest != nil {
		return ctxOutput(latest, latestAnchor, branch), nil
	}
	return &types.ContextOutput{
		Branch:  branch,
		HasTask: false,
	}, nil
}

func ctxOutput(c *types.Contract, anchor, branch string) *types.ContextOutput {
	return &types.ContextOutput{
		TaskID:       c.TaskID,
		Name:         c.Name,
		Status:       c.Status,
		Branch:       branch,
		AnchorCommit: anchor,
		Contract:     c,
		HasContract:  true,
		HasTask:      true,
	}
}

// Git is the git command runner for internal use.
func git(args ...string) (string, error) {
	cmd := exec.Command("git", args...)
	out, err := cmd.Output()
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return "", fmt.Errorf("git %s: %s", strings.Join(args, " "), string(exitErr.Stderr))
		}
		return "", fmt.Errorf("git %s: %w", strings.Join(args, " "), err)
	}
	return string(out), nil
}
