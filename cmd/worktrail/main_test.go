package main

import (
	"os/exec"
	"strings"
	"testing"
)

// cmdTest describes how to safely test a command is registered.
// flag is passed to avoid destructive operations (real install, finalize).
type cmdTest struct {
	name string
	flag string // safe flag that triggers handler without side effects
}

var allCommands = []cmdTest{
	// Read-only or no-flag commands — --help triggers usage path.
	{"context", "--help"},
	{"list", "--help"},
	{"time", "--help"},
	{"doctor", "--help"},

	// Subcommand-based — bogus sub triggers "unknown subcommand" exit (safe).
	{"contract", "___nosuchsub___"},
	{"decision", "___nosuchsub___"},
	{"spec", "___nosuchsub___"},
	{"progress", "___nosuchsub___"},
	{"archive", "___nosuchsub___"},

	// Destructive commands — need safe guard flags.
	// install --dry-run prints what would happen without doing it.
	{"install", "--dry-run"},
	// finalize with nonexistent task-id fails before touching any real task.
	{"finalize", "--task-id NOPE-9999999"},
	// report with nonexistent task-id fails fast (or prints empty).
	{"report", "--task-id NOPE-9999999"},
}

// TestAllCommandsRegistered verifies every known command routes to its
// handler and does NOT fall through to "unknown command". Catches switch
// regression where case statements shifted during refactoring.
func TestAllCommandsRegistered(t *testing.T) {
	binary := "./worktrail"
	if err := exec.Command("go", "build", "-o", binary, ".").Run(); err != nil {
		t.Fatalf("build worktrail: %v", err)
	}

	for _, ct := range allCommands {
		t.Run(ct.name, func(t *testing.T) {
			args := []string{ct.name}
			if ct.flag != "" {
				args = append(args, strings.Fields(ct.flag)...)
			}
			c := exec.Command(binary, args...)
			out, _ := c.CombinedOutput()
			output := string(out)

			if strings.Contains(output, "unknown command") {
				t.Errorf("command %q not registered in dispatch switch\noutput: %s", ct.name, output)
			}
		})
	}
}

// TestCommandsInHelpOutput verifies the usage() function lists all
// registered commands.
func TestCommandsInHelpOutput(t *testing.T) {
	binary := "./worktrail"
	cmd := exec.Command(binary, "help")
	out, _ := cmd.CombinedOutput()
	output := string(out)

	expectedCmds := []string{
		"context", "list", "contract", "time", "decision", "spec",
		"progress", "finalize", "report", "archive", "install", "doctor",
	}
	for _, name := range expectedCmds {
		if !strings.Contains(output, name) {
			t.Errorf("command %q missing from help output", name)
		}
	}
}
