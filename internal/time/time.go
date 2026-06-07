// Package time derives approximate work duration from git commit history.
// It uses a 4-hour gap between consecutive commits as a session boundary
// to distinguish active work periods from breaks, nights, and weekends.
package time

import (
	"fmt"
	"os/exec"
	"strings"
	stdtime "time"

	"worktrail/internal/context"
	"worktrail/internal/gitnotes"
	"worktrail/internal/types"
)

const sessionGapThreshold = 4 * stdtime.Hour

// Derive returns an approximate human-readable work duration for the given task
// based on git commit timestamps. If taskID is empty, the current task is
// resolved from git context.
func Derive(taskID string) (string, error) {
	secs, err := DurationSeconds(taskID)
	if err != nil {
		return "", err
	}
	if secs <= 0 {
		return "0m", nil
	}

	d := stdtime.Duration(secs) * stdtime.Second
	hours := int(d.Hours())
	minutes := int(d.Minutes()) % 60

	if hours > 0 {
		return fmt.Sprintf("%dh %dm", hours, minutes), nil
	}
	return fmt.Sprintf("%dm", minutes), nil
}

// DurationSeconds returns the total approximate work time in seconds.
func DurationSeconds(taskID string) (int64, error) {
	contract, err := resolveContract(taskID)
	if err != nil {
		return 0, err
	}

	times, err := commitTimesAfter(contract.CreatedAt)
	if err != nil {
		return 0, fmt.Errorf("git log: %w", err)
	}

	var totalSecs int64
	for i := 1; i < len(times); i++ {
		gap := times[i].Sub(times[i-1])
		if gap <= sessionGapThreshold {
			totalSecs += int64(gap.Seconds())
		}
	}

	return totalSecs, nil
}

// resolveContract returns the contract for taskID, resolving from git context
// when taskID is empty.
func resolveContract(taskID string) (*types.Contract, error) {
	if taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return nil, fmt.Errorf("resolve context: %w", err)
		}
		if !ctx.HasTask {
			return nil, fmt.Errorf("no task in current context")
		}
		if ctx.Contract == nil {
			return nil, fmt.Errorf("no contract for current task")
		}
		return ctx.Contract, nil
	}

	note, _, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", taskID, err)
	}
	if note.Contract == nil {
		return nil, fmt.Errorf("no contract for task %s", taskID)
	}
	return note.Contract, nil
}

// commitTimesAfter returns the author timestamps of all commits after the
// given time, in chronological order.
func commitTimesAfter(after stdtime.Time) ([]stdtime.Time, error) {
	afterStr := after.Format(stdtime.RFC3339)
	cmd := exec.Command("git", "log", "--after="+afterStr, "--format=%H %aI", "--reverse")
	out, err := cmd.Output()
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return nil, fmt.Errorf("git log: %s", string(exitErr.Stderr))
		}
		return nil, fmt.Errorf("git log: %w", err)
	}

	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	times := make([]stdtime.Time, 0, len(lines))
	for _, line := range lines {
		if line == "" {
			continue
		}
		// Line format: "<40-char-hash> <ISO8601-date>"
		idx := strings.IndexByte(line, ' ')
		if idx < 0 {
			continue
		}
		t, err := stdtime.Parse(stdtime.RFC3339, line[idx+1:])
		if err != nil {
			continue
		}
		times = append(times, t)
	}

	return times, nil
}
