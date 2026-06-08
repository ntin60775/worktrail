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

	// 5. Binary in PATH
	binPath, binOk := checkBinaryPath()
	report["binary_in_path"] = binOk
	if binPath != "" {
		report["binary_path"] = binPath
	}
	if !binOk {
		allOk = false
	}

	// 6. ~/.local/bin in PATH
	localBinOk := checkLocalBinInPath()
	report["local_bin_in_path"] = localBinOk
	if !localBinOk {
		allOk = false
	}

	// 7. Binary installed and executable
	binInstalled, installedPath := checkBinaryInstalled()
	report["binary_installed"] = binInstalled
	if installedPath != "" {
		report["binary_install_path"] = installedPath
	}
	if !binInstalled {
		allOk = false
	}

	report["all_ok"] = allOk
	return report, nil
}

func checkGit() bool {
	_, err := exec.LookPath("git")
	if err != nil {
		return false
	}
	return exec.Command("git", "--version").Run() == nil
}

func checkNotesNamespace() bool {
	return exec.Command("git", "notes", "--ref", "refs/notes/worktrail", "list").Run() == nil
}

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
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return false, path
	}
	entries, err := os.ReadDir(path)
	if err != nil || len(entries) == 0 {
		return false, path
	}
	return true, path
}

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

func checkBinaryPath() (string, bool) {
	p, err := exec.LookPath("worktrail")
	if err != nil {
		return "", false
	}
	return p, true
}

func checkLocalBinInPath() bool {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return false
	}
	binDir := filepath.Join(homeDir, ".local", "bin")
	for _, p := range strings.Split(os.Getenv("PATH"), ":") {
		if p == binDir {
			return true
		}
	}
	return false
}

func checkBinaryInstalled() (bool, string) {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return false, ""
	}
	binPath := filepath.Join(homeDir, ".local", "bin", "worktrail")
	info, err := os.Stat(binPath)
	if err != nil {
		return false, binPath
	}
	return info.Mode()&0111 != 0, binPath
}
