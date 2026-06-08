// Package gitnotes provides read, write, and list operations on git-notes
// in the refs/notes/worktrail namespace, plus anchor commit management.
package gitnotes

import (
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"

	"worktrail/internal/types"
)

const NotesRef = "refs/notes/worktrail"
const TagPrefix = "worktrail/"
const WorktrailDir = ".worktrail"

// ─── Anchor commit ──────────────────────────────────────────────────────────

// AnchorCommit returns the anchor commit hash for a task.
// If a tag worktrail/<sanitizedID> exists, returns its target commit.
// Otherwise returns HEAD without side effects.
// This is a READ-ONLY function — it never creates commits or tags.
func AnchorCommit(taskID string) (string, error) {
	tag := TagPrefix + sanitizeTag(taskID)

	out, err := git("rev-list", "-n", "1", "refs/tags/"+tag)
	if err == nil && strings.TrimSpace(out) != "" {
		return strings.TrimSpace(out), nil
	}

	return HEAD()
}

// CreateAnchor creates an empty anchor commit and tags it for the task.
// Returns the new commit hash. Only called from contract.Init.
func CreateAnchor(taskID string) (string, error) {
	tag := TagPrefix + sanitizeTag(taskID)

	// Check if tag already exists
	out, err := git("rev-list", "-n", "1", "refs/tags/"+tag)
	if err == nil && strings.TrimSpace(out) != "" {
		return "", fmt.Errorf("anchor tag %s already exists", tag)
	}

	commitMsg := fmt.Sprintf("worktrail: anchor for %s", taskID)
	if _, err := git("commit", "--allow-empty", "-m", commitMsg); err != nil {
		return "", fmt.Errorf("create anchor commit: %w", err)
	}

	head, err := HEAD()
	if err != nil {
		return "", err
	}

	if _, err := git("tag", "-f", tag, head); err != nil {
		return "", fmt.Errorf("tag anchor: %w", err)
	}

	return head, nil
}

// HEAD returns the current HEAD commit hash.
func HEAD() (string, error) {
	out, err := git("rev-parse", "HEAD")
	if err != nil {
		return "", fmt.Errorf("git rev-parse HEAD: %w", err)
	}
	return strings.TrimSpace(out), nil
}

// CurrentBranch returns the current branch name.
func CurrentBranch() (string, error) {
	out, err := git("rev-parse", "--abbrev-ref", "HEAD")
	if err != nil {
		return "", fmt.Errorf("git rev-parse --abbrev-ref HEAD: %w", err)
	}
	return strings.TrimSpace(out), nil
}

// sanitizeTag replaces non-ASCII/unsafe characters with dashes and appends a
// short hash of the original taskID to prevent collisions.
func sanitizeTag(taskID string) string {
	var b strings.Builder
	lastDash := false
	for _, r := range taskID {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') ||
			(r >= '0' && r <= '9') || r == '_' || r == '.' {
			b.WriteRune(r)
			lastDash = false
		} else {
			if !lastDash {
				b.WriteByte('-')
				lastDash = true
			}
		}
	}
	result := strings.Trim(b.String(), "-")
	if result == "" {
		result = "x"
	}
	h := uint32(0)
	for _, r := range taskID {
		h = h*31 + uint32(r)
	}
	return fmt.Sprintf("%s-%04x", result, h&0xFFFF)
}

// ─── Tag listing ────────────────────────────────────────────────────────────

// ListTags returns all worktrail/* tag names (with prefix).
func ListTags() ([]string, error) {
	out, err := git("tag", "-l", TagPrefix+"*")
	if err != nil {
		return nil, fmt.Errorf("git tag -l: %w", err)
	}
	if strings.TrimSpace(out) == "" {
		return nil, nil
	}
	lines := strings.Split(strings.TrimSpace(out), "\n")
	var tags []string
	for _, line := range lines {
		t := strings.TrimSpace(line)
		if t != "" {
			tags = append(tags, t)
		}
	}
	return tags, nil
}

// TaskIDFromTag strips the worktrail/ prefix from a tag name.
func TaskIDFromTag(tag string) string {
	return strings.TrimPrefix(tag, TagPrefix)
}

// ResolveTag returns the commit hash a worktrail tag points to.
func ResolveTag(tag string) (string, error) {
	out, err := git("rev-list", "-n", "1", "refs/tags/"+tag)
	if err != nil {
		return "", fmt.Errorf("resolve tag %s: %w", tag, err)
	}
	return strings.TrimSpace(out), nil
}

// ─── Notes CRUD ─────────────────────────────────────────────────────────────

// Read reads the aggregate TaskNote from the git-note on the anchor commit.
// Returns nil note if no note exists (not an error). Returns error on git failures.
func Read(anchorCommit string) (*types.TaskNote, error) {
	out, err := git("notes", "--ref="+NotesRef, "show", anchorCommit)
	if err != nil {
		// Distinguish "no note" from real errors by checking output.
		// git notes show exits 1 with "error: no note found for object" on stderr.
		// We can't easily distinguish via CombinedOutput, so check the message.
		if strings.Contains(err.Error(), "no note found") {
			return &types.TaskNote{}, nil
		}
		return nil, fmt.Errorf("git notes show %s: %w", anchorCommit, err)
	}

	var note types.TaskNote
	if err := json.Unmarshal([]byte(out), &note); err != nil {
		return nil, fmt.Errorf("parse task note: %w", err)
	}
	return &note, nil
}

// Write writes the aggregate TaskNote to the anchor commit's git-note.
// Returns error if note is nil.
func Write(anchorCommit string, note *types.TaskNote) error {
	if note == nil {
		return fmt.Errorf("cannot write nil note")
	}

	data, err := json.MarshalIndent(note, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal task note: %w", err)
	}

	if err := gitStdin("notes", "--ref="+NotesRef, "add", "-f", "-F", "-", anchorCommit, string(data)); err != nil {
		return fmt.Errorf("write note: %w", err)
	}
	return nil
}

// ─── Convenience helpers ────────────────────────────────────────────────────

// ReadByTask reads the TaskNote for a task by ID. Returns (note, anchor, error).
func ReadByTask(taskID string) (*types.TaskNote, string, error) {
	anchor, err := AnchorCommit(taskID)
	if err != nil {
		return nil, "", err
	}
	note, err := Read(anchor)
	if err != nil {
		return nil, "", err
	}
	return note, anchor, nil
}

// ─── helpers ────────────────────────────────────────────────────────────────

// git runs a git command and returns its stdout.
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

// gitStdin runs a git command piping stdin content through a temp file.
// Expects at least 3 args: the git args, the anchor commit, and the content.
func gitStdin(args ...string) error {
	if len(args) < 3 {
		return fmt.Errorf("gitStdin requires at least 3 args (git args, commit, content)")
	}

	n := len(args)
	content := args[n-1]
	anchor := args[n-2]
	baseArgs := args[:n-2]

	cmd := exec.Command("git", append(baseArgs, anchor)...)
	cmd.Stdin = strings.NewReader(content)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("git %s: %s", strings.Join(baseArgs, " "), string(out))
	}
	return nil
}
