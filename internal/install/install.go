// Package install sets up worktrail in a git repository environment —
// global hooks and skill directory.
package install

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Install configures git global hooks path and copies the skill definition.
// If dryRun is true, reports what would be done without making changes.
func Install(dryRun bool) (string, error) {
	var b strings.Builder

	// 1. Find repository root
	repoRoot, err := gitTopLevel()
	if err != nil {
		return "", fmt.Errorf("find repo root: %w", err)
	}

	hooksDir := filepath.Join(repoRoot, "hooks")

	// Check hooks directory exists
	if _, err := os.Stat(hooksDir); os.IsNotExist(err) {
		return "", fmt.Errorf("hooks directory not found: %s", hooksDir)
	}

	// 2. Set git global hooks path
	fmt.Fprintf(&b, "## Git Hooks\n\n")
	configCmd := fmt.Sprintf("git config --global core.hooksPath %s", hooksDir)
	if dryRun {
		fmt.Fprintf(&b, "[dry-run] Would run: `%s`\n", configCmd)
	} else {
		if err := runGit("config", "--global", "core.hooksPath", hooksDir); err != nil {
			return "", fmt.Errorf("set hooks path: %w", err)
		}
		fmt.Fprintf(&b, "✓ Set git global hooks path to `%s`\n", hooksDir)
	}

	// 2b. Ensure hooks are executable
	for _, name := range []string{"post-commit", "post-checkout", "prepare-commit-msg"} {
		hookPath := filepath.Join(hooksDir, name)
		if fi, err := os.Stat(hookPath); err == nil && !fi.IsDir() {
			if err := os.Chmod(hookPath, 0o755); err != nil {
				return "", fmt.Errorf("chmod %s: %w", name, err)
			}
		}
	}

	// 3. Copy SKILL.md to ~/.agents/skills/worktrail/
	fmt.Fprintf(&b, "\n## Skill\n\n")
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("get home dir: %w", err)
	}
	skillDir := filepath.Join(homeDir, ".agents", "skills", "worktrail")
	skillPath := filepath.Join(skillDir, "SKILL.md")
	srcPath := filepath.Join(repoRoot, "SKILL.md")

	if _, err := os.Stat(srcPath); os.IsNotExist(err) {
		return "", fmt.Errorf("SKILL.md not found at %s", srcPath)
	}

	if dryRun {
		fmt.Fprintf(&b, "[dry-run] Would create directory `%s`\n", skillDir)
		fmt.Fprintf(&b, "[dry-run] Would copy `%s` → `%s`\n", srcPath, skillPath)
	} else {
		if err := os.MkdirAll(skillDir, 0o755); err != nil {
			return "", fmt.Errorf("create skill dir: %w", err)
		}
		data, err := os.ReadFile(srcPath)
		if err != nil {
			return "", fmt.Errorf("read SKILL.md: %w", err)
		}
		if err := os.WriteFile(skillPath, data, 0o644); err != nil {
			return "", fmt.Errorf("write SKILL.md: %w", err)
		}
		fmt.Fprintf(&b, "✓ Copied SKILL.md to `%s`\n", skillPath)
	}

	return b.String(), nil
}

// gitTopLevel returns the root directory of the current git repository.
func gitTopLevel() (string, error) {
	cmd := exec.Command("git", "rev-parse", "--show-toplevel")
	out, err := cmd.Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

// runGit runs a git command and returns any error.
func runGit(args ...string) error {
	cmd := exec.Command("git", args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}
