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

// ─── VRR ────────────────────────────────────────────────────────────────────

// VRR is a single verification run record.
type VRR struct {
	Run            int            `json:"run"`
	Method         string         `json:"method"`
	Timestamp      time.Time      `json:"timestamp"`
	TaskID         string         `json:"task_id"`
	Commit         string         `json:"commit,omitempty"`
	Summary        VRRSummary     `json:"summary"`
	Failures       []VRRFailure   `json:"failures"`
	Regressions    []string       `json:"regressions,omitempty"`
	FixedSinceLast []string       `json:"fixed_since_last,omitempty"`
}

// VRRSummary is the aggregate pass/fail count.
type VRRSummary struct {
	Total  int `json:"total"`
	Passed int `json:"passed"`
	Failed int `json:"failed"`
}

// VRRFailure describes a single failing check.
type VRRFailure struct {
	Name    string `json:"name"`
	Message string `json:"message"`
	File    string `json:"file,omitempty"`
	Line    int    `json:"line,omitempty"`
}

// ─── Review Package ─────────────────────────────────────────────────────────

// ReviewPackage is assembled at finalize — contains everything for review.
type ReviewPackage struct {
	TaskID              string             `json:"task_id"`
	Status              string             `json:"status"` // always "review"
	Contract            Contract           `json:"contract"`
	VerificationSummary VerificationSummary `json:"verification_summary"`
	Decisions           []Decision         `json:"decisions,omitempty"`
	Specs               []Spec             `json:"specs,omitempty"`
	Boundaries          Boundaries         `json:"boundaries,omitempty"`
}

// VerificationSummary aggregates verification history and final result.
type VerificationSummary struct {
	TotalRuns int    `json:"total_runs"`
	FinalRun  VRR    `json:"final_run"`
	VRRLog    string `json:"vrr_log,omitempty"` // path to JSONL log
}

// Boundaries are the scope of changes in a task.
type Boundaries struct {
	ChangedFiles        []string `json:"changed_files"`
	UntouchedByContract string   `json:"untouched_by_contract,omitempty"`
	DependenciesChecked string   `json:"dependencies_checked,omitempty"`
}

// ─── Review Result ──────────────────────────────────────────────────────────

// ReviewResult is the verdict from the expert review panel.
type ReviewResult struct {
	TaskID    string         `json:"task_id"`
	Verdict   string         `json:"verdict"` // accepted | rejected
	Timestamp time.Time      `json:"timestamp"`
	Experts   []ExpertResult `json:"experts"`
	Report    string         `json:"report,omitempty"` // path to markdown report
}

// ExpertResult is the verdict from a single expert.
type ExpertResult struct {
	Expert   string          `json:"expert"`   // contract-auditor, code-auditor, ...
	Verdict  string          `json:"verdict"`  // pass | fail
	Blockers []ExpertBlocker `json:"blockers,omitempty"`
	Warnings []ExpertWarning `json:"warnings,omitempty"`
	Details  []ExpertDetail  `json:"details,omitempty"`
}

// ExpertBlocker is a blocking issue that must be fixed.
type ExpertBlocker struct {
	ID       string `json:"id"`
	Title    string `json:"title"`
	Problem  string `json:"problem"`
	Fix      string `json:"fix,omitempty"`
	Location string `json:"location,omitempty"`
}

// ExpertWarning is a non-blocking concern.
type ExpertWarning struct {
	ID      string `json:"id"`
	Title   string `json:"title"`
	Problem string `json:"problem"`
}

// ExpertDetail is a per-criterion check result.
type ExpertDetail struct {
	CriteriaID string `json:"criteria_id"`
	Status     string `json:"status"`   // covered | missing | partial
	Evidence   string `json:"evidence,omitempty"`
}

// ─── TaskNote (aggregate git-note) ──────────────────────────────────────────

// TaskNote is the aggregate structure stored in a single git-note on the anchor commit.
type TaskNote struct {
	Contract      *Contract      `json:"contract,omitempty"`
	Decisions     []Decision     `json:"decisions,omitempty"`
	Specs         []Spec         `json:"specs,omitempty"`
	Progress      []Progress     `json:"progress,omitempty"`
	ReviewPackage *ReviewPackage `json:"review_package,omitempty"`
	ReviewResult  *ReviewResult  `json:"review_result,omitempty"`
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

// ─── ReviewJob (for review run command) ─────────────────────────────────────

// ReviewJob is one expert assignment for parallel review.
type ReviewJob struct {
	Expert         string          `json:"expert"`
	TaskID         string          `json:"task_id"`
	Profile        string          `json:"profile"`
	Prompt         string          `json:"prompt"`
	Artifacts      ReviewArtifacts `json:"artifacts"`
	ExpectedOutput ExpectedOutput  `json:"expected_output"`
}

// ReviewArtifacts are the data passed to an expert.
type ReviewArtifacts struct {
	Contract    Contract    `json:"contract"`
	Specs       []Spec      `json:"specs,omitempty"`
	Boundaries  Boundaries  `json:"boundaries"`
	VRRSummary  VRRSummary  `json:"vrr_summary"`
}

// ExpectedOutput is the schema an expert sub-agent must return.
type ExpectedOutput struct {
	Verdict  string          `json:"verdict"` // pass|fail
	Blockers []ExpertBlocker `json:"blockers,omitempty"`
	Warnings []ExpertWarning `json:"warnings,omitempty"`
	Details  []ExpertDetail  `json:"details,omitempty"`
}

// ─── Profile ────────────────────────────────────────────────────────────────

// Profile defines the expert panel for a project type.
type Profile struct {
	Name     string   `json:"name"`
	Experts  []string `json:"experts"`
}

// Valid profiles.
var Profiles = map[string]Profile{
	"code": {
		Name: "code",
		Experts: []string{
			"contract-auditor",
			"code-auditor",
			"decisions-auditor",
			"boundaries-auditor",
			"vrr-auditor",
		},
	},
	"1c": {
		Name: "1c",
		Experts: []string{
			"contract-auditor",
			"code-auditor",
			"metadata-auditor",
			"decisions-auditor",
			"boundaries-auditor",
		},
	},
	"research": {
		Name: "research",
		Experts: []string{
			"contract-auditor",
			"sources-auditor",
		},
	},
	"generic": {
		Name: "generic",
		Experts: []string{
			"contract-auditor",
		},
	},
}
