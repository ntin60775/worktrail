// Package reviewer provides review run and review result operations.
// It generates expert review jobs for a task and processes their results.
package reviewer

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"worktrail/internal/gitnotes"
	"worktrail/internal/contract"
	"worktrail/internal/types"
)

// ErrNoReviewPackage is returned when a task has no assembled review package.
var ErrNoReviewPackage = errors.New("no review package found for task")

// ErrInvalidProfile is returned when the requested profile does not exist.
var ErrInvalidProfile = errors.New("unknown profile")

// ─── Profile-specific prompts ────────────────────────────────────────────────

var expertPrompts = map[string]string{
	"contract-auditor":   "Verify success_criteria against VRR results. Check every criterion is covered.",
	"code-auditor":       "Check invariants from specs in the changed code files. Look for abstraction leaks.",
	"decisions-auditor":  "Review rationale completeness and alternative consideration.",
	"boundaries-auditor": "Check scope — are there unexpected changes outside contract scope?",
	"vrr-auditor":        "Verify VRR honesty — do the numbers match actual test results?",
	"metadata-auditor":   "Check 1C metadata changes — requisites, forms, roles, subsystems.",
	"sources-auditor":    "Check source coverage and citation quality.",
}

// ─── ReviewRun ────────────────────────────────────────────────────────────────

// ReviewRun generates a set of ReviewJob entries for the task's review package.
// If profile is empty, it is auto-detected from the project structure.
func ReviewRun(taskID, profile string) ([]types.ReviewJob, error) {
	note, _, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", taskID, err)
	}
	if note.ReviewPackage == nil {
		return nil, ErrNoReviewPackage
	}
	rp := note.ReviewPackage
	if rp.Contract.TaskID == "" {
		rp.Contract.TaskID = taskID
	}

	if profile == "" {
		profile = detectProfile()
	}
	p, ok := types.Profiles[profile]
	if !ok {
		return nil, fmt.Errorf("%w: %s", ErrInvalidProfile, profile)
	}

	jobs := make([]types.ReviewJob, 0, len(p.Experts))
	for _, expert := range p.Experts {
		prompt := expertPrompts[expert]
		if prompt == "" {
			prompt = fmt.Sprintf("Review the task as %s.", expert)
		}

		job := types.ReviewJob{
			Expert:  expert,
			TaskID:  taskID,
			Profile: profile,
			Prompt:  prompt,
			Artifacts: types.ReviewArtifacts{
				Contract:   rp.Contract,
				Specs:      rp.Specs,
				Boundaries: rp.Boundaries,
				VRRSummary: rp.VerificationSummary.FinalRun.Summary,
			},
			ExpectedOutput: types.ExpectedOutput{
				Verdict: "pass",
			},
		}
		jobs = append(jobs, job)
	}

	return jobs, nil
}

// ─── ReviewResult ─────────────────────────────────────────────────────────────

// ReviewResult reads a JSON result file produced by a review sub-agent,
// validates it, writes it to the task's git-note, and returns the result.
func ReviewResult(taskID, verdict, resultFile string) (*types.ReviewResult, error) {
	data, err := os.ReadFile(resultFile)
	if err != nil {
		return nil, fmt.Errorf("read result file %s: %w", resultFile, err)
	}

	var rr types.ReviewResult
	if err := json.Unmarshal(data, &rr); err != nil {
		return nil, fmt.Errorf("parse result file: %w", err)
	}

	// Validate required fields.
	if rr.TaskID == "" {
		rr.TaskID = taskID
	}
	if verdict != "" {
		rr.Verdict = verdict
	}
	if rr.Verdict == "" {
		return nil, errors.New("review result missing verdict")
	}
	if rr.Timestamp.IsZero() {
		rr.Timestamp = time.Now()
	}
	if len(rr.Experts) == 0 {
		return nil, errors.New("review result has no expert entries")
	}

	// Write to git-note.
	note, anchor, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", taskID, err)
	}

	note.ReviewResult = &rr

	// Update contract status based on verdict.
	if note.Contract != nil {
		var targetStatus string
		switch rr.Verdict {
		case "accepted":
			targetStatus = "done"
		case "rejected":
			targetStatus = "active"
		}
		if targetStatus != "" {
			if err := contract.ValidateTransition(note.Contract.Status, targetStatus); err != nil {
				fmt.Fprintf(os.Stderr, "worktrail reviewer: %s: %v\n", taskID, err)
			} else {
				note.Contract.Status = targetStatus
				note.Contract.UpdatedAt = time.Now()
			}
		}
	}

	if err := gitnotes.Write(anchor, note); err != nil {
		return nil, fmt.Errorf("write review result: %w", err)
	}

	return &rr, nil
}

// ─── Profile detection ───────────────────────────────────────────────────────

// detectProfile inspects the working directory to determine the project type.
func detectProfile() string {
	// 1C:Enterprise — *.bsl files present.
	if matches, _ := filepath.Glob("*.bsl"); len(matches) > 0 {
		return "1c"
	}

	// Recursive check for *.bsl in immediate subdirectories (common in 1C repos).
	if hasBSL() {
		return "1c"
	}

	// Code project — tests directory, *_test.go files, or any code files.
	if info, err := os.Stat("tests"); err == nil && info.IsDir() {
		if hasCodeFiles() {
			return "code"
		}
	}
	if hasTestFiles() || hasCodeFiles() {
		return "code"
	}

	// Research project — paper.md, references.bib, or common research patterns.
	if fileExists("paper.md") || fileExists("references.bib") {
		return "research"
	}

	return "generic"
}

func hasBSL() bool {
	entries, err := os.ReadDir(".")
	if err != nil {
		return false
	}
	for _, e := range entries {
		if e.IsDir() {
			matches, _ := filepath.Glob(filepath.Join(e.Name(), "*.bsl"))
			if len(matches) > 0 {
				return true
			}
		}
	}
	return false
}

func hasCodeFiles() bool {
	codeExts := map[string]bool{
		".go": true, ".py": true, ".ts": true, ".js": true, ".rs": true,
		".java": true, ".c": true, ".cpp": true, ".h": true, ".hpp": true,
	}
	found := false
	filepath.Walk(".", func(path string, info os.FileInfo, err error) error {
		if err != nil || found {
			return nil
		}
		if info.IsDir() {
			name := info.Name()
			if name == ".git" || name == ".worktrail" || name == "vendor" || name == "node_modules" {
				return filepath.SkipDir
			}
			return nil
		}
		ext := filepath.Ext(path)
		if codeExts[ext] {
			found = true
		}
		return nil
	})
	return found
}

func hasTestFiles() bool {
	found := false
	filepath.Walk(".", func(path string, info os.FileInfo, err error) error {
		if err != nil || found {
			return nil
		}
		if info.IsDir() {
			if info.Name() == ".git" || info.Name() == ".worktrail" {
				return filepath.SkipDir
			}
			return nil
		}
		if strings.HasSuffix(path, "_test.go") {
			found = true
		}
		return nil
	})
	return found
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}