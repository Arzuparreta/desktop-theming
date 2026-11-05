# Product direction

desktop-theming is a modular control center for the Linux desktop. It helps
people understand their existing setup and compose a coherent desktop using
our wallpaper-derived, accessible color and theme system.

The original repository was an agent-created implementation of one person's
ThinkPad workflow. Its architecture and dotfiles are historical starting
points, not product requirements. The ThinkPad setup is one example profile.

## User experience

1. **Understand:** discover installed components, running components, the
   current session, and existing configuration. Installed, running, selected
   for management, and actually configured are different states.
2. **Compose:** choose components individually, keep existing preferences,
   and connect only the desired pieces to the common theme system.
3. **Preview:** inspect colors, supported behavior, missing dependencies and
   the exact proposed file changes before applying anything.
4. **Apply deliberately:** explicit approval authorizes the reviewed changes.
   Discovery never installs software or takes ownership of a configuration.
5. **Recover:** retain previous configuration and offer reversible changes.
   If files change afterwards, explain conflicts instead of overwriting them.

The interface should explain choices in everyday language. A user should be
able to say: "Use this wallpaper's colors in Ghostty, keep my icons, and leave
the rest of my desktop alone."

## Product principles

- Existing desktops are the starting point. Do not impose a desktop stack.
- A shared palette and accessibility rules connect independent integrations.
- Each integration declares what it can discover, configure and reload.
- Missing software is information, never permission to install it.
- Session detection must distinguish available tools from the active session.
- Changing an application theme does not imply replacing its entire config.
- Configuration, palette generation and application reload are separate steps.
- Prefer a small number of complete, verifiable integrations over broad claims.
- Show current limitations. GTK3, GTK4/libadwaita and Qt are separate targets;
  terminal contrast checks do not establish whole-desktop accessibility.
- No dependency on pywal or a particular window manager for discovery or the
  new control center. Retain the original workflow as an explicit legacy option.

## Current foundation and next interface

The current checkout provides a Qt Quick / PySide6 GUI over a Python engine for
read-only inventory, explicit component selection, palette preview, exact change
plans, application, export, undo and recovery.
There is no HTTP server, configuration CLI or MCP implementation.
The source launcher and AppImage packaging keep the engine local.

The GUI over the engine exposes existing color
sources, unresolved issues, explicit color replacement and symlink handling,
exact file changes, approval, disconnection and recovery. No user needs a terminal
command to finish those workflows. A future MCP interface and small fallback CLI
for agents will use the same engine.

Kitty and Ghostty are the first managed integrations. Wallpaper changes use automatically selected, session-specific adapters with
reviewed application and conflict-checked undo. Other component themes remain
discovery-only. See WALLPAPER.md for capability and validation limits. Connecting and
disconnecting an integration are both reviewed, reversible changes.

Discovery must not alter desktop settings. Applying a plan changes only the
selected integrations, an explicitly selected desktop wallpaper and the engine's
own profile/history. No automatic package installation, process signalling or
session reload is included. Probing never changes the wallpaper.

## Next outcomes

1. Extend terminal support (Alacritty and foot) and named profile composition.
2. Connect launchers, notifications and bars to the same palette.
3. Extend wallpaper coverage to additional protocols and session versions,
   retaining restorable state and conflict checks.
4. Add environment-specific GTK, GNOME, KDE Plasma and Xfce integrations,
   with individual capability and validation records.
5. Add explicit, reviewable dependency installation only when useful.

Each delivery must preserve user configuration, test failure/conflict recovery
and distinguish automated validation from verification in a real session.
