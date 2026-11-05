# Roadmap

Product direction: [docs/DIRECTION.md](docs/DIRECTION.md). The ThinkPad dotfiles
are one historical example, not the architecture or a required desktop stack.

## Delivered foundation

- [x] Read-only inventory with separate executable, process, config and session evidence.
- [x] Shared Python engine independent of any user interface.
- [x] Empty initial management selection; explicit opt-in for each integration.
- [x] Reuse the accessible palette engine without legacy application hooks or pywal.
- [x] Kitty and Ghostty generated themes and marked includes preserving other preferences.
- [x] Palette generation and exact change plans for review before application.
- [x] Conflict checks, previous file contents, rollback, undo and interrupted recovery.
- [x] Reviewed disconnection of an integration, independently reversible.
- [x] HOME/XDG isolation in engine and installer tests.
- [x] Source launcher and AppImage packaging; no automatic installation or desktop changes.

- [x] Inspect existing terminal color sources; require explicit replacement and link detachment.
- [x] Persistent color ownership, conflict detection and restoration on disconnection.
- [x] Standalone theme rendering in the engine for user-managed dotfiles.

## Next complete workflows

- [x] Build the GUI: inventory, color-source inspection, explicit replacement/link choices,
      previews, exact review, approval, standalone export, undo and recovery.
- [ ] MCP interface for agents, followed by a small fallback CLI over the shared engine.

- [ ] Named profiles: create, compare, switch and export component selections and theme settings.
- [ ] Alacritty and foot integration, including config-format/version differences.
- [ ] Verify Ghostty configuration and appearance in a real Ghostty session.
- [ ] Report applied file state versus running application state; explicit reload actions
      with adapter-specific support, never automatic during discovery or install.
- [x] File chooser for wallpaper color sources.
- [ ] Per-profile wallpaper libraries.
- [ ] Rofi/Wofi and Dunst/Mako palette adapters with interaction-state contrast checks.
- [ ] Polybar/Waybar adapters that preserve modules, hardware choices and existing styles.
- [ ] Wallpaper providers: X11 first, then Sway/Hyprland with explicit backend selection.
- [ ] GTK 3 preference management with selectable installed light/dark themes.
- [ ] Separate GTK 4/libadwaita, GNOME, KDE/Qt and Xfce capabilities and validation.
- [ ] Improve discovery for custom config locations, Flatpak and runtime desktop settings.
- [ ] Extend conservative parsing to quoted/optional includes and Ghostty resource themes.
- [ ] Optional reviewed dependency installation with per-distribution package information.
- [ ] Portable example profiles with no personal paths, services or hardware assumptions.

## Later composition options

- [ ] Fish and zsh style adapters; optional prompt segments using the common palette.
- [ ] Per-component overrides, icon/cursor selection and contrast explanations.
- [ ] Optional time-of-day or sensor-based appearance switching with explicit enrollment.
- [ ] Wallpaper thumbnails and library browsing.

Each adapter must declare discovery/configuration/reload capabilities and its
actual validation evidence. Previewing and inspection must remain read-only.
