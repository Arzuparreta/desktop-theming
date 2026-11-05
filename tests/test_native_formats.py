"""Use existing native parsers without displays, config execution or installation."""

import ctypes
import ctypes.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_theming import appearance, changes, service, theme
from desktop_theming.paths import Paths


class NativeFormatTests(unittest.TestCase):
    def test_available_native_parsers_accept_generated_themes_in_isolation(self):
        value = theme.palette(service.DEFAULT_PROFILE)
        checks = {"zsh": ("zsh", ["-dfn"]), "fish": ("fish", ["--no-config", "--no-execute"]),
                  "alacritty": ("alacritty", ["migrate", "--dry-run", "--skip-imports", "--config-file"]),
                  "i3": ("i3", ["-C", "-c"])}
        checked = []
        for component, (tool, arguments) in checks.items():
            executable = shutil.which(tool)
            if not executable:
                continue
            with self.subTest(component=component), tempfile.TemporaryDirectory(prefix="theme-parser-") as private:
                root = Path(private)
                config = root / ("theme.toml" if component == "alacritty" else "theme.conf")
                config.write_text(theme.render(component, value))
                env = {**os.environ, "HOME": private, "XDG_CONFIG_HOME": str(root / "config"),
                       "XDG_DATA_HOME": str(root / "data"), "XDG_STATE_HOME": str(root / "state"),
                       "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime"),
                       "DISPLAY": "", "WAYLAND_DISPLAY": "", "DBUS_SESSION_BUS_ADDRESS": ""}
                result = subprocess.run([executable, *arguments, str(config)], env=env,
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                checked.append(component)
        if not checked:
            self.skipTest("No supported native configuration parser is already installed")

    @unittest.skipUnless(shutil.which("rofi") and shutil.which("Xvfb"), "Rofi parsing requires an existing private Xvfb")
    def test_rofi_parser_accepts_rasi_on_a_private_display(self):
        from desktop_theming.smoke_wallpaper import private_display

        with tempfile.TemporaryDirectory(prefix="rofi-parser-") as private:
            root = Path(private)
            config = root / "theme.rasi"
            config.write_text(theme.render("rofi", theme.palette(service.DEFAULT_PROFILE)))
            with patch.dict(os.environ, HOME=private, XDG_CONFIG_HOME=str(root / "config"),
                            XDG_DATA_HOME=str(root / "data"), XDG_STATE_HOME=str(root / "state"),
                            XDG_CACHE_HOME=str(root / "cache"), XDG_RUNTIME_DIR=str(root / "runtime")), private_display(
                                shutil.which("Xvfb"), root):
                result = subprocess.run([shutil.which("rofi"), "-no-config", "-rasi-validate", str(config)],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("gsettings") and shutil.which("glib-compile-schemas"),
                         "Native GLib tools are not installed")
    def test_real_gsettings_apply_and_undo_use_only_private_schema_and_keyfile_backend(self):
        with tempfile.TemporaryDirectory(prefix="gsettings-parser-") as private:
            root = Path(private)
            schema = root / "schemas"
            schema.mkdir()
            (schema / "org.gnome.desktop.interface.gschema.xml").write_text('''<schemalist>
<enum id="test.Mode"><value nick="default" value="0"/><value nick="prefer-dark" value="1"/>
<value nick="prefer-light" value="2"/></enum>
<enum id="test.Accent"><value nick="blue" value="0"/><value nick="red" value="1"/></enum>
<schema id="org.gnome.desktop.interface" path="/org/gnome/desktop/interface/">
<key name="color-scheme" enum="test.Mode"><default>'default'</default></key>
<key name="accent-color" enum="test.Accent"><default>'blue'</default></key>
</schema></schemalist>''')
            result = subprocess.run([shutil.which("glib-compile-schemas"), str(schema)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            paths = Paths(root, root / "config", root / "state")
            with patch.dict(os.environ, HOME=private, XDG_CONFIG_HOME=str(paths.config),
                            XDG_STATE_HOME=str(paths.state), XDG_DATA_HOME=str(root / "data"),
                            XDG_CACHE_HOME=str(root / "cache"), XDG_RUNTIME_DIR=str(root / "runtime"),
                            GSETTINGS_BACKEND="keyfile", GSETTINGS_SCHEMA_DIR=str(schema),
                            DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent-isolated-bus",
                            DISPLAY="", WAYLAND_DISPLAY="", XDG_CURRENT_DESKTOP="GNOME"):
                profile = dict(service.DEFAULT_PROFILE, components=["gnome"], mode="safe",
                               resolutions={"gnome": {"replace_colors": True}})
                def which(command):
                    return "/test/gnome-shell" if command == "gnome-shell" else shutil.which(command)

                plan = service.make_plan(paths, profile, which=which)
                action = plan["settings_actions"][0]
                before = appearance.read(action)
                applied = service.apply_reviewed(paths, plan, which=which)
                self.assertEqual(appearance.read(action), action["after"])
                self.assertEqual(appearance.read(action)["color-scheme"], "prefer-dark")
                changes.undo(paths, applied["id"], reviewed=changes.review_undo(paths, applied["id"]))
                self.assertEqual(appearance.read(action), before)

    def test_existing_gtk3_parser_accepts_css_without_initializing_a_desktop(self):
        library = ctypes.util.find_library("gtk-3")
        if not library:
            self.skipTest("GTK 3 parser is not installed")
        gtk = ctypes.CDLL(library)
        gtk.gtk_css_provider_new.restype = ctypes.c_void_p
        gtk.gtk_css_provider_load_from_data.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                                       ctypes.c_ssize_t, ctypes.POINTER(ctypes.c_void_p)]
        gtk.gtk_css_provider_load_from_data.restype = ctypes.c_int
        gtk.g_object_unref.argtypes = [ctypes.c_void_p]
        value = theme.palette(service.DEFAULT_PROFILE)
        for component in ("gtk3", "gtk4", "wofi", "waybar"):
            with self.subTest(component=component):
                provider = gtk.gtk_css_provider_new()
                error = ctypes.c_void_p()
                text = theme.render(component, value).encode()
                try:
                    self.assertTrue(gtk.gtk_css_provider_load_from_data(provider, text, len(text),
                                                                       ctypes.byref(error)))
                finally:
                    gtk.g_object_unref(provider)
