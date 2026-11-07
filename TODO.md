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

The [everyday workflow record and plan](docs/WORKFLOW.md) tracks delivery and
remaining acceptance gates:

- [ ] Measure launch, browsing, review and activation against explicit daily tasks.
- [x] Separate applied, draft and last-viewed state; keep the latest preview request.
- [x] Deliver keyboard-first daily browsing, search/random, concise exact review and direct reviewed undo.
- [x] Add reviewed application-menu registration, repair/removal and single-instance activation.
- [x] Explain per-integration activation steps without claiming observed runtime appearance.
- [ ] Validate targeted explicit live activation separately in disposable real application sessions.

- [x] Build the GUI: inventory, color-source inspection, explicit replacement/link choices,
      previews, exact review, approval, standalone export, undo and recovery.
- [ ] MCP interface for agents, followed by a small fallback CLI over the shared engine.

- [ ] Named profiles: create, compare, switch and export component selections and theme settings.
- [x] Alacritty and foot integration, including conservative TOML and version-specific INI formats.
- [ ] Verify Ghostty configuration and appearance in a real Ghostty session.
- [ ] Report applied file state versus running application state; explicit reload actions
      with adapter-specific support, never automatic during discovery or install.
- [x] File chooser for wallpaper color sources.
- [ ] Per-profile wallpaper libraries.
- [x] Rofi/Wofi and Dunst/Mako palette defaults, interaction/urgency roles and contrast checks.
- [x] Polybar/Waybar adapters that preserve modules, hardware choices and existing styles.
- [x] Session-selected live wallpaper adapters and reviewed Swaybg background configuration.
- [x] Separate GTK 3/4 CSS, native GNOME mode/accent and Xfce installed theme counterparts.
- [x] KDE application color roles and qt5ct/qt6ct palettes with separate capability/validation records.
- [x] i3/Sway/Hyprland border roles and shared Sway/background file composition.
- [ ] Verify every new adapter's actual appearance in disposable real desktop sessions.
- [ ] Improve discovery for custom config locations, Flatpak and runtime desktop settings.
- [ ] Offer reviewed conflict resolutions in the GUI: keep my edit and stop managing, or
      replace it with the theme value.
- [ ] Accept KConfig keys with spaces (for example `[KFileDialog Settings]`) in kdeglobals.
- [ ] Extend conservative parsing to quoted/optional includes and Ghostty resource themes.
- [ ] Optional reviewed dependency installation with per-distribution package information.
- [ ] Portable example profiles with no personal paths, services or hardware assumptions.

## Later composition options

- [x] Fish and zsh interactive editor/syntax/pager style adapters, preserving prompts.
- [ ] Optional prompt segments using the common palette.
- [ ] Per-component overrides, icon/cursor selection and contrast explanations.
- [ ] Optional time-of-day or sensor-based appearance switching with explicit enrollment.
- [x] Wallpaper thumbnails, search/random and bounded optional recursive library browsing.

Each adapter must declare discovery/configuration/reload capabilities and its
actual validation evidence. Previewing and inspection must remain read-only.
