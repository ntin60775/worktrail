// Package doctor provides system health diagnostics for worktrail.
package doctor

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Diagnose checks the health of the worktrail installation and returns
// a diagnostic report as a structured map.
func Diagnose() (map[string]interface{}, error) {
	report := map[string]interface{}{}
	allOk := true

	// 1. Git availability
	gitOk := checkGit()
	report["git_available"] = gitOk
	if !gitOk {
		allOk = false
	}

	// 2. Worktrail git-notes namespace
	notesOk := checkNotesNamespace()
	report["git_notes_namespace"] = notesOk
	if !notesOk {
		allOk = false
	}

	// 3. Hooks installed (global hooksPath set)
	hooksOk, hooksPath := checkHooksInstalled()
	report["hooks_installed"] = hooksOk
	if hooksPath != "" {
		report["hooks_path"] = hooksPath
	}
	if !hooksOk {
		allOk = false
	}

	// 4. Skill directory exists
	skillOk, skillPath := checkSkillDir()
	report["skill_installed"] = skillOk
	if skillPath != "" {
		report["skill_path"] = skillPath
	}
	if !skillOk {
		allOk = false
	}

	report["all_ok"] = allOk

	return report, nil
}

// checkGit verifies git is available in PATH.
func checkGit() bool {
	_, err := exec.LookPath("git")
	if err != nil {
		return false
	}
	cmd := exec.Command("git", "--version")
	if err := cmd.Run(); err != nil {
		return false
	}
	return true
}

// checkNotesNamespace verifies the worktrail git-notes ref exists.
func checkNotesNamespace() bool {
	cmd := exec.Command("git", "notes", "--ref", "refs/notes/worktrail", "list")
	// This command succeeds even if the ref is empty (no notes yet),
	// but fails if git-notes isn't configured or the repo is broken.
	if err := cmd.Run(); err != nil {
		return false
	}
	return true
}

// checkHooksInstalled checks if git global core.hooksPath is configured.
func checkHooksInstalled() (bool, string) {
	cmd := exec.Command("git", "config", "--global", "core.hooksPath")
	out, err := cmd.Output()
	if err != nil {
		return false, ""
	}
	path := strings.TrimSpace(string(out))
	if path == "" {
		return false, ""
	}
	// Verify the hooks directory exists
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return false, path
	}
	// Verify it contains at least one hook
	entries, err := os.ReadDir(path)
	if err != nil || len(entries) == 0 {
		return false, path
	}
	return true, path
}

// checkSkillDir checks if the worktrail skill is installed.
func checkSkillDir() (bool, string) {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return false, ""
	}
	skillPath := filepath.Join(homeDir, ".agents", "skills", "worktrail", "SKILL.md")
	if _, err := os.Stat(skillPath); os.IsNotExist(err) {
		return false, skillPath
	}
	return true, skillPath
}
