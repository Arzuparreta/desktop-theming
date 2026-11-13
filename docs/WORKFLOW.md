# Everyday workflow delivery plan

Status: everyday-workflow implementation for source version 0.3.0, following
the baseline audit at `1b7ad0a` on 2026-11-07. The initial planning record below
is retained to explain the decisions and remaining acceptance gates.

Implemented: a daily view sharing the full center's state, search/random,
bounded optional recursive libraries, applied/draft separation, latest-choice
preview workers, background discovery, shorter routine review, identifiable
history/direct reviewed undo, explicit reversible menu registration and private
per-session instance activation. Preview caching is memory-only, content-aware
and excluded from reviewed plans. Palette generation now analyzes each image
once. `--measure-startup` reports isolated fixture milestones.

Activation guidance is per integration. Subsequent work enables native
Kitty/Alacritty/Waybar watchers and guarded one-shot i3 activation; see
[current activation contracts and evidence](INTEGRATIONS.md#automatic-color-updates).
Other runtime appearances remain unverified. Residency/autostart, named profiles
and real-desktop/p95 performance claims remain outside this delivery. Compositor
focus and global shortcuts need real-session validation; no Mod+w binding is
installed. See [the actual user workflow](GUI.md#daily-use).

Validation for this delivery: the full suite completed 234 tests with one
Rofi/private-Xvfb check skipped because Xvfb is unavailable. The final launcher
suite additionally covers extract-and-run menu commands (29 tests). Ruff,
installer/build shell syntax and local documentation links pass. The rebuilt
AppImage reports 0.3.0 and passes its isolated smoke test, including actual
bundle registration/removal, private QtNetwork IPC and all 18 native file
adapters. The runtime's explicit extract-and-run flag is also exercised.

Two independent Opus 5.5 / high implementation reviews reproduced issues in
display identity, rollback after replacement, slow startup handoff, deferred
inventory/review/error interaction, cancelled previews and window resizing.
These were corrected with regression coverage. The bundle check also caught
and fixed a diagnostic socket-path limit under a long extraction TMPDIR.
No theme was applied to the developer's desktop. Real compositor focus and
application appearance remain unverified; the UI says so.

The plan incorporates two independent Claude Opus 5.5 / high analyses: everyday
interaction and cross-desktop launch/responsiveness. The synthesis chooses one
shared window/state model, treats live activation as necessary for each claimed
end-to-end integration, and defers residency until launch measurements justify it.

## Outcome

A returning user should be able to summon Linux Theming, find or shuffle an
image, see the proposed result and affected applications, approve it and return
to work using the keyboard. Initial composition belongs in the full control
center; repeating a theme change should not repeat setup.

The reference is the convenience of the original ThinkPad menu, without its
personal paths, assumed desktop stack or unrestricted apply hooks. The existing
[product and safety direction](DIRECTION.md) remains authoritative.

## Baseline findings before this implementation

- `bin/wallpaper-menu` offers image selection, random selection and the four
  adaptive/safe × dark/light combinations. It shows the current wallpaper and
  effective fallback, and lists images recursively. These are concrete daily
  tasks to retain. Its Mod+w binding is a personal example, not a default.
- `linux_theming/__main__.py` creates a fresh application/controller/window on
  each launch. There is no single-instance activation or quick entry point.
- `packaging/linux-theming.desktop` is bundled metadata with
  `Exec=linux-theming`. `scripts/install-platform.py` only explains launching
  and refuses normal `--apply`; there is no user-facing launcher registration.
- `Controller.refresh()` runs inventory before restoring the remembered image
  folder and generating its palette. Daily use shares startup work with desktop
  inspection. Navigation may restore an unapplied image: it must not be labelled
  as the active theme.
- `Controller.start()`, `edit()` and `chooseWallpaper()` share a global busy
  gate. A request made during palette computation is discarded. The QML disables
  rows during that work, so rapid browsing also stops accepting input.
- The image list has thumbnails and keyboard navigation, but no search, random
  action, favorites or recursive library. At the default window size its start
  can sit below the large preview and require scrolling.
- Review is a nearly full-window dialog dominated by a file selector and diff.
  `presentation.review_summary()` already provides a human-readable summary;
  use that existing boundary rather than replacing the engine's review model.
- `Controller.approve()` reloads the full overview and palette after applying.
  It reports saved configuration and asks the user to reload applications where
  needed. The legacy `walltheme.run_hooks()` signals Kitty, reloads i3 and may
  relaunch Polybar; the new platform must not call those hooks.
- `Controller.review()` calls `presentation.connection()` per selected component;
  each connection performs discovery, then `service.make_plan()` performs it
  again. This is a concrete profiling target, not a measured latency result.
- `changes.history()` exposes transaction status/components/file count without
  the image, requested/effective mode or polarity, so choosing undo lacks a
  useful description of the theme being restored.
- `service.apply_reviewed()` regenerates and compares the exact reviewed plan.
  `changes.locked()` serializes transactions. Single-instance UX is an addition
  to these protections, not a replacement for transaction locking.

An isolated run with the pinned PySide6 6.8.3 confirmed that choosing `b.JPG`
while the palette for `a #1.png` was running left `a #1.png` selected. The fixture
created no applied profile or history. This establishes the dropped-request
behavior; it does not benchmark the user's ThinkPad, AppImage launch, compositor
focus or real application reloads.

## Product decisions

### One application, two levels of interaction

Add a compact daily view within the existing window and keep the full center
for composition, inspection, exports and recovery. Share one controller, draft and transaction
engine. Opening the center from the compact view must retain the candidate,
component selection and any pending review; do not create two competing states.

The compact view contains the current applied theme, a searchable image library,
preview, dark/light and palette controls, a random action, affected-component
summary, review/apply and last-change undo. Keep the selected row visible and
put search and choices before optional large previews and technical details.

First use guides the user through a library and explicit integration selection.
After setup, entry returns directly to daily actions. New or newly detected
applications never join the managed set automatically.

### Fast review remains exact review

Changing a selection only previews. Prepare a review asynchronously and present
its plain-language scope next to the candidate, with every exact file/settings
change available before approval. Every apply approves that particular plan;
there is no permanent permission to apply future random themes or profiles.

Use the compact presentation only for unchanged, already managed integration
scope. New connections/disconnections, replacement/link decisions, preserved
external edits, conflicts and recovery require the attention flow. Classify
conservatively from the actual plan and ownership records in Python; both
presentations expose exact changes and require explicit approval.

Navigation keys must never apply. The key that selects an image must not also
approve a review that appears as a result. A changed candidate or input
invalidates approval immediately. Interrupted recovery and new ownership/link
decisions take precedence over the daily path. Undo is also reviewed and checks
for conflicts; its speed must come from discoverability, not weaker checks.

Keep applied theme, browsing candidate, pending changes, saved configuration and
known activation result distinct. Cancelling discards review authority. Remembered
navigation is not an applied profile or authorization to restore a desktop.
On entry, show the last applied profile as the reference; retain the last viewed
image as navigation or an explicitly labelled unapplied candidate. Display the
requested and effective palette modes together when accessibility requires a
safe fallback. Do not silently change the requested option to conceal fallback.
History and undo should name both the theme being removed and the theme being
restored; older journals without summaries remain readable with honest unknowns.

Keep the first compact view simple: no independent overlay process or controller.
If a smaller layout does not improve the measured tasks over a well-focused
Appearance page, use that page as the daily view instead. Extra windows alone
do not establish convenience.

### Discoverable launch, chosen shortcut

Offer **Add to application menu** with a reviewable per-user registration plan:
exact launcher/icon/executable paths, existing-file conflicts and undo data.
Opening the AppImage itself remains portable and has no registration side effect.
Unregister only owned, unchanged files; preserve profile and history.

The current transaction snapshot format is text-only and its allowed roots do
not include XDG data. Launcher registration must address both limits explicitly:
review binary icons by size/hash while retaining bounded original bytes for
restoration, and narrowly validate owned XDG data paths. Removal is a fresh,
reviewed disconnection operation, so later theme transactions do not prevent
unregistering; ordinary undo ordering and conflict protections still hold.
Desktop Entry command quoting/field-code escaping needs specification-based
tests, not shell string interpolation.

Choose an explicit stable AppImage location during registration. Handle spaces,
non-ASCII names, missing executables and moved images. Do not leave a launcher
pointing into an ephemeral mount, extraction directory or build environment.
Replacing that executable must retain the registration; moving it requires a
visible repair flow. Automatic copying/updating is separate product scope.

Expose launch actions for the compact view and full center. Show the command
that a user can assign in their desktop's shortcut settings. Never assign
Mod+w, edit a WM configuration or claim universal global-shortcut support.
Use environment-specific guidance and supported portals where available. Keep
menu launch usable when global shortcut or focus activation is unsupported.

Repeated launch should activate the existing instance in the same user/profile
and graphical session. Use private local IPC for a small allowlist of navigation
requests, never remote apply or arbitrary commands. Session identity, stale
endpoints, simultaneous launches and protocol-version mismatches need explicit
handling. Wayland focus remains subject to the compositor's activation policy.

Use the existing session-identity and host-environment helpers where appropriate.
Validate the runtime directory and private endpoint rather than falling back to
an untrusted shared path. A newly launched executable must detect an older
running version and explain how to switch after pending work finishes; never
silently hand off to obsolete code or terminate the running process.

A resident process is an optional later optimization, only after measuring
ordinary launch. No default daemon, autostart, tray requirement or hidden
close-to-background behavior. If offered, provide an explicit enable/disable,
clear quit action and reviewable autostart registration.

### Responsive preview, conservative writes

Keep apply, undo, ownership decisions and recovery serialized. Separate their
exclusive state from cancellable preview, library listing and inventory work.
Accept new browsing input while computing; publish only results whose request
revision still matches the current candidate. Coalesce superseded work instead
of building a queue of obsolete images. A failed image must not retain an old
palette as though it belongs to the new selection.

Escape cancels the current navigation/review without applying. Closing during
read-only work cancels or discards that work; closing during a transaction must
explain that it is finishing safely. Reopening the compact view never converts
a cancelled or abandoned draft into permission to apply.

Show a usable daily surface before a full inventory refresh. Cached inventory is
labelled as last known; review/apply still re-probes the relevant configuration,
session and dependencies. Bound slow external probes and surface their failures.

Cache image analysis/palettes only after profiling. Include image identity and
content change, palette options and engine version in invalidation. Cache data
is disposable and never supplies authorization, ownership or trusted apply plans.
Check the duplicate image-analysis work in `theme.palette()`/the legacy pure
palette engine before adding a broad cache layer.

### Configured and visible are separate outcomes

The daily flow must explain whether changes are saved, observed live, require
manual activation or have an unknown runtime result. File-writing success is
not evidence of a running application's appearance.

Introduce activation support per integration only where there is a safe,
targeted mechanism and disposable-session evidence. Each action declares its
scope and is explicitly reviewed/authorized, either alongside the file change
or as a separate action. Never broadcast process-name signals, restart a bar,
reload unrelated session settings or reuse the legacy hooks for convenience.
The i3 adapter compares the actual loaded config with the reviewed file and
offers IPC reload only when non-color settings match; it never restarts i3.

Activation failure must not be reported as a failed file transaction if the
configuration was saved. Show what succeeded, what failed and the next action.
Undo restores configuration; do not claim it restores process state unless that
adapter separately supports and verifies it. Unsupported reloads retain clear
manual instructions, rather than blocking all other daily improvements.

## Execution order and acceptance gates

1. **Establish the baseline and interaction contract.** Add isolated fixtures and
   instrumentation for process start, first visible frame, usable library,
   candidate preview, fresh review, apply completion and visible activation.
   Record Qt/Python, image sizes/count, packaging mode, hardware and session.
   Measure mounted AppImage and extract-and-run separately, cold and repeated
   launches separately. Compare the legacy menu only on a disposable compatible
   session, or through the user's own timed trial; do not execute its hooks on
   the developer's desktop. Capture task steps and focus behavior, not just CPU
   time. Record accessibility and shortcut expectations before changing layout.

2. **Make state honest and stop dropping user intent.** Separate the applied
   profile, draft and last-viewed image in `gui.py`; show pending changes and
   discard, effective fallback and identifiable history in `Main.qml`,
   `presentation.py` and backward-compatible transaction summaries. Refactor
   `gui.py` work scheduling and update QML enabled/focus rules. Test rapid image changes, stale results,
   folder changes while decoding, failures, close/cancel and apply exclusion.
   Gate: the final user choice always wins, no old palette is mislabelled, and
   no preview creates profile/ownership/history or changes the desktop. Reopening
   after viewing an unapplied image cannot present it as the applied theme.

3. **Make the daily task complete inside Qt.** Add the compact view over the
   same engine, search, random-with-preview, mode controls, inline review and
   direct reviewed undo. Reuse the existing full center for initial composition
   and exceptional decisions. Start with the existing selected folder; add
   optional recursive libraries with bounded enumeration, cancellation and
   defined symlink behavior. Remember library navigation independently of the
   applied profile. Gate: after setup, image change, random, dark/light,
   adaptive/safe and undo work entirely by keyboard without opening a file
   manager, visiting Components or losing the selected row. An empty/unmounted
   library gives an actionable state and does not silently choose another image.
   Make random's scope visible (the selected library/filter), exclude the current
   candidate when alternatives exist, and explain the single-image case. Start
   search on the selected image and retain its position across previews. Keep
   Ctrl+R for desktop refresh; choose separate discoverable keys for search,
   random and mode changes. Shortcut handlers defer to focused text editors and
   modal ownership/review dialogs.

4. **Make the daily task easy to summon.** Add reviewed menu registration,
   repair/removal and single-instance activation in the entry point/packaging.
   Extend the transaction model deliberately for XDG data paths rather than
   pretending launcher installation is theme composition. Gate: menu launch and
   repeated activation work after executable replacement; conflicting files,
   links, stale IPC and a second session do not overwrite or hijack state.
   Document manual shortcut setup for each validated desktop.

5. **Close the configured-to-visible gap.** Extend integration capabilities and
   presentation with activation states; implement targeted activation one
   integration at a time. Prioritize the original workflow's affected terminal,
   launcher, notifications, bar and WM, but do not assume a supported reload for
   each. Gate: real disposable-session appearance and undo evidence for every
   claimed live adapter, explicit partial failure, and no reload during
   discovery, browsing, registration, tests against the actual desktop or
   unapproved application.

6. **Tune measured bottlenecks and finish wider composition.** Profile launch,
   decode, analysis, inventory and review independently; add bounded caches or
   optional residency only if evidence justifies them. Favorites/recent choices
   and named profiles follow the functioning daily loop. Profiles store explicit
   scopes and portable library references; switching still generates a fresh
   reviewed plan. Multi-monitor placement, broader activation and further DE
   adapters retain separate capability and validation records.

Each step is a coherent delivery with checks, a pushed commit and an updated
local AppImage/checksum whenever bundled code, UI, resources or packaging change.
Do not wait for every desktop adapter to work before delivering the daily loop.
Do not label the whole roadmap complete after adding only a shortcut or a panel.

Treat steps 1–4 as the first complete everyday-workflow milestone: it includes
both a better daily task and an accessible way to summon it. Step 5 extends
live integration by integration; step 6 follows measured bottlenecks. Within
the first milestone, launcher work can proceed independently once its review
and ownership contract is defined.

## Implementation boundaries

- `gui.py` owns request revisions and applied/draft UI state; `Main.qml` and a
  possible daily-view QML component share that state. Do not put safety or
  routine-versus-attention classification in QML.
- `presentation.py` provides concise scope and exact-change navigation. Reuse
  one discovery snapshot within a review where safe; keep the engine's fresh
  apply-time checks. `changes.py` exposes backward-compatible theme summaries
  for history and retains locking, conflict checks and journals.
- A focused library module can own search/random/recursive enumeration as it
  outgrows `chooseFolder()`. `navigation.py` stores explicitly chosen browsing
  preferences with its existing path/permission protections; caches belong in
  XDG cache, not restoration records.
- The entry point handles quick/center launch intent. A small instance module
  can contain private navigation-only IPC. A separate launcher-registration
  module validates executable identity and the narrowly allowed XDG data paths;
  it must not broaden theme plans into unrestricted file writes.
- Integration capability data and a dedicated activation boundary describe any
  supported live action. Keep native wallpaper/settings transactions distinct
  from application activation, and retain structured partial outcomes.
- Extend `test_gui.py`, `test_review_undo.py`, `test_install.py` and bundled
  `smoke.py` at these seams. Add focused tests for IPC/registration/library work
  where existing suites do not cover its behavior.

## Performance and usability targets

These are proposed acceptance budgets, not measured performance claims. First
record a baseline on named reference hardware and representative libraries.

- Warm activation to focused, usable daily controls: p95 at most 200 ms where
  the compositor permits activation. Report focus refusal separately.
- Mounted-AppImage launch to usable daily controls: initial p95 budget 1 s;
  refine openly after measuring. Report extraction overhead separately.
- Selection feedback within 50 ms, with browsing available during computation.
  Target a current-candidate preview within 300 ms warm / 1 s uncached for the
  documented image fixture; slow inputs show progress and remain cancellable.
- A repeat mode/random operation should require summoning, choosing and one
  explicit approval once its exact fresh review is ready. Image search adds
  typing/selection. No mandatory diff navigation, repeated setup or timed
  auto-approval. New conflicts or ownership choices can require extra decisions.
- No mouse required for normal daily operations; visible focus, appropriate
  accessible names, no unexpected focus jumps and usable layout at 200% scale.
- Reopening or cancelling never changes the desktop. Pending recovery is always
  visible before any fresh apply is offered.

## Validation and delivery

Use disposable HOME and all XDG directories, private displays/sessions where
needed and the project-pinned Qt/Python. Never validate by theming the actual
developer desktop. Run the required unittest discovery, Ruff and shell syntax
checks; extend existing GUI and bundled smoke coverage for the new workflows.

Cover first run and returning use, unavailable/moved libraries, unusual paths,
large collections, candidate/applied divergence, image changes in place,
out-of-order work, stale review, external edits, linked paths, competing launches,
IPC failure, interrupted writes, undo, repair and unregister conflicts.

For platform claims, record separate results for i3/X11, GNOME/Wayland,
Plasma/Wayland and supported Sway/Hyprland sessions. Offscreen Qt verifies
interaction/state but cannot establish compositor focus, shortcut portals,
application appearance or session activation. An unavailable test environment
remains unverified, not silently supported.

Rebuild affected local AppImages, run their isolated `--smoke-test`, refresh the
checksum and test registration against the actual bundle in a disposable
environment. Commit and push completed work without force-pushing. A versioned
release is a separate delivery following [APPIMAGE.md](APPIMAGE.md#github-releases)
when requested; this plan does not publish one.
