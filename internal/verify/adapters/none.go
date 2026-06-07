package adapters

import (
	"worktrail/internal/types"
)

// NoneAdapter returns an all-zero VRR for projects without verification.
type NoneAdapter struct{}

func (a *NoneAdapter) Name() string { return "none" }

func (a *NoneAdapter) Run(taskID, scope, method string) (*types.VRR, error) {
	return &types.VRR{
		Method:  method,
		TaskID:  taskID,
		Commit:  headCommit(),
		Summary: types.VRRSummary{Total: 0, Passed: 0, Failed: 0},
	}, nil
}
