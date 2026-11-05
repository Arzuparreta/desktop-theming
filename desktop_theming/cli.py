import argparse
import json
import sys
from pathlib import Path

from . import changes, inventory, service, theme
from .paths import Paths


def emit(value):
    print(json.dumps(value, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect and compose your desktop. "
                                     "Nothing is managed until you review and apply a plan.")
    sub = parser.add_subparsers(dest="command")
    dashboard = sub.add_parser("dashboard", help="open the local control center (default)")
    dashboard.add_argument("--no-browser", action="store_true")
    dashboard.add_argument("--port", type=int, default=0, help="local port; default: automatic")
    inspect = sub.add_parser("inspect", help="read-only desktop inventory")
    inspect.add_argument("--json", action="store_true")
    sub.add_parser("profile", help="show the current opt-in profile as JSON")
    preview = sub.add_parser("preview", help="preview colors without changing configuration")
    plan = sub.add_parser("plan", help="review exact changes without applying them")
    for command in (preview, plan):
        command.add_argument("--profile", type=Path, help="JSON profile; defaults to saved profile")
        command.add_argument("--wallpaper")
        command.add_argument("--mode", choices=("adaptive", "safe"))
        command.add_argument("--polarity", choices=("dark", "light"))
    plan.add_argument("--components", nargs="*", choices=sorted(inventory.SUPPORTED),
                      help="explicitly select integrations; nothing selected by default")
    plan.add_argument("--output", type=Path, help="save the reviewed plan for later application")
    apply = sub.add_parser("apply", help="apply an unchanged, previously reviewed plan")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--yes", action="store_true", help="approve the exact reviewed file changes")
    sub.add_parser("history", help="list theme transactions")
    for command in ("undo", "recover"):
        action = sub.add_parser(command, help="restore the previous configuration")
        action.add_argument("id", help="transaction ID from history")
        action.add_argument("--yes", action="store_true", help="approve restoring these files")
    args = parser.parse_args(argv)
    paths = Paths.current()
    try:
        if args.command in (None, "dashboard"):
            from .server import serve
            serve(paths, port=getattr(args, "port", 0),
                  open_browser=not getattr(args, "no_browser", False))
        elif args.command == "inspect":
            value = service.overview(paths)
            if args.json:
                emit(value)
            else:
                print(f"Session: {value['session']['desktop']} · {value['session']['type']}")
                print("COMPONENT          INSTALLED   RUNNING   CONFIGURED   MANAGED   SUPPORT")
                for item in value["components"]:
                    installed = "unknown" if item["installed"] is None else (
                        "yes" if item["installed"] else "no")
                    configured = any(file["exists"] for file in item["configs"])
                    def yes(state):
                        return "yes" if state else "no"
                    print(f"{item['name']:18} {installed:11} {yes(item['running']):9} "
                          f"{yes(configured):12} {yes(item['managed']):9} "
                          f"{'theme files' if item['supported'] else 'discovery only'}")
                print(f"\n{value['scope']}")
        elif args.command == "profile":
            emit(service.load_profile(paths))
        elif args.command in ("preview", "plan"):
            profile = (json.loads(args.profile.read_text()) if args.profile else
                       service.load_profile(paths))
            for field in ("wallpaper", "mode", "polarity", "components"):
                value = getattr(args, field, None)
                if value is not None:
                    profile[field] = value
            profile = service.validate_profile(profile)
            if args.command == "preview":
                emit(theme.palette(profile))
            else:
                value = service.make_plan(paths, profile)
                if args.output:
                    args.output.write_text(json.dumps(value, indent=2) + "\n")
                print(f"Plan {value['id'][:12]} · {len(value['changes'])} file change(s)")
                for item in value["changes"]:
                    print(item["diff"])
                for warning in value["warnings"]:
                    print(f"Note: {warning}")
                if args.output:
                    print(f"\nReviewed plan saved to {args.output}")
        elif args.command == "apply":
            if not args.yes:
                raise ValueError("Review the plan first, then pass --yes to approve its changes.")
            emit(service.apply_reviewed(paths, json.loads(args.plan.read_text())))
        elif args.command == "history":
            emit(changes.history(paths))
        elif args.command in ("undo", "recover"):
            if not args.yes:
                raise ValueError("Pass --yes to approve restoring the transaction's files. "
                                 "Later edits will never be overwritten.")
            emit(changes.undo(paths, args.id, recover=args.command == "recover"))
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"desktop-theming: {exc}", file=sys.stderr)
        return 1
    return 0
