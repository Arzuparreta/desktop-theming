#!/usr/bin/env python3
"""Install only the control-center launcher unless the legacy profile is chosen."""

import argparse
import os
from datetime import datetime, timezone
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
    home = Path.home()
    target = home / ".local/bin/desktop-theming"
    if args.thinkpad:
        print("LEGACY THINKPAD WORKFLOW: replaces complete i3, kitty, polybar and rofi configs; "
              "links shell styles, may edit .zshrc and reapplies the saved theme.", flush=True)
        print("Existing regular files are backed up; old symlinks are repointed. "
              "Includes personal commands and paths. No packages are installed.", flush=True)
        if args.apply:
            os.execv("/bin/bash", ["bash", str(repo / "scripts/install-thinkpad.sh")])
        print("No changes. To choose this legacy setup explicitly: ./install.sh --thinkpad --apply")
        return
    source = repo / "bin/desktop-theming"
    print(f"Launcher: {target} -> {source}")
    print("No desktop configuration, shell startup files, themes or packages will be changed.")
    if not args.apply:
        print("No changes. To install this launcher: ./install.sh --apply")
        return
    if target.is_symlink() and target.resolve() == source:
        print("Launcher is already installed.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.is_dir():
        raise SystemExit(f"Refusing to replace a directory: {target}")
    if target.exists() or target.is_symlink():
        backup = target.with_name(target.name + ".bak-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
        target.rename(backup)
        print(f"Backup: {backup}")
    target.symlink_to(source)
    print("Installed. Run ~/.local/bin/desktop-theming (keep this checkout in place).")


if __name__ == "__main__":
    main()
