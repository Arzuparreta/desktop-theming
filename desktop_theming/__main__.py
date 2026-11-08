"""Keep existing python -m desktop_theming launch commands working."""
from linux_theming.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
