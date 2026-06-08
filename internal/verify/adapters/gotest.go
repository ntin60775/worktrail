package adapters

import (
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"

	"worktrail/internal/types"
)

// GoTestAdapter runs `go test ./... -json` and parses the output.
type GoTestAdapter struct{}

func (a *GoTestAdapter) Name() string { return "go_test" }

func (a *GoTestAdapter) Run(taskID, scope, method string) (*types.VRR, error) {
	args := []string{"test", "-json"}
	if scope != "" {
		args = append(args, scope)
	} else {
		args = append(args, "./...")
	}

	cmd := exec.Command("go", args...)
	out, err := cmd.Output()

	vrr := &types.VRR{
		Method:  method,
		TaskID:  taskID,
		Commit:  headCommit(),
		Summary: types.VRRSummary{},
	}

	if err != nil {
		// go test returns non-zero on failures — parse the output anyway
	}

	// Parse JSON lines: each line is a test event.
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		if line == "" {
			continue
		}
		var event struct {
			Action  string `json:"Action"`
			Test    string `json:"Test"`
			Package string `json:"Package"`
			Output  string `json:"Output"`
		}
		if err := json.Unmarshal([]byte(line), &event); err != nil {
			continue
		}

		switch event.Action {
		case "pass":
			vrr.Summary.Total++
			vrr.Summary.Passed++
		case "fail":
			if event.Test != "" {
				vrr.Summary.Total++
				vrr.Summary.Failed++
				vrr.Failures = append(vrr.Failures, types.VRRFailure{
					Name:    fmt.Sprintf("%s/%s", event.Package, event.Test),
					Message: strings.TrimSpace(event.Output),
				})
			}
		}
	}

	return vrr, nil
}
