"""S3M Tactical CLI - Interactive Command Interface.

Provides field operators with direct access to the Quad-Engine system
through an interactive terminal interface with military-style commands.
"""

import cmd
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

# Try to import requests for API communication
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class TacticalCLI(cmd.Cmd):
    """S3M Tactical Command Line Interface."""

    intro = """
╔══════════════════════════════════════════════════════════════╗
║                 S3M QUAD-ENGINE SYSTEM v4.0                  ║
║              Tactical Command Line Interface                 ║
║                                                              ║
║  Engines: Phi-3 Medium | Grok-8B | Mistral-7B | ALLaM-7B     ║
║  Platform: NVIDIA Jetson AGX Orin 64GB                       ║
║  Status: AIR-GAPPED DEPLOYMENT                               ║
║                                                              ║
║  Type 'help' for commands or 'shortcuts' for quick actions   ║
╚══════════════════════════════════════════════════════════════╝
"""
    prompt = "\033[1;32mS3M>\033[0m "

    def __init__(self, api_url: str = "http://localhost:8080"):
        super().__init__()
        self.api_url = api_url
        self.current_engine = "phi3"
        self.current_domain = "general"
        self.temperature = 0.7
        self.max_tokens = 512
        self.history = []
        self.classification = "UNCLASSIFIED"

    # ── Helper Methods ────────────────────────────────────────

    def _api_call(self, method: str, endpoint: str, data: dict = None) -> Optional[dict]:
        """Make API call to S3M server."""
        if not HAS_REQUESTS:
            self._print_warning("requests library not installed. Install with: pip install requests")
            return None

        url = f"{self.api_url}{endpoint}"
        try:
            if method == "GET":
                resp = requests.get(url, timeout=30)
            elif method == "POST":
                resp = requests.post(url, json=data, timeout=60)
            elif method == "PUT":
                resp = requests.put(url, json=data, timeout=30)
            elif method == "PATCH":
                resp = requests.patch(url, json=data, timeout=30)
            else:
                return None

            if resp.status_code == 200:
                return resp.json()
            else:
                self._print_error(f"API returned {resp.status_code}: {resp.text}")
                return None
        except requests.ConnectionError:
            self._print_error(f"Cannot connect to API at {self.api_url}")
            self._print_info("Start the API server with: python scripts/start_api.py")
            return None
        except Exception as e:
            self._print_error(f"API call failed: {e}")
            return None

    def _print_response(self, text: str):
        print(f"\n\033[1;36m{'─' * 60}\033[0m")
        print(f"\033[1;37m{text}\033[0m")
        print(f"\033[1;36m{'─' * 60}\033[0m\n")

    def _print_info(self, text: str):
        print(f"\033[1;34m[INFO]\033[0m {text}")

    def _print_warning(self, text: str):
        print(f"\033[1;33m[WARN]\033[0m {text}")

    def _print_error(self, text: str):
        print(f"\033[1;31m[ERROR]\033[0m {text}")

    def _print_success(self, text: str):
        print(f"\033[1;32m[OK]\033[0m {text}")

    def _print_table(self, headers: list, rows: list):
        """Print a formatted table."""
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))

        header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        separator = "-+-".join("-" * w for w in widths)

        print(f"  {header_line}")
        print(f"  {separator}")
        for row in rows:
            line = " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
            print(f"  {line}")
        print()

    # ── Inference Commands ────────────────────────────────────

    def do_ask(self, arg):
        """Send a prompt to the current engine. Usage: ask <prompt>"""
        if not arg:
            self._print_warning("Usage: ask <your prompt here>")
            return

        self._print_info(f"Sending to {self.current_engine} (domain: {self.current_domain})...")

        result = self._api_call("POST", "/inference", {
            "prompt": arg,
            "engine": self.current_engine,
            "domain": self.current_domain,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        })

        if result:
            self._print_response(result.get("response", "No response"))
            self._print_info(
                f"Engine: {result.get('engine')} | "
                f"Tokens: {result.get('tokens_used')} | "
                f"Latency: {result.get('latency_ms')}ms | "
                f"ID: {result.get('request_id')}"
            )
            self.history.append({"prompt": arg, "response": result})

    def do_consensus(self, arg):
        """Run consensus across all engines. Usage: consensus <prompt>"""
        if not arg:
            self._print_warning("Usage: consensus <your prompt here>")
            return

        self._print_info("Running consensus across all engines...")

        result = self._api_call("POST", "/consensus", {
            "prompt": arg,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "strategy": "majority"
        })

        if result:
            self._print_response(result.get("consensus", "No consensus"))
            print(f"  Agreement Score: {result.get('agreement_score', 0):.2%}")
            print(f"  Strategy: {result.get('strategy')}")
            print(f"  Latency: {result.get('latency_ms')}ms")
            print()

            if "engine_responses" in result:
                print("  Individual Engine Responses:")
                for eng, resp in result["engine_responses"].items():
                    print(f"    [{eng.upper()}]: {resp[:100]}...")
                print()

    # ── Tactical Shortcuts ────────────────────────────────────

    def do_sitrep(self, arg):
        """Generate a situation report. Usage: sitrep <situation description>"""
        if not arg:
            arg = "current operational area"
        prompt = f"Generate a military SITREP (Situation Report) for: {arg}. Include: 1) Situation 2) Enemy Forces 3) Friendly Forces 4) Assessment 5) Recommendation"
        self.do_consensus(prompt)

    def do_opord(self, arg):
        """Generate an operations order. Usage: opord <mission description>"""
        if not arg:
            self._print_warning("Usage: opord <mission description>")
            return
        prompt = f"Generate a military OPORD (Operations Order) for: {arg}. Include: 1) Situation 2) Mission 3) Execution 4) Sustainment 5) Command"
        self.do_ask(prompt)

    def do_threat(self, arg):
        """Assess threat level. Usage: threat <threat description>"""
        if not arg:
            self._print_warning("Usage: threat <threat description>")
            return
        old_engine = self.current_engine
        self.current_engine = "grok"
        prompt = f"Provide a tactical threat assessment for: {arg}. Include threat level (LOW/MEDIUM/HIGH/CRITICAL), confidence score, and recommended actions."
        self.do_ask(prompt)
        self.current_engine = old_engine

    # ── Engine Management ─────────────────────────────────────

    def do_engine(self, arg):
        """Set current engine. Usage: engine <phi3|grok|mistral|allam>"""
        valid = ["phi3", "grok", "mistral", "allam"]
        if arg not in valid:
            self._print_warning(f"Usage: engine <{'|'.join(valid)}>")
            self._print_info(f"Current engine: {self.current_engine}")
            return
        self.current_engine = arg
        self._print_success(f"Engine set to: {arg}")

    def do_engines(self, arg):
        """List all engines and their status."""
        result = self._api_call("GET", "/engines")
        if result and "engines" in result:
            rows = []
            for eng in result["engines"]:
                status_icon = "●" if eng["status"] == "loaded" else "○"
                rows.append([
                    eng["name"],
                    f"{status_icon} {eng['status']}",
                    eng.get("model_path", "N/A"),
                    str(eng.get("gpu_layers", "N/A"))
                ])
            self._print_table(["Engine", "Status", "Model Path", "GPU Layers"], rows)
        else:
            # Fallback display
            self._print_info("Engine status (local):")
            for eng in ["phi3", "grok", "mistral", "allam"]:
                marker = ">>>" if eng == self.current_engine else "   "
                print(f"  {marker} {eng}")

    def do_load(self, arg):
        """Load an engine into memory. Usage: load <engine_name>"""
        valid = ["phi3", "grok", "mistral", "allam"]
        if arg not in valid:
            self._print_warning(f"Usage: load <{'|'.join(valid)}>")
            return
        self._print_info(f"Loading {arg}...")
        result = self._api_call("POST", f"/engines/{arg}/load")
        if result:
            self._print_success(result.get("message", "Done"))

    def do_unload(self, arg):
        """Unload an engine from memory. Usage: unload <engine_name>"""
        valid = ["phi3", "grok", "mistral", "allam"]
        if arg not in valid:
            self._print_warning(f"Usage: unload <{'|'.join(valid)}>")
            return
        result = self._api_call("POST", f"/engines/{arg}/unload")
        if result:
            self._print_success(result.get("message", "Done"))

    # ── Configuration Commands ────────────────────────────────

    def do_domain(self, arg):
        """Set current domain. Usage: domain <tactical|intelligence|logistics|arabic|general>"""
        valid = ["tactical", "intelligence", "logistics", "arabic", "general"]
        if arg not in valid:
            self._print_warning(f"Usage: domain <{'|'.join(valid)}>")
            self._print_info(f"Current domain: {self.current_domain}")
            return
        self.current_domain = arg
        self._print_success(f"Domain set to: {arg}")

    def do_temp(self, arg):
        """Set temperature. Usage: temp <0.0-2.0>"""
        try:
            val = float(arg)
            if 0.0 <= val <= 2.0:
                self.temperature = val
                self._print_success(f"Temperature set to: {val}")
            else:
                self._print_warning("Temperature must be between 0.0 and 2.0")
        except ValueError:
            self._print_warning("Usage: temp <0.0-2.0>")
            self._print_info(f"Current temperature: {self.temperature}")

    def do_tokens(self, arg):
        """Set max tokens. Usage: tokens <1-4096>"""
        try:
            val = int(arg)
            if 1 <= val <= 4096:
                self.max_tokens = val
                self._print_success(f"Max tokens set to: {val}")
            else:
                self._print_warning("Tokens must be between 1 and 4096")
        except ValueError:
            self._print_warning("Usage: tokens <1-4096>")
            self._print_info(f"Current max tokens: {self.max_tokens}")

    def do_config(self, arg):
        """Show current configuration."""
        print(f"\n  Current Configuration:")
        print(f"  {'─' * 40}")
        print(f"  API URL:        {self.api_url}")
        print(f"  Engine:         {self.current_engine}")
        print(f"  Domain:         {self.current_domain}")
        print(f"  Temperature:    {self.temperature}")
        print(f"  Max Tokens:     {self.max_tokens}")
        print(f"  Classification: {self.classification}")
        print(f"  History Items:  {len(self.history)}")
        print()

    # ── System Commands ───────────────────────────────────────

    def do_health(self, arg):
        """Check system health."""
        result = self._api_call("GET", "/health")
        if result:
            print(f"\n  System Health:")
            print(f"  {'─' * 40}")
            print(f"  Status:  {result.get('status', 'unknown')}")
            print(f"  Uptime:  {result.get('uptime_seconds', 0):.1f}s")
            print(f"  Engines:")
            for eng, status in result.get("engines", {}).items():
                icon = "●" if status == "loaded" else "○"
                print(f"    {icon} {eng}: {status}")
            print()

    def do_stats(self, arg):
        """Show system statistics."""
        result = self._api_call("GET", "/stats")
        if result:
            print(f"\n  System Statistics:")
            print(f"  {'─' * 40}")
            print(f"  Uptime:           {result.get('uptime_seconds', 0):.1f}s")
            print(f"  Total Requests:   {result.get('total_requests', 0)}")
            print(f"  Engines Loaded:   {result.get('engines_loaded', 0)}")
            print(f"  Engines Simulated:{result.get('engines_simulated', 0)}")
            print(f"  Audit Entries:    {result.get('audit_entries', 0)}")
            print()

    def do_audit(self, arg):
        """Show audit log. Usage: audit [limit]"""
        limit = 10
        if arg:
            try:
                limit = int(arg)
            except ValueError:
                pass

        result = self._api_call("GET", f"/audit?limit={limit}")
        if result and "logs" in result:
            if not result["logs"]:
                self._print_info("No audit entries yet.")
                return
            rows = []
            for entry in result["logs"]:
                rows.append([
                    entry.get("id", ""),
                    entry.get("timestamp", "")[:19],
                    entry.get("action", ""),
                    str(entry.get("details", {}))[:50]
                ])
            self._print_table(["ID", "Timestamp", "Action", "Details"], rows)

    def do_routing(self, arg):
        """Show domain routing table."""
        result = self._api_call("GET", "/routing")
        if result and "domain_routing" in result:
            rows = [[d, e] for d, e in result["domain_routing"].items()]
            self._print_table(["Domain", "Engine"], rows)
        else:
            self._print_info("Domain routing (local defaults):")
            for d, e in [("tactical", "phi3"), ("intelligence", "grok"),
                         ("logistics", "mistral"), ("arabic", "allam"), ("general", "phi3")]:
                print(f"  {d:15s} -> {e}")
            print()

    # ── Utility Commands ──────────────────────────────────────

    def do_shortcuts(self, arg):
        """Show available shortcuts."""
        print(f"\n  Tactical Shortcuts:")
        print(f"  {'─' * 50}")
        print(f"  sitrep <situation>  - Generate situation report")
        print(f"  opord <mission>     - Generate operations order")
        print(f"  threat <desc>       - Assess threat level")
        print()
        print(f"  Quick Commands:")
        print(f"  {'─' * 50}")
        print(f"  ask <prompt>        - Query current engine")
        print(f"  consensus <prompt>  - Query all engines")
        print(f"  engine <name>       - Switch engine")
        print(f"  domain <name>       - Switch domain")
        print(f"  temp <value>        - Set temperature")
        print(f"  tokens <value>      - Set max tokens")
        print(f"  health              - System health check")
        print(f"  stats               - System statistics")
        print(f"  audit [limit]       - View audit log")
        print(f"  config              - Show configuration")
        print(f"  clear               - Clear screen")
        print(f"  exit/quit           - Exit CLI")
        print()

    def do_clear(self, arg):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def do_history(self, arg):
        """Show command history."""
        if not self.history:
            self._print_info("No history yet.")
            return
        for i, entry in enumerate(self.history[-10:], 1):
            print(f"  {i}. {entry['prompt'][:60]}...")
        print()

    def do_exit(self, arg):
        """Exit the CLI."""
        print("\n  Shutting down S3M Tactical CLI...")
        print("  Stay safe, operator.\n")
        return True

    def do_quit(self, arg):
        """Exit the CLI."""
        return self.do_exit(arg)

    def do_EOF(self, arg):
        """Handle Ctrl+D."""
        print()
        return self.do_exit(arg)

    def default(self, line):
        """Handle unknown commands - treat as inference query."""
        self._print_info(f"Unknown command. Treating as query...")
        self.do_ask(line)

    def emptyline(self):
        """Do nothing on empty line."""
        pass
