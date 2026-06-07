// Package archive provides migration and reading support for
// task-centric-knowledge (TCK) v1 format.
package archive

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// ReadTCK reads a TCK directory and returns structured data.
// path is the root of the TCK installation (typically "knowledge/").
// If taskID is non-empty, only that task is read; otherwise all tasks are read.
func ReadTCK(path string, taskID string) (map[string]interface{}, error) {
	tasksDir := filepath.Join(path, "tasks")
	entries, err := os.ReadDir(tasksDir)
	if err != nil {
		return nil, fmt.Errorf("read tasks dir %s: %w", tasksDir, err)
	}

	result := map[string]interface{}{}

	// Read registry if it exists
	registryPath := filepath.Join(path, "registry.md")
	if regData, err := os.ReadFile(registryPath); err == nil {
		reg := parseFrontmatter(string(regData))
		result["registry"] = reg
	}

	// Read tasks
	var tasks []map[string]interface{}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		dirName := entry.Name()

		// If taskID specified, filter
		if taskID != "" && !strings.HasPrefix(dirName, taskID+"-") && dirName != taskID {
			continue
		}

		taskDir := filepath.Join(tasksDir, dirName)
		taskData, err := readTaskDir(taskDir, dirName)
		if err != nil {
			continue // skip unreadable tasks
		}
		tasks = append(tasks, taskData)
	}

	if taskID != "" && len(tasks) == 0 {
		return nil, fmt.Errorf("task %s not found in %s", taskID, tasksDir)
	}

	result["tasks"] = tasks
	return result, nil
}

// readTaskDir reads a single task directory and returns its data.
func readTaskDir(taskDir, dirName string) (map[string]interface{}, error) {
	task := map[string]interface{}{
		"dir": dirName,
	}

	// Read task.md
	taskMDPath := filepath.Join(taskDir, "task.md")
	if data, err := os.ReadFile(taskMDPath); err == nil {
		fm := parseFrontmatter(string(data))
		for k, v := range fm {
			task[k] = v
		}
	}

	// Read supplementary files
	suppFiles := []string{"plan.md", "sdd.md", "worklog.md", "decisions.md", "handoff.md"}
	for _, fname := range suppFiles {
		fpath := filepath.Join(taskDir, fname)
		if data, err := os.ReadFile(fpath); err == nil {
			fm := parseFrontmatter(string(data))
			// Use filename without extension as key
			key := strings.TrimSuffix(fname, ".md")
			task[key] = fm
		}
	}

	return task, nil
}

// parseFrontmatter parses YAML-like frontmatter + markdown content.
// Frontmatter is delimited by `---` on separate lines.
func parseFrontmatter(content string) map[string]interface{} {
	result := map[string]interface{}{}

	scanner := bufio.NewScanner(strings.NewReader(content))

	// Check for opening ---
	if !scanner.Scan() {
		return result
	}
	firstLine := strings.TrimSpace(scanner.Text())
	if firstLine != "---" {
		// No frontmatter, treat entire content as body
		result["body"] = content
		return result
	}

	// Parse frontmatter lines until closing ---
	var frontmatterLines []string
	inFrontmatter := true
	for scanner.Scan() {
		line := scanner.Text()
		if strings.TrimSpace(line) == "---" {
			inFrontmatter = false
			break
		}
		if inFrontmatter {
			frontmatterLines = append(frontmatterLines, line)
		}
	}

	// Parse key: value pairs
	parseSimpleYAML(frontmatterLines, result)

	// Collect remaining as body
	var bodyLines []string
	for scanner.Scan() {
		bodyLines = append(bodyLines, scanner.Text())
	}
	// Also include any lines before the opening --- that weren't part of frontmatter
	if len(bodyLines) > 0 {
		result["body"] = strings.TrimSpace(strings.Join(bodyLines, "\n"))
	}

	return result
}

// parseSimpleYAML parses a minimal YAML-like structure from lines.
// Supports: key: value, nested maps (indented), lists (- item).
func parseSimpleYAML(lines []string, result map[string]interface{}) {
	i := 0
	for i < len(lines) {
		line := lines[i]
		trimmed := strings.TrimSpace(line)

		// Skip empty lines and comments
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			i++
			continue
		}

		// Check for list item
		if strings.HasPrefix(trimmed, "- ") {
			listValue := strings.TrimPrefix(trimmed, "- ")
			// Continue collecting list items
			var list []string
			list = append(list, listValue)
			i++
			for i < len(lines) {
				next := strings.TrimSpace(lines[i])
				if strings.HasPrefix(next, "- ") {
					list = append(list, strings.TrimPrefix(next, "- "))
					i++
				} else {
					break
				}
			}
			// If we already have a "list" key, append
			if existing, ok := result["items"]; ok {
				if existingList, ok := existing.([]string); ok {
					result["items"] = append(existingList, list...)
				}
			} else {
				result["items"] = list
			}
			continue
		}

		// Key: value
		colonIdx := strings.Index(trimmed, ":")
		if colonIdx < 0 {
			i++
			continue
		}

		key := strings.TrimSpace(trimmed[:colonIdx])
		value := strings.TrimSpace(trimmed[colonIdx+1:])

		// Check for nested map (next lines are indented)
		nestedLines := collectIndented(lines, i+1)
		if len(nestedLines) > 0 {
			nestedMap := map[string]interface{}{}
			parseSimpleYAML(nestedLines, nestedMap)
			result[key] = nestedMap
			i += 1 + len(nestedLines)
		} else {
			if value == "" {
				value = "true" // bare key without value
			}
			result[key] = value
			i++
		}
	}
}

// collectIndented collects consecutive lines that are more indented than the baseline.
// It uses the indentation of the first collected line as the reference.
func collectIndented(lines []string, start int) []string {
	if start >= len(lines) {
		return nil
	}

	// Determine base indentation from the first non-empty line
	var baseIndent int
	baseSet := false
	for i := start; i < len(lines); i++ {
		trimmed := strings.TrimSpace(lines[i])
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		baseIndent = len(lines[i]) - len(strings.TrimLeft(lines[i], " \t"))
		baseSet = true
		break
	}
	if !baseSet || baseIndent == 0 {
		return nil
	}

	var result []string
	for i := start; i < len(lines); i++ {
		trimmed := strings.TrimSpace(lines[i])
		if trimmed == "" {
			result = append(result, lines[i])
			continue
		}
		indent := len(lines[i]) - len(strings.TrimLeft(lines[i], " \t"))
		if indent < baseIndent {
			break
		}
		result = append(result, lines[i])
	}
	return result
}
