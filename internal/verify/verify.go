// Package verify defines the verification adapter interface and orchestrates
// verification runs for worktrail v2 tasks. Verification results are stored as
// JSONL in .worktrail/<taskID>/vrr.jsonl.
package verify

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"worktrail/internal/types"
)

// Adapter runs a verification method against a task scope and returns a VRR.
type Adapter interface {
	// Run executes verification. taskID is the worktrail task, scope is the
	// filesystem path or command string to verify, method is the verification
	// method name (may differ from the adapter's registered name).
	Run(taskID, scope, method string) (*types.VRR, error)

	// Name returns the adapter's registered name.
	Name() string
}

// Adapters maps method names to their adapter implementations.
var Adapters = map[string]Adapter{}

// Register adds an adapter to the global registry.
func Register(a Adapter) {
	Adapters[a.Name()] = a
}

// ─── Public API ──────────────────────────────────────────────────────────────

// RunVerification runs the named adapter, appends the VRR to the JSONL log,
// and returns the result.
func RunVerification(method, taskID, scope string) (*types.VRR, error) {
	a, ok := Adapters[method]
	if !ok {
		return nil, fmt.Errorf("unknown verification method: %q", method)
	}

	vrr, err := a.Run(taskID, scope, method)
	if err != nil {
		return nil, fmt.Errorf("%s verification: %w", method, err)
	}

	if err := appendVRR(taskID, scope, vrr); err != nil {
		return nil, fmt.Errorf("write VRR log: %w", err)
	}

	return vrr, nil
}

// ReadVRRLog reads all VRR entries from the JSONL log for a task.
func ReadVRRLog(taskID string) ([]types.VRR, error) {
	return readVRRLog(taskID, "")
}

// ReadVRRLogScoped reads all VRR entries for a task within a scope directory.
func ReadVRRLogScoped(taskID, scope string) ([]types.VRR, error) {
	return readVRRLog(taskID, scope)
}

// GetLastVRR returns the most recent VRR entry for a task.
func GetLastVRR(taskID string) (*types.VRR, error) {
	return getLastVRR(taskID, "")
}

// GetLastVRRScoped returns the most recent VRR entry for a task within a scope.
func GetLastVRRScoped(taskID, scope string) (*types.VRR, error) {
	return getLastVRR(taskID, scope)
}

// ─── Path helpers ────────────────────────────────────────────────────────────

// vrrPath returns the JSONL path: .worktrail/<taskID>/vrr.jsonl.
// When scope is non-empty, the path is resolved relative to that directory.
func vrrPath(taskID, scope string) string {
	base := "."
	if scope != "" {
		base = scope
	}
	return filepath.Join(base, ".worktrail", taskID, "vrr.jsonl")
}

// ─── JSONL I/O ───────────────────────────────────────────────────────────────

func appendVRR(taskID, scope string, vrr *types.VRR) error {
	path := vrrPath(taskID, scope)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}

	// Determine run number from existing log.
	existing, _ := readVRRLog(taskID, scope)
	vrr.Run = len(existing) + 1
	vrr.Timestamp = time.Now()

	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()

	line, err := json.Marshal(vrr)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintln(f, string(line))
	return err
}

func readVRRLog(taskID, scope string) ([]types.VRR, error) {
	path := vrrPath(taskID, scope)
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()

	var out []types.VRR
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var v types.VRR
		if err := json.Unmarshal(line, &v); err != nil {
			continue
		}
		out = append(out, v)
	}
	return out, scanner.Err()
}

func getLastVRR(taskID, scope string) (*types.VRR, error) {
	entries, err := readVRRLog(taskID, scope)
	if err != nil {
		return nil, err
	}
	if len(entries) == 0 {
		return nil, nil
	}
	last := entries[len(entries)-1]
	return &last, nil
}

