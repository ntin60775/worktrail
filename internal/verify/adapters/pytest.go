// Package adapters provides built-in verification adapter implementations.
package adapters

import (
	"fmt"
	"os/exec"
	"strconv"
	"strings"

	"worktrail/internal/types"
)

// PytestAdapter runs pytest against the scope path.
type PytestAdapter struct{}

func (a *PytestAdapter) Name() string { return "pytest" }

func (a *PytestAdapter) Run(taskID, scope, method string) (*types.VRR, error) {
	vrr := &types.VRR{
		Method: method,
		TaskID: taskID,
		Commit: headCommit(),
	}

	// Try pytest --json-report first.
	args := []string{"--json-report"}
	if scope != "" {
		args = append(args, scope)
	}
	out, _ := exec.Command("pytest", args...).CombinedOutput()

	// If output contains JSON summary fields, parse it.
	raw := string(out)
	if strings.Contains(raw, `"summary"`) {
		a.parseJSONReport(vrr, raw)
		return vrr, nil
	}

	// Fall back to -q and parse the summary line.
	return a.fallbackParse(taskID, scope, method)
}

// fallbackParse runs pytest -q and parses the "N passed" summary line.
func (a *PytestAdapter) fallbackParse(taskID, scope, method string) (*types.VRR, error) {
	vrr := &types.VRR{
		Method: method,
		TaskID: taskID,
		Commit: headCommit(),
	}

	args := []string{"-q"}
	if scope != "" {
		args = append(args, scope)
	}
	out, _ := exec.Command("pytest", args...).CombinedOutput()

	// Parse lines like: "3 passed, 1 failed in 0.12s"
	summary := string(out)
	vrr.Summary.Total = 0
	vrr.Summary.Passed = 0
	vrr.Summary.Failed = 0

	// Extract counts from the last meaningful line.
	lines := strings.Split(strings.TrimSpace(summary), "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if strings.Contains(line, "passed") || strings.Contains(line, "failed") {
			a.parseSummaryLine(vrr, line)
			break
		}
		if strings.Contains(line, "no tests ran") || strings.Contains(line, "error") {
			break
		}
	}

	if vrr.Summary.Total == 0 {
		// Try to extract individual failure lines.
		vrr.Summary.Total = vrr.Summary.Passed + vrr.Summary.Failed
	}
	return vrr, nil
}

// parseJSONReport extracts counts from pytest's JSON output.
func (a *PytestAdapter) parseJSONReport(vrr *types.VRR, raw string) {
	// The JSON report has a top-level "summary" object with "passed", "failed",
	// "total", etc. We do a lightweight manual parse to avoid importing
	// encoding/json for the full nested structure.
	//
	// Look for: "passed": N, "failed": N, "total": N
	vrr.Summary.Passed = extractJSONInt(raw, "passed")
	vrr.Summary.Failed = extractJSONInt(raw, "failed")
	if t := extractJSONInt(raw, "total"); t > 0 {
		vrr.Summary.Total = t
	} else {
		vrr.Summary.Total = vrr.Summary.Passed + vrr.Summary.Failed
	}

	// Extract failure details from "tests" array entries with "outcome":"failed".
	a.extractFailures(vrr, raw)
}

// parseSummaryLine parses pytest's console summary like "3 passed, 1 failed".
func (a *PytestAdapter) parseSummaryLine(vrr *types.VRR, line string) {
	for _, part := range strings.Split(line, ",") {
		part = strings.TrimSpace(part)
		fields := strings.Fields(part)
		if len(fields) < 2 {
			continue
		}
		n, err := strconv.Atoi(fields[0])
		if err != nil {
			continue
		}
		switch {
		case strings.Contains(part, "passed"):
			vrr.Summary.Passed = n
		case strings.Contains(part, "failed"):
			vrr.Summary.Failed = n
		}
	}
	vrr.Summary.Total = vrr.Summary.Passed + vrr.Summary.Failed
}

// extractFailures scans raw JSON for failed test entries.
func (a *PytestAdapter) extractFailures(vrr *types.VRR, raw string) {
	// Simple scan for failure entries — look for "outcome": "failed"
	// and extract name/message from surrounding context.
	// This is best-effort; full parsing would require encoding/json.
	search := `"outcome": "failed"`
	idx := 0
	for {
		pos := strings.Index(raw[idx:], search)
		if pos < 0 {
			break
		}
		idx += pos + len(search)

		failure := types.VRRFailure{}

		// Extract name from preceding "nodeid" or "name" field.
		if n := extractStringBefore(raw[:idx], `"nodeid"`); n != "" {
			failure.Name = n
		} else if n := extractStringBefore(raw[:idx], `"name"`); n != "" {
			failure.Name = n
		}

		// Extract message from following "longrepr" field.
		if m := extractStringAfter(raw[idx:], `"longrepr"`); m != "" {
			failure.Message = m
		}

		if failure.Name != "" || failure.Message != "" {
			vrr.Failures = append(vrr.Failures, failure)
		}
	}
	vrr.Summary.Failed = len(vrr.Failures)
}

// ─── Lightweight JSON field extractors ───────────────────────────────────────

// extractJSONInt finds "key": N and returns N.
func extractJSONInt(raw, key string) int {
	search := fmt.Sprintf(`"%s":`, key)
	idx := strings.Index(raw, search)
	if idx < 0 {
		return 0
	}
	rest := strings.TrimSpace(raw[idx+len(search):])
	// Read digits.
	end := 0
	for end < len(rest) && (rest[end] >= '0' && rest[end] <= '9') {
		end++
	}
	if end == 0 {
		return 0
	}
	n, _ := strconv.Atoi(rest[:end])
	return n
}

// extractStringBefore finds the last "key": "value" pair before pos.
func extractStringBefore(raw, key string) string {
	search := fmt.Sprintf(`"%s":`, key)
	idx := strings.LastIndex(raw, search)
	if idx < 0 {
		return ""
	}
	rest := raw[idx+len(search):]
	// Skip whitespace and opening quote.
	rest = strings.TrimSpace(rest)
	if len(rest) == 0 || rest[0] != '"' {
		return ""
	}
	rest = rest[1:]
	end := strings.Index(rest, `"`)
	if end < 0 {
		return ""
	}
	return rest[:end]
}

// extractStringAfter finds the first "key": "value" pair after pos.
func extractStringAfter(raw, key string) string {
	search := fmt.Sprintf(`"%s":`, key)
	idx := strings.Index(raw, search)
	if idx < 0 {
		return ""
	}
	rest := raw[idx+len(search):]
	rest = strings.TrimSpace(rest)
	if len(rest) == 0 || rest[0] != '"' {
		return ""
	}
	rest = rest[1:]
	end := strings.Index(rest, `"`)
	if end < 0 {
		return ""
	}
	return rest[:end]
}


