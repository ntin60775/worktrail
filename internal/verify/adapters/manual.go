package adapters

import (
	"worktrail/internal/types"
)

// ManualAdapter returns a zero-count VRR to signal that manual verification
// is needed. The caller inspects Summary.Total == 0 to detect this case.
type ManualAdapter struct{}

func (a *ManualAdapter) Name() string { return "manual" }

func (a *ManualAdapter) Run(taskID, scope, method string) (*types.VRR, error) {
	return &types.VRR{
		Method:  method,
		TaskID:  taskID,
		Commit:  headCommit(),
		Summary: types.VRRSummary{Total: 0, Passed: 0, Failed: 0},
	}, nil
}
