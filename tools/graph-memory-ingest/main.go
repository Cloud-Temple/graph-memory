package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"graph-memory-ingest/internal/cli"
	"graph-memory-ingest/internal/config"
	"graph-memory-ingest/internal/tui"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to load config file: %v. Using defaults.\n", err)
		cfg = config.DefaultConfig()
	}

	ui := tui.NewUI(os.Stdin, os.Stdout)
	app := cli.NewApp(ui, cfg)

	exitCode := app.Run(ctx, os.Args[1:])
	os.Exit(exitCode)
}
