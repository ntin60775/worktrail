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

// ErrInvalidStatus is returned for invalid status transitions.
var ErrInvalidStatus = errors.New("invalid status transition")

// allowedTransitions defines valid status transitions.
// Missing transitions are rejected.
var allowedTransitions = map[string]map[string]bool{
	"draft":     {"active": true, "cancelled": true},
	"active":    {"blocked": true, "review": true, "done": true, "cancelled": true},
	"blocked":   {"active": true, "cancelled": true},
	"review":    {"done": true, "active": true, "cancelled": true},
	"done":      {"active": true},     // reopen
	"cancelled": {"draft": true},       // reactivate
}

// validStatuses for initial validation.
var validStatuses = map[string]bool{
	"draft": true, "active": true, "blocked": true,
	"review": true, "done": true, "cancelled": true,
}

// ValidateTransition checks if moving from oldStatus to newStatus is allowed.
func ValidateTransition(oldStatus, newStatus string) error {
	if !validStatuses[newStatus] {
		return fmt.Errorf("%w: unknown status %q", ErrInvalidStatus, newStatus)
	}
	if oldStatus == "" {
		return nil // initial set
	}
	if oldStatus == newStatus {
		return nil
	}
	if allowed, ok := allowedTransitions[oldStatus]; ok && allowed[newStatus] {
		return nil
	}
	return fmt.Errorf("%w: cannot transition %s → %s", ErrInvalidStatus, oldStatus, newStatus)
}

// Init creates a new contract for the given task.
func Init(taskID, name, scope string, relatesTo []string) (*types.Contract, error) {
	// Check if contract already exists via tag
	tags, err := gitnotes.ListTags()
	if err != nil {
		return nil, fmt.Errorf("list tags: %w", err)
	}
	for _, tag := range tags {
		anchor, err := gitnotes.ResolveTag(tag)
		if err != nil {
			continue
		}
		note, err := gitnotes.Read(anchor)
		if err != nil {
			continue
		}
		if note.Contract != nil && note.Contract.TaskID == taskID {
			return nil, ErrContractExists
		}
	}

	// Create unique anchor commit and tag
	anchor, err := gitnotes.CreateAnchor(taskID)
	if err != nil {
		return nil, fmt.Errorf("create anchor: %w", err)
	}

	branch, err := gitnotes.CurrentBranch()
	if err != nil {
		return nil, fmt.Errorf("get branch: %w", err)
	}

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
		RelatesTo: relatesTo,
	}

	note := &types.TaskNote{Contract: &contract}
	if err := gitnotes.Write(anchor, note); err != nil {
		return nil, fmt.Errorf("write contract: %w", err)
	}

	return &contract, nil
}

// Show returns the contract for the given task.
func Show(taskID string) (*types.Contract, error) {
	if taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return nil, err
		}
		if !ctx.HasTask {
			return nil, ErrNoContract
		}
		taskID = ctx.TaskID
	}

	note, _, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", taskID, err)
	}
	if note.Contract == nil {
		return nil, ErrNoContract
	}
	return note.Contract, nil
}

// Update modifies an existing contract's fields.
func Update(taskID string, updates map[string]string, criteriaFile, verifyFile string, relatesTo []string) (*types.Contract, error) {
	note, anchor, err := gitnotes.ReadByTask(taskID)
	if err != nil {
		return nil, fmt.Errorf("read task %s: %w", taskID, err)
	}
	if note.Contract == nil {
		return nil, ErrNoContract
	}

	c := note.Contract

	// Validate status transition if status is being changed
	if newStatus, ok := updates["status"]; ok {
		if err := ValidateTransition(c.Status, newStatus); err != nil {
			return nil, err
		}
		c.Status = newStatus
	}

	if v, ok := updates["name"]; ok {
		c.Name = v
	}
	if v, ok := updates["summary"]; ok {
		c.Summary = v
	}
	if v, ok := updates["scope"]; ok {
		c.Scope = v
	}

	// Load criteria from file
	if criteriaFile != "" {
		data, err := os.ReadFile(criteriaFile)
		if err != nil {
			return nil, fmt.Errorf("read criteria file: %w", err)
		}
		var criteria []types.SuccessCriterion
		if err := json.Unmarshal(data, &criteria); err != nil {
			return nil, fmt.Errorf("parse criteria: %w", err)
		}
		c.SuccessCriteria = criteria
	}

	// Load verification methods from file
	if verifyFile != "" {
		data, err := os.ReadFile(verifyFile)
		if err != nil {
			return nil, fmt.Errorf("read verify file: %w", err)
		}
		var methods []types.VerificationMethod
		if err := json.Unmarshal(data, &methods); err != nil {
			return nil, fmt.Errorf("parse verification: %w", err)
		}
		c.Verification = methods
	}


	if relatesTo != nil {
		c.RelatesTo = relatesTo
	}
	c.UpdatedAt = time.Now()

	note.Contract = c
	if err := gitnotes.Write(anchor, note); err != nil {
		return nil, fmt.Errorf("write contract: %w", err)
	}

	return c, nil
}
