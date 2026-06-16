// Package install sets up worktrail globally: git hooks, skill copy,
// binary build+install, PATH check, smoke test. Also provides uninstall and TCK conflict resolution.
package install

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
)


// TCK markers — the #XXXX suffix varies, match generically.
var (
	tckBeginRe = regexp.MustCompile(`(?m)^⟦⟦BEGIN_TASK_KNOWLEDGE_SYSTEM#[A-Z0-9]+⟧⟧`)
	tckEndRe   = regexp.MustCompile(`(?m)^⟦⟦END_TASK_KNOWLEDGE_SYSTEM#[A-Z0-9]+⟧⟧`)
)

// ─── Public API ─────────────────────────────────────────────────────────────

// Install performs a full global bootstrap: TCK conflict check, git hooks,
// skill copy, binary build+install, PATH check, smoke test.
// If dryRun is true, reports what would be done without changes.
func Install(dryRun bool) (string, error) {
	var b strings.Builder

	repoRoot, err := gitTopLevel()
	if err != nil {
		return "", fmt.Errorf("find repo root: %w", err)
	}

	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("get home dir: %w", err)
	}

	hooksDir := filepath.Join(repoRoot, "hooks")
	binDir := filepath.Join(homeDir, ".local", "bin")
	binPath := filepath.Join(binDir, "worktrail")
	scanRoot := filepath.Join(homeDir, "dev")

	// Step 0 — TCK conflict resolution
	fmt.Fprintf(&b, "## 0. TCK Conflict Check\n\n")
	tckReport, err := removeTCKIfPresent(dryRun, scanRoot)
	if err != nil {
		fmt.Fprintf(&b, "✗ TCK check failed: %v\n", err)
		return b.String(), fmt.Errorf("TCK check: %w", err)
	}
	fmt.Fprint(&b, tckReport)

	// Step 1 — Git Hooks
	fmt.Fprintf(&b, "\n## 1. Git Hooks\n\n")
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
		} else {
			fmt.Fprintf(&b, "✓ `worktrail doctor` OK\n")
		}
	}

	return b.String(), nil
}

// Uninstall removes worktrail globally: git hooks config, skill directory, and binary.
// If dryRun is true, reports what would be done without changes.
func Uninstall(dryRun bool) (string, error) {
	var b strings.Builder
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("get home dir: %w", err)
	}

	repoRoot, err := gitTopLevel()
	if err != nil {
		return "", fmt.Errorf("find repo root: %w", err)
	}
	hooksDir := filepath.Join(repoRoot, "hooks")

	// Step 1 — Hooks config
	fmt.Fprintf(&b, "## 1. Git Hooks Config\n\n")
	currentHooks, _ := gitConfigGlobal("core.hooksPath")
	if currentHooks == hooksDir || currentHooks == "" {
		if dryRun {
			fmt.Fprintf(&b, "[dry-run] Would unset `git config --global core.hooksPath`\n")
		} else if currentHooks != "" {
			if err := runCmd("git", "config", "--global", "--unset", "core.hooksPath"); err != nil {
				fmt.Fprintf(&b, "✗ failed to unset hooks path: %v\n", err)
			} else {
				fmt.Fprintf(&b, "✓ hooks config removed\n")
			}
		} else {
			fmt.Fprintf(&b, "  no hooks config to remove\n")
		}
	} else {
		fmt.Fprintf(&b, "  hooks path is `%s` (not ours), skipping\n", currentHooks)
	}

	// Step 2 — Skill directory
	fmt.Fprintf(&b, "\n## 2. Skill\n\n")
	skillDir := filepath.Join(homeDir, ".agents", "skills", "worktrail")
	if _, err := os.Stat(skillDir); os.IsNotExist(err) {
		fmt.Fprintf(&b, "  skill directory not found, skipping\n")
	} else if dryRun {
		fmt.Fprintf(&b, "[dry-run] Would remove `%s`\n", skillDir)
	} else {
		if err := os.RemoveAll(skillDir); err != nil {
			fmt.Fprintf(&b, "✗ failed to remove skill dir: %v\n", err)
		} else {
			fmt.Fprintf(&b, "✓ skill directory removed\n")
		}
	}


	// Step 3 — Binary
	fmt.Fprintf(&b, "\n## 3. Binary\n\n")
	binPath := filepath.Join(homeDir, ".local", "bin", "worktrail")
	if _, err := os.Stat(binPath); os.IsNotExist(err) {
		fmt.Fprintf(&b, "  binary not found, skipping\n")
	} else if dryRun {
		fmt.Fprintf(&b, "[dry-run] Would remove `%s`\n", binPath)
	} else {
		if err := os.Remove(binPath); err != nil {
			fmt.Fprintf(&b, "✗ failed to remove binary: %v\n", err)
		} else {
			fmt.Fprintf(&b, "✓ binary removed\n")
		}
	}


	return b.String(), nil
}

// ─── TCK conflict resolution ───────────────────────────────────────────────

// removeTCKIfPresent checks for a globally installed task-centric-knowledge
// skill and cleans it up. Also scans for project-level TCK managed blocks
// and removes them from each affected AGENTS.md.
func removeTCKIfPresent(dryRun bool, scanRoot string) (string, error) {
	var b strings.Builder
	homeDir, _ := os.UserHomeDir()
	tckSkillDir := filepath.Join(homeDir, ".agents", "skills", "task-centric-knowledge")

	tckSkillExists := false
	if fi, err := os.Stat(tckSkillDir); err == nil && fi.IsDir() {
		tckSkillExists = true
	}

	repos, err := findReposWithTCK(scanRoot)
	if err != nil {
		return "", fmt.Errorf("scan for TCK repos: %w", err)
	}

	if !tckSkillExists && len(repos) == 0 {
		fmt.Fprintf(&b, "  no task-centric-knowledge installation found\n")
		return b.String(), nil
	}

	if tckSkillExists {
		if dryRun {
			fmt.Fprintf(&b, "[dry-run] Would remove TCK skill directory: %s\n", tckSkillDir)
		} else {
			if err := os.RemoveAll(tckSkillDir); err != nil {
				return "", fmt.Errorf("remove TCK skill dir: %w", err)
			}
			fmt.Fprintf(&b, "✓ removed TCK skill directory\n")
		}
	}

	if len(repos) > 0 {
		fmt.Fprintf(&b, "  found TCK managed blocks in %d repos\n", len(repos))
		for _, repo := range repos {
			if dryRun {
				fmt.Fprintf(&b, "[dry-run] Would remove TCK block from `%s`\n", repo)
			} else {
				if err := cleanTCKBlock(repo); err != nil {
					fmt.Fprintf(&b, "  ✗ failed to clean TCK block from `%s`: %v\n", repo, err)
				} else {
					fmt.Fprintf(&b, "  ✓ cleaned TCK block from `%s`\n", repo)
				}
			}
		}
	}

	return b.String(), nil
}

// findReposWithTCK scans root for AGENTS.md files containing TCK managed blocks.
func findReposWithTCK(root string) ([]string, error) {
	cmd := exec.Command("find", root, "-maxdepth", "6", "-name", "AGENTS.md")
	out, err := cmd.Output()
	if err != nil {
		// find returns non-zero if no files found — that's ok
		if len(out) == 0 {
			return nil, nil
		}
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	var repos []string
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		data, err := os.ReadFile(line)
		if err != nil {
			continue
		}
		if tckBeginRe.Match(data) {
			repos = append(repos, line)
		}
	}
	return repos, nil
}

// cleanTCKBlock removes the TCK managed block (between BEGIN/END markers)
// from an AGENTS.md file. Returns an error if the block is malformed.
func cleanTCKBlock(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read file: %w", err)
	}

	content := string(data)
	beginLoc := tckBeginRe.FindStringIndex(content)
	if beginLoc == nil {
		return nil // no block — nothing to do
	}

	// Find matching END marker AFTER the BEGIN marker.
	rest := content[beginLoc[1]:]
	endLoc := tckEndRe.FindStringIndex(rest)
	if endLoc == nil {
		return fmt.Errorf("TCK BEGIN marker found but no END marker — block is corrupted")
	}

	// Remove the block: everything from BEGIN to end of END line.
	// Consume exactly one trailing newline after the END marker (the line break).
	endPos := beginLoc[1] + endLoc[1]
	suffix := content[endPos:]
	if len(suffix) > 0 && suffix[0] == '\n' {
		suffix = suffix[1:]
	}
	cleaned := content[:beginLoc[0]] + suffix

	// If the file is now empty or whitespace-only, remove it.
	trimmed := strings.TrimSpace(cleaned)
	if trimmed == "" {
		return os.Remove(path)
	}

	return os.WriteFile(path, []byte(strings.TrimRight(cleaned, "\n")+"\n"), 0o644)
}


// ─── Helpers ────────────────────────────────────────────────────────────────

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
	out, err := exec.Command("git", "rev-parse", "--show-toplevel").Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

// gitConfigGlobal returns the value of a global git config key, or "" if unset.
func gitConfigGlobal(key string) (string, error) {
	cmd := exec.Command("git", "config", "--global", "--get", key)
	out, err := cmd.Output()
	if err != nil {
		return "", nil // unset = empty, not an error
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

