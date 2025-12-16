#!/usr/bin/env python3.9
"""Startup script for the Delta Exchange Trading Platform.

Provides an interactive menu to launch the application in Terminal mode.
"""
import subprocess  # nosec B404
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()


def run_command(command):
    """Execute a shell command."""
    try:
        console.print(f"[dim]Executing: {command}[/dim]")
        subprocess.run(command, shell=True, check=True)  # nosec B602
    except subprocess.CalledProcessError:
        console.print("[bold red]Command failed[/bold red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")


def show_header():
    """Display the application header."""
    console.print(
        Panel.fit(
            "[bold blue]Delta Exchange Trading Platform[/bold blue]\n"
            "[dim]Interactive Terminal Launcher[/dim]",
            border_style="blue",
        )
    )


def main():
    """Start the interactive launcher."""
    show_header()

    while True:
        console.print("\n[bold]Select Command:[/bold]")
        console.print("1. [cyan]Fetch Historical Data[/cyan]")
        console.print("2. [cyan]Run Backtest[/cyan]")
        console.print("3. [green]Start Live Trading[/green]")
        console.print("4. [magenta]Generate Report[/magenta]")
        console.print("5. [red]Exit[/red]")

        cmd_choice = Prompt.ask(
            "Select command", choices=["1", "2", "3", "4", "5"], default="1"
        )

        if cmd_choice == "1":
            symbol = Prompt.ask("Symbol", default="BTCUSD")
            timeframe = Prompt.ask("Timeframe", default="1h")
            days = Prompt.ask("Days", default="30")
            cmd = (
                f"python3.9 main.py fetch-data --symbol {symbol} "
                f"--timeframe {timeframe} --days {days}"
            )
            run_command(cmd)

        elif cmd_choice == "2":
            strategy = Prompt.ask("Strategy Name")
            symbol = Prompt.ask("Symbol", default="BTCUSD")
            timeframe = Prompt.ask("Timeframe", default="1h")
            cmd = (
                f"python3.9 main.py backtest --strategy {strategy} "
                f"--symbol {symbol} --timeframe {timeframe}"
            )
            run_command(cmd)

        elif cmd_choice == "3":
            strategy = Prompt.ask("Strategy Name")
            symbol = Prompt.ask("Symbol", default="BTCUSD")
            paper = Confirm.ask("Use Paper Trading?", default=True)
            paper_flag = "--paper" if paper else ""
            
            candle_type = Prompt.ask(
                "Candle Type", 
                choices=["standard", "heikin-ashi"], 
                default="heikin-ashi"
            )
            
            cmd = (
                f"python3.9 main.py live --strategy {strategy} "
                f"--symbol {symbol} {paper_flag} --candle-type {candle_type}"
            )
            run_command(cmd)

        elif cmd_choice == "4":
            run_command("python3.9 main.py report")

        elif cmd_choice == "5":
            console.print("Goodbye!")
            sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting...[/yellow]")
        sys.exit(0)
