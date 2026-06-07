// Package executor provides progress, decision, spec recording, and
// task finalization operations for worktrail v2.
package executor

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"worktrail/internal/context"
	"worktrail/internal/gitnotes"
	wtime "worktrail/internal/time"
	"worktrail/internal/types"
)

// ErrNoTask is returned when the current context has no active task.
var ErrNoTask = errors.New("no task in current context")

// resolveTaskID resolves taskID from git context when empty.
func resolveTaskID(taskID string) (string, error) {
	if taskID != "" {
		return taskID, nil
	}
	ctx, err := context.Resolve()
	if err != nil {
		return "", fmt.Errorf("resolve context: %w", err)
	}
	if !ctx.HasTask {
		return "", ErrNoTask
	}
	return ctx.TaskID, nil
}

// ─── Progress ────────────────────────────────────────────────────────────────

// RecordProgress appends a progress entry to the task's git-note.
// If taskID is empty, the current task is resolved from git context.
func RecordProgress(taskID, summary, commit string) (*types.Progress, error) {
	tid, err := resolveTaskID(taskID)
	if err != nil {
		return nil, err
	}

	note, anchor, err := gitnotes.ReadByTask(tid)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", tid, err)
	}

	p := types.Progress{
		TaskID:    tid,
		Timestamp: time.Now(),
		Summary:   summary,
		Commit:    commit,
	}

	note.Progress = append(note.Progress, p)
	if err := gitnotes.Write(anchor, note); err != nil {
		return nil, fmt.Errorf("write progress: %w", err)
	}

	return &p, nil
}

// ListProgress returns progress entries for a task.
// If taskID is empty, the current task is resolved from git context.
// If last > 0, only the last N entries are returned.
func ListProgress(taskID string, last int) ([]types.Progress, error) {
	tid, err := resolveTaskID(taskID)
	if err != nil {
		return nil, err
	}

	note, _, err := gitnotes.ReadByTask(tid)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", tid, err)
	}

	all := note.Progress
	if last > 0 && last < len(all) {
		return all[len(all)-last:], nil
	}
	return all, nil
}

// ─── Decision ─────────────────────────────────────────────────────────────────

// RecordDecision appends a decision entry to the task's git-note.
// If taskID is empty, the current task is resolved from git context.
func RecordDecision(taskID, id, title, rationale, file, lines string, alternatives []string) (*types.Decision, error) {
	tid, err := resolveTaskID(taskID)
	if err != nil {
		return nil, err
	}

	note, anchor, err := gitnotes.ReadByTask(tid)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", tid, err)
	}

	d := types.Decision{
		ID:           id,
		TaskID:       tid,
		Title:        title,
		Rationale:    rationale,
		Alternatives: alternatives,
		File:         file,
		Lines:        lines,
		CreatedAt:    time.Now(),
	}

	note.Decisions = append(note.Decisions, d)
	if err := gitnotes.Write(anchor, note); err != nil {
		return nil, fmt.Errorf("write decision: %w", err)
	}

	return &d, nil
}

// ListDecisions returns all decisions for a task.
// If taskID is empty, the current task is resolved from git context.
func ListDecisions(taskID string) ([]types.Decision, error) {
	tid, err := resolveTaskID(taskID)
	if err != nil {
		return nil, err
	}

	note, _, err := gitnotes.ReadByTask(tid)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", tid, err)
	}

	return note.Decisions, nil
}

// ─── Spec ─────────────────────────────────────────────────────────────────────

// RecordSpec appends a spec entry to the task's git-note.
// If taskID is empty, the current task is resolved from git context.
func RecordSpec(taskID, id, scope string, invariants []string, file, lines string) (*types.Spec, error) {
	tid, err := resolveTaskID(taskID)
	if err != nil {
		return nil, err
	}

	note, anchor, err := gitnotes.ReadByTask(tid)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", tid, err)
	}

	s := types.Spec{
		ID:         id,
		TaskID:     tid,
		Scope:      scope,
		Invariants: invariants,
		File:       file,
		Lines:      lines,
		CreatedAt:  time.Now(),
	}

	note.Specs = append(note.Specs, s)
	if err := gitnotes.Write(anchor, note); err != nil {
		return nil, fmt.Errorf("write spec: %w", err)
	}

	return &s, nil
}

// ListSpecs returns all specs for a task.
// If taskID is empty, the current task is resolved from git context.
func ListSpecs(taskID string) ([]types.Spec, error) {
	tid, err := resolveTaskID(taskID)
	if err != nil {
		return nil, err
	}

	note, _, err := gitnotes.ReadByTask(tid)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", tid, err)
	}

	return note.Specs, nil
}

// ─── Finalize ─────────────────────────────────────────────────────────────────

// Finalize assembles a review package, sets the task status, derives work
// duration, and writes everything back to the git-note.
//
// If skipReview is true, status is set to "done" immediately without building
// a review package. Otherwise, status is set to "review" and the review
// package is stored in the note.
//
// If taskID is empty, the current task is resolved from git context.
func Finalize(taskID string, skipReview bool) (*types.ReviewPackage, error) {
	tid, err := resolveTaskID(taskID)
	if err != nil {
		return nil, err
	}

	note, anchor, err := gitnotes.ReadByTask(tid)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", tid, err)
	}
	if note.Contract == nil {
		return nil, fmt.Errorf("no contract for task %s", tid)
	}

	contract := note.Contract

	// Compute boundaries: changed files since anchor commit.
	changedFiles, err := diffFiles(anchor)
	if err != nil {
		return nil, fmt.Errorf("compute boundaries: %w", err)
	}

	// Read last VRR from JSONL log.
	lastVRR, totalRuns := readLastVRR(tid)

	vrrLogPath := filepath.Join(gitnotes.WorktrailDir, tid, "vrr.jsonl")

	verificationSummary := types.VerificationSummary{
		TotalRuns: totalRuns,
		VRRLog:    vrrLogPath,
	}
	if lastVRR != nil {
		verificationSummary.FinalRun = *lastVRR
	}

	boundaries := types.Boundaries{
		ChangedFiles: changedFiles,
	}

	var rp *types.ReviewPackage

	if skipReview {
		contract.Status = "done"
	} else {
		contract.Status = "review"

		rp = &types.ReviewPackage{
			TaskID:              tid,
			Status:              "review",
			Contract:            *contract,
			VerificationSummary: verificationSummary,
			Decisions:           note.Decisions,
			Specs:               note.Specs,
			Boundaries:          boundaries,
		}
		note.ReviewPackage = rp
	}

	contract.UpdatedAt = time.Now()

	// Derive work duration and update contract.
	_, _ = wtime.Derive(tid)

	note.Contract = contract

	if err := gitnotes.Write(anchor, note); err != nil {
		return nil, fmt.Errorf("write finalize: %w", err)
	}

	return rp, nil
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

// diffFiles returns the list of files changed between the given commit and HEAD.
func diffFiles(anchor string) ([]string, error) {
	cmd := exec.Command("git", "diff", anchor+"..HEAD", "--name-only")
	out, err := cmd.Output()
	if err != nil {
		// If the range is empty or invalid, return empty list.
		return nil, nil
	}
	if len(out) == 0 {
		return nil, nil
	}
	lines := splitLines(string(out))
	return lines, nil
}

// readLastVRR reads the VRR JSONL file for a task and returns the last entry
// and the total number of entries. If the file doesn't exist or is empty,
// both return values are zero.
func readLastVRR(taskID string) (*types.VRR, int) {
	path := filepath.Join(gitnotes.WorktrailDir, taskID, "vrr.jsonl")
	f, err := os.Open(path)
	if err != nil {
		return nil, 0
	}
	defer f.Close()

	var last *types.VRR
	count := 0
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var v types.VRR
		if err := json.Unmarshal(line, &v); err != nil {
			continue
		}
		count++
		last = &v
	}

	return last, count
}

// splitLines splits text into lines, trimming trailing empty entries.
func splitLines(s string) []string {
	raw := make([]string, 0)
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == '\n' {
			raw = append(raw, s[start:i])
			start = i + 1
		}
	}
	if start < len(s) {
		raw = append(raw, s[start:])
	}
	// Trim trailing empty strings.
	for len(raw) > 0 && raw[len(raw)-1] == "" {
		raw = raw[:len(raw)-1]
	}
	return raw
}
