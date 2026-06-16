// Package types defines the canonical data structures for worktrail v2.
// All types map 1:1 to the JSON schemas in references/schemas/.
package types

import "time"

// ─── Contract ───────────────────────────────────────────────────────────────

// Contract is the task contract — what to do, boundaries, success criteria,
// verification methods. Stored as git-note refs/notes/worktrail.
type Contract struct {
	TaskID          string               `json:"task_id"`
	Name            string               `json:"name,omitempty"`
	Summary         string               `json:"summary"`
	Scope           string               `json:"scope,omitempty"`
	Status          string               `json:"status,omitempty"` // draft|active|blocked|review|done|cancelled
	CreatedAt       time.Time            `json:"created_at"`
	UpdatedAt       time.Time            `json:"updated_at,omitempty"`
	Branch          string               `json:"branch,omitempty"`
	RelatesTo       []string             `json:"relates_to,omitempty"`
	SuccessCriteria []SuccessCriterion   `json:"success_criteria,omitempty"`
	Verification    []VerificationMethod `json:"verification,omitempty"`
}

// SuccessCriterion is a verifiable statement that must be true for task completion.
type SuccessCriterion struct {
	ID        string   `json:"id"`
	Statement string   `json:"statement"`
	CoveredBy []string `json:"covered_by,omitempty"`
}

// VerificationMethod defines how to verify success criteria.
type VerificationMethod struct {
	Method  string   `json:"method"`            // pytest, 1c_test, manual, shell, none
	Label   string   `json:"label,omitempty"`   // human-readable label
	Scope   string   `json:"scope,omitempty"`   // files/dirs to check
	MapsTo  []string `json:"maps_to,omitempty"` // criterion IDs covered
}

// ─── Progress ───────────────────────────────────────────────────────────────

// Progress is a lightweight chronological record of work done.
type Progress struct {
	TaskID    string    `json:"task_id"`
	Timestamp time.Time `json:"timestamp"`
	Summary   string    `json:"summary"`
	Commit    string    `json:"commit,omitempty"` // git commit hash
}

// ─── Decision ───────────────────────────────────────────────────────────────

// Decision records an architectural or project decision.
type Decision struct {
	ID           string    `json:"id"`
	TaskID       string    `json:"task_id"`
	Title        string    `json:"title"`
	Rationale    string    `json:"rationale"`
	Alternatives []string  `json:"alternatives,omitempty"`
	File         string    `json:"file,omitempty"`
	Lines        string    `json:"lines,omitempty"` // e.g. "1-20"
	CreatedAt    time.Time `json:"created_at"`
}

// ─── Spec ───────────────────────────────────────────────────────────────────

// Spec is a set of invariants attached to a scope or file.
type Spec struct {
	ID         string    `json:"id"`
	TaskID     string    `json:"task_id"`
	Scope      string    `json:"scope"`
	Invariants []string  `json:"invariants"`
	File       string    `json:"file,omitempty"`
	Lines      string    `json:"lines,omitempty"`
	CreatedAt  time.Time `json:"created_at"`
}

// ─── TaskNote (aggregate git-note) ──────────────────────────────────────────

// TaskNote is the aggregate structure stored in a single git-note on the anchor commit.
type TaskNote struct {
	Contract  *Contract  `json:"contract,omitempty"`
	Decisions []Decision `json:"decisions,omitempty"`
	Specs     []Spec     `json:"specs,omitempty"`
	Progress  []Progress `json:"progress,omitempty"`
}

// ─── Context ────────────────────────────────────────────────────────────────

// ContextOutput is the JSON output of the context command.
type ContextOutput struct {
	TaskID       string    `json:"task_id"`
	Name         string    `json:"name"`
	Status       string    `json:"status"`
	Branch       string    `json:"branch"`
	AnchorCommit string    `json:"anchor_commit"`
	Contract     *Contract `json:"contract,omitempty"`
	HasContract  bool      `json:"has_contract"`
	HasTask      bool      `json:"has_task"`
}

// ─── TaskSummary (for list command) ─────────────────────────────────────────

// TaskSummary is a lightweight listing entry.
type TaskSummary struct {
	TaskID       string `json:"task_id"`
	Name         string `json:"name"`
	Status       string `json:"status"`
	Branch       string `json:"branch"`
	AnchorCommit string `json:"anchor_commit"`
}
