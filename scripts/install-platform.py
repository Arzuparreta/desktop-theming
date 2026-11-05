#!/usr/bin/env python3
"""Describe the engine-only checkout or explicitly select the legacy installer."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Preview installation. "
                                     "Add --apply to authorize the listed changes.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true", help="preview only (the default)")
    parser.add_argument("--thinkpad", action="store_true",
                        help="explicitly select the original personal dotfiles workflow")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.thinkpad:
        print("LEGACY THINKPAD WORKFLOW: replaces complete i3, kitty, polybar and rofi configs; "
              "links shell styles, may edit .zshrc and reapplies the saved theme.", flush=True)
        print("Existing regular files are backed up; old symlinks are repointed. "
              "Includes personal commands and paths. No packages are installed.", flush=True)
        if args.apply:
            os.execv("/bin/bash", ["bash", str(repo / "scripts/install-thinkpad.sh")])
        print("No changes. To choose this legacy setup explicitly: ./install.sh --thinkpad --apply")
        return
    message = "This checkout contains the Python engine only; no application is available to install."
    if args.apply:
        raise SystemExit(message + " No changes were made.")
    print(message)
    print("No changes. The legacy installer requires an explicit --thinkpad choice.")



if __name__ == "__main__":
    main()
