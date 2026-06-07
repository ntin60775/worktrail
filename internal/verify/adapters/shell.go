package adapters

import (
	"os/exec"
	"strings"

	"worktrail/internal/types"
)

// ShellAdapter runs a shell command (passed as scope) and reports pass/fail
// based on exit code. The scope string is executed verbatim via `sh -c`.
type ShellAdapter struct{}

func (a *ShellAdapter) Name() string { return "shell" }

func (a *ShellAdapter) Run(taskID, scope, method string) (*types.VRR, error) {
	vrr := &types.VRR{
		Method: method,
		TaskID: taskID,
		Commit: headCommit(),
	}

	if scope == "" {
		vrr.Summary = types.VRRSummary{Total: 0, Passed: 0, Failed: 0}
		return vrr, nil
	}

	cmd := exec.Command("sh", "-c", scope)
	out, err := cmd.CombinedOutput()

	vrr.Summary.Total = 1
	if err != nil {
		vrr.Summary.Failed = 1
		vrr.Summary.Passed = 0
		vrr.Failures = []types.VRRFailure{{
			Name:    "shell-exit",
			Message: strings.TrimSpace(string(out)),
		}}
	} else {
		vrr.Summary.Passed = 1
		vrr.Summary.Failed = 0
	}

	return vrr, nil
}

