// Package install sets up worktrail in a git repository environment —
// global hooks, skill directory, binary, PATH check, and smoke test.
package install

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Install configures git global hooks path, copies the skill definition,
// builds and installs the binary, checks PATH, and smoke-tests the result.
// If dryRun is true, reports what would be done without making changes.
func Install(dryRun bool) (string, error) {
	var b strings.Builder

	// 1. Find repository root
	repoRoot, err := gitTopLevel()
	if err != nil {
		return "", fmt.Errorf("find repo root: %w", err)
	}

	hooksDir := filepath.Join(repoRoot, "hooks")
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("get home dir: %w", err)
	}
	binDir := filepath.Join(homeDir, ".local", "bin")
	binPath := filepath.Join(binDir, "worktrail")

	// Step 1 — Hooks
	fmt.Fprintf(&b, "## 1. Git Hooks\n\n")
	if _, err := os.Stat(hooksDir); os.IsNotExist(err) {
		fmt.Fprintf(&b, "✗ hooks directory not found: %s\n", hooksDir)
		return b.String(), fmt.Errorf("hooks directory not found: %s", hooksDir)
	}
	if dryRun {
		fmt.Fprintf(&b, "[dry-run] Would set `git config --global core.hooksPath %s`\n", hooksDir)
		fmt.Fprintf(&b, "[dry-run] Would chmod +x hooks/*\n")
	} else {
		if err := runCmd("git", "config", "--global", "core.hooksPath", hooksDir); err != nil {
			fmt.Fprintf(&b, "✗ failed to set hooks path: %v\n", err)
			return b.String(), fmt.Errorf("set hooks path: %w", err)
		}
		for _, name := range []string{"post-commit", "post-checkout", "prepare-commit-msg"} {
			hookPath := filepath.Join(hooksDir, name)
			if fi, err := os.Stat(hookPath); err == nil && !fi.IsDir() {
				if err := os.Chmod(hookPath, 0o755); err != nil {
					fmt.Fprintf(&b, "✗ failed to chmod %s: %v\n", name, err)
					return b.String(), fmt.Errorf("chmod %s: %w", name, err)
				}
			}
		}
		fmt.Fprintf(&b, "✓ hooks configured at `%s`\n", hooksDir)
	}

	// Step 2 — Skill
	fmt.Fprintf(&b, "\n## 2. Skill\n\n")
	skillDir := filepath.Join(homeDir, ".agents", "skills", "worktrail")
	skillPath := filepath.Join(skillDir, "SKILL.md")
	srcPath := filepath.Join(repoRoot, "SKILL.md")

	if _, err := os.Stat(srcPath); os.IsNotExist(err) {
		fmt.Fprintf(&b, "✗ SKILL.md not found at %s\n", srcPath)
		return b.String(), fmt.Errorf("SKILL.md not found at %s", srcPath)
	}
	if dryRun {
		fmt.Fprintf(&b, "[dry-run] Would copy `%s` → `%s`\n", srcPath, skillPath)
	} else {
		if err := os.MkdirAll(skillDir, 0o755); err != nil {
			fmt.Fprintf(&b, "✗ failed to create skill dir: %v\n", err)
			return b.String(), fmt.Errorf("create skill dir: %w", err)
		}
		data, err := os.ReadFile(srcPath)
		if err != nil {
			fmt.Fprintf(&b, "✗ failed to read SKILL.md: %v\n", err)
			return b.String(), fmt.Errorf("read SKILL.md: %w", err)
		}
		if err := os.WriteFile(skillPath, data, 0o644); err != nil {
			fmt.Fprintf(&b, "✗ failed to write SKILL.md: %v\n", err)
			return b.String(), fmt.Errorf("write SKILL.md: %w", err)
		}
		fmt.Fprintf(&b, "✓ skill installed to `%s`\n", skillPath)
	}

	// Step 3 — Binary (build + install)
	fmt.Fprintf(&b, "\n## 3. Binary\n\n")
	builtBinary := filepath.Join(repoRoot, "worktrail")

	if dryRun {
		fmt.Fprintf(&b, "[dry-run] Would ensure binary at `%s` (build if missing)\n", builtBinary)
		fmt.Fprintf(&b, "[dry-run] Would copy `%s` → `%s`\n", builtBinary, binPath)
	} else {
		// Auto-build if missing
		if _, err := os.Stat(builtBinary); os.IsNotExist(err) {
			fmt.Fprintf(&b, "  building binary (go build)...\n")
			buildCmd := exec.Command("go", "build", "-o", builtBinary, filepath.Join(repoRoot, "cmd", "worktrail"))
			buildCmd.Dir = repoRoot
			out, buildErr := buildCmd.CombinedOutput()
			if buildErr != nil {
				fmt.Fprintf(&b, "✗ build failed: %v\n%s\n", buildErr, string(out))
				return b.String(), fmt.Errorf("go build: %w", buildErr)
			}
			fmt.Fprintf(&b, "  build succeeded\n")
		}

		if err := os.MkdirAll(binDir, 0o755); err != nil {
			fmt.Fprintf(&b, "✗ failed to create bin dir: %v\n", err)
			return b.String(), fmt.Errorf("create bin dir: %w", err)
		}
		data, err := os.ReadFile(builtBinary)
		if err != nil {
			fmt.Fprintf(&b, "✗ failed to read binary: %v\n", err)
			return b.String(), fmt.Errorf("read binary: %w", err)
		}
		if err := os.WriteFile(binPath, data, 0o755); err != nil {
			fmt.Fprintf(&b, "✗ failed to write binary: %v\n", err)
			return b.String(), fmt.Errorf("write binary: %w", err)
		}
		fmt.Fprintf(&b, "✓ binary installed to `%s`\n", binPath)
	}

	// Step 4 — PATH check
	fmt.Fprintf(&b, "\n## 4. PATH\n\n")
	if pathContains(binDir) {
		fmt.Fprintf(&b, "✓ `%s` is in PATH\n", binDir)
	} else {
		fmt.Fprintf(&b, "✗ `%s` is NOT in PATH — add it to your shell profile\n", binDir)
	}

	// Step 5 — Smoke test
	fmt.Fprintf(&b, "\n## 5. Smoke Test\n\n")
	if dryRun {
		fmt.Fprintf(&b, "[dry-run] Would run `worktrail doctor`\n")
	} else {
		docCmd := exec.Command(binPath, "doctor")
		out, docErr := docCmd.CombinedOutput()
		if docErr != nil {
			fmt.Fprintf(&b, "✗ smoke test failed: %v\n%s\n", docErr, string(out))
			// Non-fatal: report but don't abort install
		} else {
			fmt.Fprintf(&b, "✓ `worktrail doctor` OK\n")
		}
	}

	return b.String(), nil
}

// pathContains reports whether dir is present in the PATH environment variable.
func pathContains(dir string) bool {
	for _, p := range strings.Split(os.Getenv("PATH"), string(os.PathListSeparator)) {
		if filepath.Clean(p) == filepath.Clean(dir) {
			return true
		}
	}
	return false
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

// runCmd runs a command and returns any error.
func runCmd(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}
