// Package main is the CLI entry point for worktrail v2.
// All commands support --json for machine-readable output.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"worktrail/internal/archive"
	"worktrail/internal/context"
	"worktrail/internal/contract"
	"worktrail/internal/doctor"
	"worktrail/internal/executor"
	"worktrail/internal/install"
	"worktrail/internal/index"
	"worktrail/internal/list"
	"worktrail/internal/report"
	wt "worktrail/internal/time"
	"worktrail/internal/types"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}

	cmd := os.Args[1]
	args := os.Args[2:]

	var result interface{}
	var err error

	switch cmd {
	case "context":
		result, err = handleContext(args)
	case "list":
		result, err = handleList(args)
	case "contract":
		result, err = handleContract(args)
	case "time":
		result, err = handleTime(args)
	case "decision":
		result, err = handleDecision(args)
	case "spec":
		result, err = handleSpec(args)
	case "progress":
		result, err = handleProgress(args)
	case "finalize":
		result, err = handleFinalize(args)
	case "index":
		result, err = handleIndex(args)
	case "report":
		result, err = handleReport(args)
	case "archive":
		result, err = handleArchive(args)
	case "install":
		result, err = handleInstall(args)
	case "uninstall":
		result, err = handleUninstall(args)
	case "doctor":
		result, err = handleDoctor(args)
	case "-h", "--help", "help":
		usage()
		return
	default:
		fmt.Fprintf(os.Stderr, "worktrail: unknown command %q\n", cmd)
		fmt.Fprintf(os.Stderr, "Run 'worktrail help' for usage.\n")
		os.Exit(1)
	}

	if err != nil {
		fmt.Fprintf(os.Stderr, "worktrail: %s\n", err)
		os.Exit(1)
	}

	if result != nil {
		_ = json.NewEncoder(os.Stdout).Encode(result)
	}
}

// ─── Context ─────────────────────────────────────────────────────────────────

func handleContext(args []string) (interface{}, error) {
	f := flag.NewFlagSet("context", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail context [--json]\n")
	}
	_ = f.Parse(args)

	ctx, err := context.Resolve()
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return ctx, nil
	}
	printContext(ctx)
	return nil, nil
}

// ─── List ────────────────────────────────────────────────────────────────────

func handleList(args []string) (interface{}, error) {
	f := flag.NewFlagSet("list", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	status := f.String("status", "", "filter by status")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail list [--status <s>] [--json]\n")
	}
	_ = f.Parse(args)

	summaries, err := list.List(*status)
	if err != nil {
		return nil, err
	}
	if summaries == nil {
		summaries = []types.TaskSummary{}
	}
	if *jsonFlag {
		return summaries, nil
	}
	printList(summaries)
	return nil, nil
}

// ─── Contract ────────────────────────────────────────────────────────────────

func handleContract(args []string) (interface{}, error) {
	if len(args) == 0 {
		fmt.Fprint(os.Stderr, "usage: worktrail contract <init|show|update> [args]\n")
		os.Exit(1)
	}

	sub := args[0]
	rest := args[1:]

	switch sub {
	case "init":
		return handleContractInit(rest)
	case "show":
		return handleContractShow(rest)
	case "update":
		return handleContractUpdate(rest)
	default:
		fmt.Fprintf(os.Stderr, "worktrail contract: unknown subcommand %q\n", sub)
		os.Exit(1)
		return nil, nil
	}
}

func handleContractInit(args []string) (interface{}, error) {
	f := flag.NewFlagSet("contract init", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task identifier (required)")
	name := f.String("name", "", "contract name (required)")
	scope := f.String("scope", "", "task scope (optional)")
	var relatesTo stringSliceFlag
	f.Var(&relatesTo, "relates-to", "related task IDs (repeatable)")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail contract init --task-id <id> --name \"...\" [--scope \"...\"] [--relates-to <id>] [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" || *name == "" {
		f.Usage()
		os.Exit(1)
	}

	c, err := contract.Init(*taskID, *name, *scope, relatesTo.slice())
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return c, nil
	}
	printContract(c)
	return nil, nil
}

func handleContractShow(args []string) (interface{}, error) {
	f := flag.NewFlagSet("contract show", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task identifier (optional)")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail contract show [--task-id <id>] [--json]\n")
	}
	_ = f.Parse(args)

	c, err := contract.Show(*taskID)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return c, nil
	}
	printContract(c)
	return nil, nil
}

func handleContractUpdate(args []string) (interface{}, error) {
	f := flag.NewFlagSet("contract update", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task identifier (required)")

	var sets stringSliceFlag
	f.Var(&sets, "set", "key=value update (repeatable)")

	criteriaFile := f.String("criteria-file", "", "path to JSON file with success criteria")
	verifyFile := f.String("verify-file", "", "path to JSON file with verification methods")
	var relatesTo stringSliceFlag
	f.Var(&relatesTo, "relates-to", "related task IDs (repeatable)")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail contract update --task-id <id> [--set <key=value>] [--relates-to <id>] [--criteria-file <path>] [--verify-file <path>] [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" {
		f.Usage()
		os.Exit(1)
	}

	updates := make(map[string]string)
	for _, s := range sets.values {
		parts := strings.SplitN(s, "=", 2)
		if len(parts) != 2 {
			return nil, fmt.Errorf("invalid --set value %q: expected key=value", s)
		}
		updates[parts[0]] = parts[1]
	}

	var rt []string
	if relatesTo.seen {
		rt = relatesTo.slice()
	}

	c, err := contract.Update(*taskID, updates, *criteriaFile, *verifyFile, rt)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return c, nil
	}
	printContract(c)
	return nil, nil
}

// ─── Time ────────────────────────────────────────────────────────────────────

func handleTime(args []string) (interface{}, error) {
	f := flag.NewFlagSet("time", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task identifier (optional)")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail time [--task-id <id>] [--json]\n")
	}
	_ = f.Parse(args)

	duration, err := wt.Derive(*taskID)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return struct {
			Duration string `json:"duration"`
		}{Duration: duration}, nil
	}
	fmt.Println(duration)
	return nil, nil
}

// ─── Decision ────────────────────────────────────────────────────────────────

func handleDecision(args []string) (interface{}, error) {
	if len(args) == 0 {
		fmt.Fprint(os.Stderr, "usage: worktrail decision <record|list> [args]\n")
		os.Exit(1)
	}

	sub := args[0]
	switch sub {
	case "record":
		return handleDecisionRecord(args[1:])
	case "list":
		return handleDecisionList(args[1:])
	default:
		fmt.Fprintf(os.Stderr, "worktrail decision: unknown subcommand %q\n", sub)
		os.Exit(1)
		return nil, nil
	}
}

func handleDecisionRecord(args []string) (interface{}, error) {
	f := flag.NewFlagSet("decision record", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task id")
	id := f.String("id", "", "decision id")
	title := f.String("title", "", "title")
	rationale := f.String("rationale", "", "rationale")
	resource := f.String("resource", "", "resource URI (preferred)")
	file := f.String("file", "", "file path")
	lines := f.String("lines", "", "line range")
	alternatives := f.String("alternatives", "", "alternatives semicolon-separated")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail decision record --task-id <id> --id <did> --title \"...\" --rationale \"...\" [--resource <uri> | --file <path>] [--lines <range>] [--alternatives \"alt1; alt2\"] [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" || *id == "" || *title == "" || *rationale == "" {
		f.Usage()
		os.Exit(1)
	}

	if *resource != "" && *file != "" {
		return nil, fmt.Errorf("--resource and --file are mutually exclusive")
	}
	if *resource != "" {
		*file = *resource
	}

	var alts []string
	if *alternatives != "" {
		for _, a := range strings.Split(*alternatives, ";") {
			a = strings.TrimSpace(a)
			if a != "" {
				alts = append(alts, a)
			}
		}
	}

	d, err := executor.RecordDecision(*taskID, *id, *title, *rationale, *file, *lines, alts)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return d, nil
	}
	fmt.Printf("Decision %s recorded: %s\n", d.ID, d.Title)
	return nil, nil
}

func handleDecisionList(args []string) (interface{}, error) {
	f := flag.NewFlagSet("decision list", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task id")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail decision list --task-id <id> [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return nil, err
		}
		if !ctx.HasTask {
			return nil, fmt.Errorf("no task in current context — specify --task-id")
		}
		*taskID = ctx.TaskID
	}
	decisions, err := executor.ListDecisions(*taskID)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return decisions, nil
	}
	if len(decisions) == 0 {
		fmt.Println("No decisions recorded.")
		return nil, nil
	}
	for _, d := range decisions {
		fmt.Printf("[%s] %s\n", d.ID, d.Title)
		fmt.Printf("  Rationale: %s\n", d.Rationale)
		if len(d.Alternatives) > 0 {
			fmt.Printf("  Alternatives: %s\n", strings.Join(d.Alternatives, ", "))
		}
		if d.File != "" {
			loc := d.File
			if d.Lines != "" {
				loc += ":" + d.Lines
			}
			fmt.Printf("  Location: %s\n", loc)
		}
		fmt.Println()
	}
	return nil, nil
}

// ─── Spec ───────────────────────────────────────────────────────────────────

func handleSpec(args []string) (interface{}, error) {
	if len(args) == 0 {
		fmt.Fprint(os.Stderr, "usage: worktrail spec <record|list> [args]\n")
		os.Exit(1)
	}
	sub := args[0]
	switch sub {
	case "record":
		return handleSpecRecord(args[1:])
	case "list":
		return handleSpecList(args[1:])
	default:
		fmt.Fprintf(os.Stderr, "worktrail spec: unknown subcommand %q\n", sub)
		os.Exit(1)
		return nil, nil
	}
}

func handleSpecRecord(args []string) (interface{}, error) {
	f := flag.NewFlagSet("spec record", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task id")
	id := f.String("id", "", "spec id")
	scope := f.String("scope", "", "scope")
	invariants := f.String("invariants", "", "invariants semicolon-separated")
	resource := f.String("resource", "", "resource URI (preferred)")
	file := f.String("file", "", "file path")
	lines := f.String("lines", "", "line range")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail spec record --task-id <id> --id <sid> --scope \"...\" --invariants \"инв1; инв2; ...\" [--resource <uri> | --file <path>] [--lines <range>] [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" || *id == "" || *scope == "" || *invariants == "" {
		f.Usage()
		os.Exit(1)
	}

	if *resource != "" && *file != "" {
		return nil, fmt.Errorf("--resource and --file are mutually exclusive")
	}
	if *resource != "" {
		*file = *resource
	}

	var invs []string
	for _, inv := range strings.Split(*invariants, ";") {
		inv = strings.TrimSpace(inv)
		if inv != "" {
			invs = append(invs, inv)
		}
	}

	s, err := executor.RecordSpec(*taskID, *id, *scope, invs, *file, *lines)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return s, nil
	}
	fmt.Printf("Spec %s recorded: %s (%d invariants)\n", s.ID, s.Scope, len(s.Invariants))
	return nil, nil
}

func handleSpecList(args []string) (interface{}, error) {
	f := flag.NewFlagSet("spec list", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task id")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail spec list [--task-id <id>] [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return nil, err
		}
		if !ctx.HasTask {
			return nil, fmt.Errorf("no task in current context — specify --task-id")
		}
		*taskID = ctx.TaskID
	}

	specs, err := executor.ListSpecs(*taskID)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return specs, nil
	}
	if len(specs) == 0 {
		fmt.Println("No specs recorded.")
		return nil, nil
	}
	for _, s := range specs {
		fmt.Printf("[%s] %s\n", s.ID, s.Scope)
		for _, inv := range s.Invariants {
			fmt.Printf("  - %s\n", inv)
		}
		if s.File != "" {
			loc := s.File
			if s.Lines != "" {
				loc += ":" + s.Lines
			}
			fmt.Printf("  Location: %s\n", loc)
		}
		fmt.Println()
	}
	return nil, nil
}

// ─── Progress ───────────────────────────────────────────────────────────────

func handleProgress(args []string) (interface{}, error) {
	if len(args) == 0 {
		fmt.Fprint(os.Stderr, "usage: worktrail progress <record|list> [args]\n")
		os.Exit(1)
	}
	sub := args[0]
	switch sub {
	case "record":
		return handleProgressRecord(args[1:])
	case "list":
		return handleProgressList(args[1:])
	default:
		fmt.Fprintf(os.Stderr, "worktrail progress: unknown subcommand %q\n", sub)
		os.Exit(1)
		return nil, nil
	}
}

func handleProgressRecord(args []string) (interface{}, error) {
	f := flag.NewFlagSet("progress record", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task id")
	summary := f.String("summary", "", "summary")
	commit := f.String("commit", "", "commit hash")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail progress record --task-id <id> --summary \"...\" [--commit <hash>] [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" || *summary == "" {
		f.Usage()
		os.Exit(1)
	}

	p, err := executor.RecordProgress(*taskID, *summary, *commit)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return p, nil
	}
	fmt.Printf("Progress recorded: %s\n", p.Summary)
	return nil, nil
}

func handleProgressList(args []string) (interface{}, error) {
	f := flag.NewFlagSet("progress list", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task id")
	last := f.Int("last", 0, "last N entries")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail progress list --task-id <id> [--last <n>] [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return nil, err
		}
		if !ctx.HasTask {
			return nil, fmt.Errorf("no task in current context — specify --task-id")
		}
		*taskID = ctx.TaskID
	}

	entries, err := executor.ListProgress(*taskID, *last)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return entries, nil
	}
	if len(entries) == 0 {
		fmt.Println("No progress entries.")
		return nil, nil
	}
	for _, p := range entries {
		fmt.Printf("[%s] %s\n", p.Timestamp.Format("2006-01-02 15:04"), p.Summary)
		if p.Commit != "" {
			fmt.Printf("       commit: %s\n", p.Commit[:8])
		}
	}
	return nil, nil
}


// ─── Finalize ───────────────────────────────────────────────────────────────

func handleFinalize(args []string) (interface{}, error) {
	f := flag.NewFlagSet("finalize", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task id")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail finalize [--task-id <id>] [--json]\n")
	}
	_ = f.Parse(args)

	if *taskID == "" {
		ctx, err := context.Resolve()
		if err != nil {
			return nil, err
		}
		if !ctx.HasTask {
			return nil, fmt.Errorf("no task in current context")
		}
		*taskID = ctx.TaskID
	}

	contract, err := executor.Finalize(*taskID)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return contract, nil
	}
	fmt.Printf("Task %s finalized. Status: done.\n", *taskID)
	return nil, nil
}


// ─── Report ─────────────────────────────────────────────────────────────────

func handleReport(args []string) (interface{}, error) {
	f := flag.NewFlagSet("report", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	taskID := f.String("task-id", "", "task id")
	save := f.Bool("save", false, "save to file")
	timesheet := f.Bool("timesheet", false, "timesheet report for employer")
	from := f.String("from", "", "start date (YYYY-MM-DD)")
	to := f.String("to", "", "end date (YYYY-MM-DD)")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail report [--task-id <id>] [--timesheet] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--save] [--json]\n")
	}
	_ = f.Parse(args)

	var (
		md  string
		err error
	)
	switch {
	case *timesheet:
		if *taskID != "" {
			md, err = report.BuildTimesheet(*taskID, *from, *to)
		} else {
			md, err = report.BuildTimesheetAll(*from, *to)
		}
	case *taskID != "":
		md, err = report.BuildReport(*taskID)
	default:
		md, err = report.BuildReportAll()
	}
	if err != nil {
		return nil, err
	}
	if *save {
		_ = os.MkdirAll(".worktrail/reports", 0755)
		var reportPath string
		switch {
		case *timesheet && *taskID != "":
			reportPath = fmt.Sprintf(".worktrail/reports/timesheet-%s.md", *taskID)
		case *timesheet:
			reportPath = ".worktrail/reports/timesheet.md"
		case *taskID != "":
			reportPath = fmt.Sprintf(".worktrail/reports/%s.md", *taskID)
		default:
			reportPath = ".worktrail/reports/all.md"
		}
		if err := os.WriteFile(reportPath, []byte(md), 0644); err != nil {
			return nil, fmt.Errorf("save report: %w", err)
		}
		fmt.Printf("Report saved to %s\n", reportPath)
	}
	if *jsonFlag {
		return map[string]string{"report": md}, nil
	}
	fmt.Print(md)
	return nil, nil
}

// ─── Index ───────────────────────────────────────────────────────────────────

func handleIndex(args []string) (interface{}, error) {
	f := flag.NewFlagSet("index", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	save := f.Bool("save", false, "save TASKS.md to repo root")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail index [--save] [--json]\n")
	}
	_ = f.Parse(args)

	md, err := index.BuildIndex()
	if err != nil {
		return nil, err
	}
	if *save {
		root, err := gitTopLevel()
		if err != nil {
			return nil, fmt.Errorf("not in a git repository: %w", err)
		}
		indexPath := filepath.Join(root, "TASKS.md")
		if err := os.WriteFile(indexPath, []byte(md), 0644); err != nil {
			return nil, fmt.Errorf("save index: %w", err)
		}
		fmt.Printf("Index saved to %s\n", indexPath)
	}
	if *jsonFlag {
		return map[string]string{"index": md}, nil
	}
	fmt.Print(md)
	return nil, nil
}

func gitTopLevel() (string, error) {
	out, err := exec.Command("git", "rev-parse", "--show-toplevel").Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

// ─── Archive ────────────────────────────────────────────────────────────────

func handleArchive(args []string) (interface{}, error) {
	if len(args) == 0 {
		fmt.Fprint(os.Stderr, "usage: worktrail archive tck [--path <path>] [--task-id <id>] [--json]\n")
		os.Exit(1)
	}

	sub := args[0]
	if sub != "tck" {
		fmt.Fprintf(os.Stderr, "worktrail archive: unknown subcommand %q\n", sub)
		os.Exit(1)
	}

	f := flag.NewFlagSet("archive tck", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	path := f.String("path", "", "TCK path")
	taskID := f.String("task-id", "", "task id")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail archive tck [--path <path>] [--task-id <id>] [--json]\n")
	}
	_ = f.Parse(args[1:])

	data, err := archive.ReadTCK(*path, *taskID)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return data, nil
	}
	b, _ := json.MarshalIndent(data, "", "  ")
	fmt.Println(string(b))
	return nil, nil
}

// ─── Install ────────────────────────────────────────────────────────────────

func handleInstall(args []string) (interface{}, error) {
	f := flag.NewFlagSet("install", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	dryRun := f.Bool("dry-run", false, "dry run")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail install [--dry-run] [--scan-root <path>] [--json]\n")
	}
	_ = f.Parse(args)

	output, err := install.Install(*dryRun)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return map[string]string{"output": output}, nil
	}
	fmt.Println(output)
	return nil, nil
}

// ─── Uninstall ──────────────────────────────────────────────────────────────

func handleUninstall(args []string) (interface{}, error) {
	f := flag.NewFlagSet("uninstall", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	dryRun := f.Bool("dry-run", false, "dry run")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail uninstall [--dry-run] [--json]\n")
	}
	_ = f.Parse(args)

	output, err := install.Uninstall(*dryRun)
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return map[string]string{"output": output}, nil
	}
	fmt.Println(output)
	return nil, nil
}


// ─── Doctor ─────────────────────────────────────────────────────────────────

func handleDoctor(args []string) (interface{}, error) {
	f := flag.NewFlagSet("doctor", flag.ContinueOnError)
	jsonFlag := f.Bool("json", false, "output as JSON")
	f.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: worktrail doctor [--json]\n")
	}
	_ = f.Parse(args)

	diag, err := doctor.Diagnose()
	if err != nil {
		return nil, err
	}
	if *jsonFlag {
		return diag, nil
	}
	b, _ := json.MarshalIndent(diag, "", "  ")
	fmt.Println(string(b))
	return nil, nil
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

type stringSliceFlag struct {
	values []string
	seen   bool
}

func (s *stringSliceFlag) String() string { return strings.Join(s.values, ", ") }
func (s *stringSliceFlag) Set(v string) error {
	s.values = append(s.values, v)
	s.seen = true
	return nil
}

func (s *stringSliceFlag) slice() []string { return s.values }

func usage() {
	fmt.Fprint(os.Stderr, `worktrail v2 — git-embedded task knowledge system

usage: worktrail <command> [args]

commands:
  context            show current task context
  list               list all tasks
  contract init      create a task contract
  contract show      show a task contract
  contract update    update a task contract
  decision record    record an architectural decision
  decision list      list decisions for a task
  spec record        record invariants for a scope
  spec list          list specs for a task
  progress record    record work progress
  progress list      list progress entries for a task
  finalize           finalize a task (status → done)
  time               derive work duration
  index              generate TASKS.md task index
  report             generate markdown report
  report --timesheet timesheet for employer
  archive tck        archive legacy TCK structure
  install            global install
  uninstall          global uninstall
  doctor             diagnostics
`)
}

// ─── Text formatters ─────────────────────────────────────────────────────────

func printContext(ctx *types.ContextOutput) {
	if !ctx.HasTask {
		fmt.Println("No task in current context.")
		return
	}
	fmt.Printf("Task:      %s\n", ctx.TaskID)
	fmt.Printf("Name:      %s\n", ctx.Name)
	fmt.Printf("Status:    %s\n", ctx.Status)
	fmt.Printf("Branch:    %s\n", ctx.Branch)
	fmt.Printf("Anchor:    %s\n", ctx.AnchorCommit)
	if ctx.HasContract {
		fmt.Println("Contract:  yes")
	} else {
		fmt.Println("Contract:  no")
	}
}

func printList(summaries []types.TaskSummary) {
	if len(summaries) == 0 {
		fmt.Println("No tasks found.")
		return
	}
	fmt.Printf("%-20s %-30s %-10s %-20s\n", "TASK ID", "NAME", "STATUS", "BRANCH")
	fmt.Println(strings.Repeat("-", 80))
	for _, s := range summaries {
		fmt.Printf("%-20s %-30s %-10s %-20s\n", s.TaskID, truncate(s.Name, 29), s.Status, s.Branch)
	}
}

func printContract(c *types.Contract) {
	fmt.Printf("Task ID:    %s\n", c.TaskID)
	fmt.Printf("Name:       %s\n", c.Name)
	if c.Summary != c.Name {
		fmt.Printf("Summary:    %s\n", c.Summary)
	}
	if c.Scope != "" {
		fmt.Printf("Scope:      %s\n", c.Scope)
	}
	fmt.Printf("Status:     %s\n", c.Status)
	fmt.Printf("Created:    %s\n", c.CreatedAt.Format("2006-01-02 15:04"))
	if !c.UpdatedAt.IsZero() {
		fmt.Printf("Updated:    %s\n", c.UpdatedAt.Format("2006-01-02 15:04"))
	}
	if c.Branch != "" {
		fmt.Printf("Branch:     %s\n", c.Branch)
	}
	if len(c.RelatesTo) > 0 {
		fmt.Printf("Related:    %s\n", strings.Join(c.RelatesTo, ", "))
	}
	if len(c.SuccessCriteria) > 0 {
		fmt.Println("\nSuccess criteria:")
		for _, sc := range c.SuccessCriteria {
			fmt.Printf("  [%s] %s\n", sc.ID, sc.Statement)
		}
	}
	if len(c.Verification) > 0 {
		fmt.Println("\nVerification:")
		for _, vm := range c.Verification {
			fmt.Printf("  %s (%s)\n", vm.Label, vm.Method)
		}
	}
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-1] + "…"
}

var _ = (*types.TaskNote)(nil)
