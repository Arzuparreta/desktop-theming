pragma Singleton
import QtQuick

// Design tokens for the application's own interface. Previewed palettes never
// change these colors, so controls keep a stable contrast with any theme.
QtObject {
    readonly property color window: "#121418"
    readonly property color surface: "#181b20"
    readonly property color raised: "#1f2228"
    readonly property color hover: "#262a31"
    readonly property color pressed: "#2e333b"
    readonly property color canvas: "#0c0d10"
    readonly property color border: "#2b2f36"
    readonly property color borderStrong: "#3d424b"
    readonly property color text: "#eceef2"
    readonly property color textMuted: "#a9aeb8"
    readonly property color textFaint: "#8a909b"
    readonly property color disabled: "#5d626c"
    readonly property color accent: "#a8d5b5"
    readonly property color accentHover: "#bfe2c9"
    readonly property color accentPressed: "#8fc19e"
    readonly property color accentInk: "#0f1512"
    readonly property color accentSoft: "#1d2c23"
    readonly property color accentBorder: "#5f9c78"
    readonly property color warning: "#e8c27a"
    readonly property color warningSoft: "#2f2718"
    readonly property color warningBorder: "#6e5a32"
    readonly property color danger: "#f2a29c"
    readonly property color dangerSoft: "#32201f"
    readonly property color dangerBorder: "#7a3f3b"
    readonly property color info: "#9cc2f2"
    readonly property color infoSoft: "#1a2533"
    readonly property color infoBorder: "#34506f"
    readonly property color diffAdd: "#183022"
    readonly property color diffAddText: "#b9e6c6"
    readonly property color diffRemove: "#3a1f22"
    readonly property color diffRemoveText: "#f4c0bb"
    readonly property color diffHunk: "#9cb4d8"
    readonly property color focus: "#d8eedf"
    readonly property color scrim: "#b3080a0c"

    readonly property int radiusSmall: 6
    readonly property int radius: 8
    readonly property int radiusLarge: 12

    readonly property int caption: 12
    readonly property int body: 13
    readonly property int bodyLarge: 14
    readonly property int title: 16
    readonly property int heading: 20

    readonly property int controlHeight: 34
    readonly property string mono: "monospace"
}
