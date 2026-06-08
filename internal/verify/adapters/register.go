package adapters

import (
	"os/exec"
	"strings"

	"worktrail/internal/verify"
)

func init() {
	verify.Register(&PytestAdapter{})
	verify.Register(&GoTestAdapter{})
	verify.Register(&ManualAdapter{})
	verify.Register(&ShellAdapter{})
	verify.Register(&NoneAdapter{})
}

// headCommit returns the current HEAD commit hash.
func headCommit() string {
	out, err := exec.Command("git", "rev-parse", "HEAD").Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}
