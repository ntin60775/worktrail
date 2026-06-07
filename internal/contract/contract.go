// Package contract provides contract operations: init, show, update.
// Contracts are stored as git-notes on anchor commits.
package contract

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"time"

	"worktrail/internal/context"
	"worktrail/internal/gitnotes"
	"worktrail/internal/types"
)

// ErrContractExists is returned when Init is called for a task that already has a contract.
var ErrContractExists = errors.New("contract already exists for this task")

// ErrNoContract is returned when a contract lookup finds no contract.
var ErrNoContract = errors.New("no contract found")

// Init creates a new contract for the given task.
// Returns an error if a contract already exists for taskID.
func Init(taskID, name, scope string) (*types.Contract, error) {
	// Check if contract already exists
	anchor, err := gitnotes.AnchorCommit(taskID)
	if err != nil {
		return nil, fmt.Errorf("anchor commit: %w", err)
	}
	existing, err := gitnotes.Read(anchor)
	if err != nil {
		return nil, fmt.Errorf("read existing note: %w", err)
	}
	if existing.Contract != nil {
		return nil, ErrContractExists
	}

	// Get HEAD and current branch
	head, err := gitnotes.HEAD()
	if err != nil {
		return nil, fmt.Errorf("get HEAD: %w", err)
	}
	branch, err := gitnotes.CurrentBranch()
	if err != nil {
		return nil, fmt.Errorf("get branch: %w", err)
	}

	// Create contract
	now := time.Now()
	contract := types.Contract{
		TaskID:    taskID,
		Name:      name,
		Summary:   name,
		Scope:     scope,
		Status:    "draft",
		CreatedAt: now,
		UpdatedAt: now,
		Branch:    branch,
	}

	// Create anchor tag
	if err := gitnotes.CreateAnchor(taskID, head); err != nil {
		return nil, fmt.Errorf("create anchor: %w", err)
	}

	// Write contract to git-note
	note, err := gitnotes.Read(head)
	if err != nil {
		return nil, fmt.Errorf("read note for write: %w", err)
	}
	note.Contract = &contract
	if err := gitnotes.Write(head, note); err != nil {
		return nil, fmt.Errorf("write contract: %w", err)
	}

	return &contract, nil
}

// Show returns the contract for the given task.
// If taskID is empty, resolves the current task from git context.
func Show(taskID string) (*types.Contract, error) {
	if taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return nil, fmt.Errorf("resolve context: %w", err)
		}
		if !ctx.HasTask {
			return nil, errors.New("no task in current context")
		}
		taskID = ctx.TaskID
	}

	note, _, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return nil, fmt.Errorf("read task: %w", err)
	}
	if note.Contract == nil {
		return nil, ErrNoContract
	}
	return note.Contract, nil
}

// Update modifies an existing contract's fields.
// String fields are updated from the updates map (keys: status, name, summary, scope).
// criteriaFile and verifyFile, when non-empty, are paths to JSON files
// containing []SuccessCriterion and []VerificationMethod respectively.
func Update(taskID string, updates map[string]string, criteriaFile, verifyFile string) (*types.Contract, error) {
	note, anchor, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return nil, fmt.Errorf("read task: %w", err)
	}
	if note.Contract == nil {
		return nil, ErrNoContract
	}
	contract := *note.Contract // shallow copy

	// Apply string updates
	if v, ok := updates["status"]; ok {
		contract.Status = v
	}
	if v, ok := updates["name"]; ok {
		contract.Name = v
	}
	if v, ok := updates["summary"]; ok {
		contract.Summary = v
	}
	if v, ok := updates["scope"]; ok {
		contract.Scope = v
	}

	// Replace success criteria from file
	if criteriaFile != "" {
		data, err := os.ReadFile(criteriaFile)
		if err != nil {
			return nil, fmt.Errorf("read criteria file: %w", err)
		}
		var criteria []types.SuccessCriterion
		if err := json.Unmarshal(data, &criteria); err != nil {
			return nil, fmt.Errorf("unmarshal criteria: %w", err)
		}
		contract.SuccessCriteria = criteria
	}

	// Replace verification methods from file
	if verifyFile != "" {
		data, err := os.ReadFile(verifyFile)
		if err != nil {
			return nil, fmt.Errorf("read verify file: %w", err)
		}
		var methods []types.VerificationMethod
		if err := json.Unmarshal(data, &methods); err != nil {
			return nil, fmt.Errorf("unmarshal verification: %w", err)
		}
		contract.Verification = methods
	}

	contract.UpdatedAt = time.Now()

	// Write back
	note.Contract = &contract
	if err := gitnotes.Write(anchor, note); err != nil {
		return nil, fmt.Errorf("write contract: %w", err)
	}

	return &contract, nil
}
