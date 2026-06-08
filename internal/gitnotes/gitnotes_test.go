package gitnotes

import (
	"strings"
	"testing"
)

func TestSanitizeTag(t *testing.T) {
	tests := []struct {
		input    string
		contains string // substring that must appear in result
	}{
		{"ERP-4521", "ERP-4521"},
		{"task/feature", "task-feature"},
		{"ПРОВЕРКА-001", "001"},       // cyrillic → dashes, suffix preserved
		{"hello world", "hello-world"}, // space → dash
		{"A.B_C-123", "A.B_C-123"},     // safe chars preserved
		{"", "x"},                       // empty → fallback
		{"№%:?*", "x"},                 // all unsafe → fallback
	}

	for _, tc := range tests {
		result := sanitizeTag(tc.input)
		if !strings.Contains(result, tc.contains) {
			t.Errorf("sanitizeTag(%q) = %q, want substring %q", tc.input, result, tc.contains)
		}
	}
}

func TestSanitizeTagCollision(t *testing.T) {
	// Different non-ASCII IDs must produce different tags
	a := sanitizeTag("ПРОВЕРКА-001")
	b := sanitizeTag("ЗАДАЧА-001")
	if a == b {
		t.Errorf("sanitizeTag collision: %q and %q both → %q", "ПРОВЕРКА-001", "ЗАДАЧА-001", a)
	}
}
