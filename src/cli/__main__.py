"""Allow running CLI as module: python -m src.cli"""
from src.cli.tactical_cli import TacticalCLI

if __name__ == "__main__":
    cli = TacticalCLI()
    cli.cmdloop()
