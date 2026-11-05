import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    required property QtObject controller
    readonly property var s: controller.state
    property int page: 0
    property var inspected: ({})
    property int diffIndex: 0
    readonly property string latestActive: (s.overview.history.filter(h => ["applied", "prepared", "recovery-needed", "undoing"].indexOf(h.status) >= 0)[0] || ({})).id || ""
    readonly property var preview: s.palette || ({})
    readonly property var special: preview.special || ({ background: "#14171c", foreground: "#d6dae1", cursor: "#cad8cb" })
    readonly property var colors: preview.colors || ({})
    width: 1080
    height: 780
    minimumWidth: 760
    minimumHeight: 600
    visible: true
    title: "Desktop Theming"
    color: "#1b1d22"
    font.family: "sans-serif"
    font.pixelSize: 13
    palette.window: "#1b1d22"
    palette.windowText: "#e7e7eb"
    palette.text: "#e7e7eb"
    palette.base: "#111318"
    palette.button: "#25272d"
    palette.buttonText: "#e7e7eb"
    palette.highlight: "#cad8cb"
    palette.highlightedText: "#17191d"
    onClosing: function(close) { if (s.busy) close.accepted = false }

    function openWallpaperPicker() { wallpaperPicker.open() }
    function closeWallpaperPicker() { wallpaperPicker.close() }
    function selected(id) { return s.profile.components.indexOf(id) >= 0 }
    function resolution(id, key) { return (s.profile.resolutions[id] || ({}))[key] }
    function evidence(c) {
        return (c.installed === null ? "Availability unknown" : c.installed ? "On PATH" : "Not on PATH")
             + " · " + (c.running ? "Running" : "Not running")
             + (c.current_session ? " · Active session" : "")
             + (c.managed ? " · Managed files" : "")
    }
    function inspect(c) { inspected = c; inspector.open() }

    Connections {
        target: controller
        function onChanged() {
            if (s.review.kind && !reviewDialog.visible) { diffIndex = 0; reviewDialog.open() }
            if (!s.review.kind && reviewDialog.visible) reviewDialog.close()
        }
    }
    Shortcut { sequence: "Ctrl+Return"; enabled: !s.busy && s.loaded && !reviewDialog.visible && !inspector.visible && !exportDialog.visible; onActivated: controller.review() }
    Shortcut { sequence: "Ctrl+R"; enabled: !s.busy && !reviewDialog.visible && !inspector.visible && !exportDialog.visible; onActivated: controller.refresh() }
    FileDialog {
        id: wallpaperPicker
        objectName: "wallpaperPicker"
        options: FileDialog.DontUseNativeDialog
        title: "Choose a color source"
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)", "All files (*)"]
        onAccepted: controller.chooseWallpaper(selectedFile.toString())
    }
    FileDialog {
        id: exportPicker
        options: FileDialog.DontUseNativeDialog
        title: "Save a new theme file"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "conf"
        onAccepted: controller.saveExport(selectedFile.toString())
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 20
        RowLayout {
            Layout.fillWidth: true
            Label { text: "Desktop Theming"; color: "#eeeeef"; font.pixelSize: 21; font.weight: Font.DemiBold }
            Item { Layout.fillWidth: true }
            Body { text: (s.overview.session.desktop || "Unknown session") + " / " + (s.overview.session.type || "unknown"); font.pixelSize: 12 }
            Command { text: "Refresh"; quiet: true; enabled: !s.busy; onClicked: controller.refresh(); Accessible.description: "Discard pending choices and inspect the desktop again" }
        }
        RowLayout {
            spacing: 4
            Repeater {
                model: ["Appearance", "Components", "History"]
                Command { required property int index; required property string modelData; text: modelData; quiet: window.page !== index; onClicked: window.page = index }
            }
            Item { Layout.fillWidth: true }
            Body { visible: s.busy; text: "Working…"; color: "#cad8cb"; Accessible.role: Accessible.StaticText }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#34363d" }
        Rectangle {
            visible: !!s.error || !!s.notice
            Layout.fillWidth: true
            implicitHeight: message.implicitHeight + 24
            color: s.error ? "#35282a" : "#263029"
            radius: 6
            Body { id: message; anchors.fill: parent; anchors.margins: 12; text: s.error || s.notice; color: s.error ? "#f0b8b5" : "#d0dfd1" }
        }
        StackLayout {
            currentIndex: window.page
            Layout.fillWidth: true
            Layout.fillHeight: true

            ScrollView {
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: 22
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 28
                        ColumnLayout {
                            Layout.preferredWidth: 290
                            Layout.maximumWidth: 330
                            Layout.alignment: Qt.AlignTop
                            spacing: 18
                            Label { text: "A palette for your desktop"; font.pixelSize: 19; color: "#e7e7eb" }
                            Body { Layout.fillWidth: true; text: "Choose colors. Connect only what you want." }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 160
                                radius: 8
                                color: "#111318"
                                clip: true
                                Image {
                                    anchors.fill: parent
                                    source: s.wallpaperUrl
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    autoTransform: true
                                    sourceSize.width: 660
                                }
                                Body { anchors.centerIn: parent; visible: !s.profile.wallpaper; text: "No image selected" }
                            }
                            RowLayout {
                                Command { text: "Choose image…"; enabled: !s.busy && s.loaded; onClicked: wallpaperPicker.open() }
                                Command { visible: !!s.profile.wallpaper; text: "Clear"; quiet: true; enabled: !s.busy; onClicked: controller.setOption("wallpaper", "") }
                            }
                            Body { Layout.fillWidth: true; visible: !!s.profile.wallpaper; text: s.profile.wallpaper; font.pixelSize: 11 }
                            Body { text: "Appearance"; color: "#e7e7eb" }
                            RowLayout {
                                Repeater {
                                    model: ["dark", "light"]
                                    Command { required property string modelData; text: modelData === "dark" ? "Dark" : "Light"; primary: s.profile.polarity === modelData; enabled: !s.busy && s.loaded; onClicked: controller.setOption("polarity", modelData) }
                                }
                            }
                            Body { text: "Color source"; color: "#e7e7eb" }
                            RowLayout {
                                Repeater {
                                    model: ["adaptive", "safe"]
                                    Command { required property string modelData; text: modelData === "adaptive" ? "From image" : "Safe palette"; primary: s.profile.mode === modelData; enabled: !s.busy && s.loaded; onClicked: controller.setOption("mode", modelData) }
                                }
                            }
                            Body { Layout.fillWidth: true; text: preview.reason || "Colors are checked for terminal contrast and distinction."; font.pixelSize: 12 }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            spacing: 16
                            RowLayout {
                                Body { text: "Terminal preview"; color: "#e7e7eb" }
                                Item { Layout.fillWidth: true }
                                Body { text: preview.effective ? preview.effective + " / " + preview.polarity : ""; font.pixelSize: 11 }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 310
                                radius: 8
                                color: special.background
                                border.color: "#3c3e45"
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 24
                                    spacing: 16
                                    Label { text: "~/projects"; font.family: "monospace"; font.pixelSize: 12; color: special.foreground; opacity: 0.65 }
                                    Label { text: "❯ git status"; font.family: "monospace"; font.pixelSize: 14; color: special.foreground }
                                    Label { text: "On branch main"; font.family: "monospace"; font.pixelSize: 13; color: special.foreground }
                                    Label { text: "  modified:  colors.conf"; font.family: "monospace"; font.pixelSize: 13; color: colors.color3 || "#d7bc82" }
                                    Label { text: "  added:     theme.conf"; font.family: "monospace"; font.pixelSize: 13; color: colors.color2 || "#99bd98" }
                                    RowLayout {
                                        Label { text: "❯"; font.family: "monospace"; font.pixelSize: 14; color: colors.color4 || "#9babcc" }
                                        Rectangle { width: 8; height: 17; color: special.cursor }
                                        Item { Layout.fillWidth: true }
                                    }
                                    Item { Layout.fillHeight: true }
                                }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 8
                                columnSpacing: 7
                                rowSpacing: 7
                                Repeater {
                                    model: 16
                                    Rectangle {
                                        required property int index
                                        Layout.fillWidth: true
                                        implicitHeight: 30
                                        radius: 4
                                        color: colors["color" + index] || "#36383f"
                                        border.color: "#555761"
                                        Accessible.name: "ANSI " + index + ": " + color
                                        HoverHandler { id: swatchHover }
                                        ToolTip.visible: swatchHover.hovered
                                        ToolTip.text: "ANSI " + index + " · " + color
                                    }
                                }
                            }
                            Body { Layout.fillWidth: true; text: "Preview only. Your wallpaper and running applications stay as they are."; font.pixelSize: 12 }
                            RowLayout {
                                Command { text: "Export theme…"; quiet: true; enabled: !s.busy && !!preview.special; onClicked: { exportDialog.open() } }
                                Item { Layout.fillWidth: true }
                            }
                        }
                    }
                }
            }

            ScrollView {
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: 0
                    Body { Layout.fillWidth: true; text: "Connect terminals to this palette. Everything else is discovery only."; bottomPadding: 20 }
                    Repeater {
                        model: s.overview.components
                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 0
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.topMargin: 12
                                Layout.bottomMargin: 12
                                spacing: 20
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    RowLayout {
                                        Label { text: modelData.name; color: "#e7e7eb"; font.pixelSize: 15 }
                                        Body { text: modelData.category; font.pixelSize: 11 }
                                    }
                                    Body { Layout.fillWidth: true; text: evidence(modelData); font.pixelSize: 12 }
                                }
                                Command { text: "Inspect"; quiet: true; enabled: !s.busy; onClicked: inspect(modelData) }
                                Choice {
                                    visible: modelData.supported
                                    objectName: "connect-" + modelData.id
                                    text: "Connect"
                                    checked: selected(modelData.id)
                                    enabled: !s.busy && s.loaded && (modelData.installed || checked)
                                    onClicked: controller.selectComponent(modelData.id, checked)
                                    Accessible.name: "Connect " + modelData.name
                                }
                                Body { visible: !modelData.supported; text: "Discovery only"; font.pixelSize: 12; Layout.preferredWidth: 100 }
                            }
                            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#2c2e35" }
                        }
                    }
                    Body { Layout.fillWidth: true; text: s.overview.scope || ""; font.pixelSize: 11; topPadding: 20 }
                }
            }

            ScrollView {
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: 12
                    Body { Layout.fillWidth: true; visible: !s.overview.history.length; text: "No changes yet. Applied changes and recovery options will appear here."; topPadding: 20 }
                    Repeater {
                        model: s.overview.history
                        Rectangle {
                            required property var modelData
                            readonly property bool pending: ["prepared", "recovery-needed", "undoing"].indexOf(modelData.status) >= 0
                            Layout.fillWidth: true
                            implicitHeight: historyRow.implicitHeight + 28
                            radius: 6
                            color: "#22242a"
                            RowLayout {
                                id: historyRow
                                anchors.fill: parent
                                anchors.margins: 14
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Body { text: new Date(modelData.created).toLocaleString(Qt.locale(), Locale.ShortFormat); color: "#e7e7eb" }
                                    Body { text: modelData.status + " · " + modelData.files + " files · " + (modelData.components.join(", ") || "Palette profile"); font.pixelSize: 12 }
                                    Body { text: modelData.id; font.family: "monospace"; font.pixelSize: 10 }
                                }
                                Command { text: pending ? "Review recovery" : "Review undo"; visible: pending || modelData.status === "applied"; enabled: !s.busy && modelData.id === latestActive; onClicked: controller.reviewUndo(modelData.id, pending) }
                            }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#34363d" }
        RowLayout {
            Layout.fillWidth: true
            Body { Layout.fillWidth: true; text: s.profile.components.length ? "Selected: " + s.profile.components.join(", ") : "No components selected"; font.pixelSize: 12 }
            Command { objectName: "reviewChanges"; text: "Review changes"; primary: true; enabled: !s.busy && s.loaded; onClicked: controller.review() }
        }
    }

    Dialog {
        id: inspector
        objectName: "inspector"
        anchors.centerIn: parent
        width: Math.min(window.width - 64, 720)
        height: Math.min(window.height - 64, 680)
        modal: true
        title: inspected.name || "Component"
        background: Rectangle { color: "#202228"; border.color: "#41434c"; radius: 10 }
        contentItem: ColumnLayout {
            spacing: 16
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true
                ColumnLayout {
                    width: parent.width
                    spacing: 14
                    Body { Layout.fillWidth: true; text: evidence(inspected) }
                    Body { Layout.fillWidth: true; text: inspected.supported ? "Theme application supported. Running application colors are not inspected." : "Discovery only. This component cannot be themed here." }
                    Repeater {
                        model: inspected.configs || []
                        Body { required property var modelData; Layout.fillWidth: true; text: modelData.path + (modelData.symlink ? " → " + modelData.target : "") + (modelData.exists ? "" : " (missing)"); font.family: "monospace"; font.pixelSize: 12 }
                    }
                    Repeater {
                        model: (inspected.configuration || ({})).issues || []
                        Body { required property string modelData; Layout.fillWidth: true; text: modelData; color: "#f0b8b5" }
                    }
                    Body { visible: !!inspected.supported; text: "Existing color sources"; color: "#e7e7eb" }
                    Body { visible: !!inspected.supported && !((inspected.configuration || ({})).sources || []).length; text: "No color sources found in conventional configuration." }
                    Repeater {
                        model: (inspected.configuration || ({})).sources || []
                        Body { required property var modelData; Layout.fillWidth: true; text: modelData.path + ":" + modelData.line + "\n" + modelData.directive + " " + modelData.value + (modelData.target ? "\n→ " + modelData.target : ""); font.family: "monospace"; font.pixelSize: 12 }
                    }
                    Choice {
                        visible: !!inspected.supported && !!(inspected.configuration || ({})).has_existing_colors && !inspected.managed
                        objectName: "replaceColors"
                        text: "Replace existing colors when connecting"
                        checked: resolution(inspected.id, "replace_colors") === true
                        enabled: !s.busy
                        onClicked: controller.resolve(inspected.id, "replace_colors", checked)
                        Layout.fillWidth: true
                    }
                    Choice {
                        visible: !!inspected.supported && (inspected.configuration || ({})).kind === "symlink" && !inspected.managed
                        objectName: "detachSymlink"
                        text: "Replace this symlink with a local copy"
                        checked: resolution(inspected.id, "symlink") === "detach"
                        enabled: !s.busy
                        onClicked: controller.resolve(inspected.id, "symlink", checked)
                        Layout.fillWidth: true
                    }
                    Body { visible: !!inspected.supported; Layout.fillWidth: true; text: "Included source files and symlink targets are preserved. Review the exact changes before applying, or export a theme to manage it yourself."; font.pixelSize: 12 }
                    Body { Layout.fillWidth: true; text: (inspected.configuration || ({})).scope || "Conventional paths and user processes only."; font.pixelSize: 11 }
                }
            }
            Command { text: "Done"; Layout.alignment: Qt.AlignRight; onClicked: inspector.close() }
        }
    }

    Dialog {
        id: reviewDialog
        objectName: "reviewDialog"
        anchors.centerIn: parent
        width: window.width - 48
        height: window.height - 48
        modal: true
        closePolicy: s.busy ? Popup.NoAutoClose : Popup.CloseOnEscape
        title: s.review.title || "Review changes"
        background: Rectangle { color: "#202228"; border.color: "#41434c"; radius: 10 }
        onRejected: controller.cancelReview()
        contentItem: ColumnLayout {
            spacing: 14
            ScrollView {
                Layout.fillWidth: true
                Layout.maximumHeight: 112
                Layout.preferredHeight: warningsColumn.implicitHeight
                contentWidth: availableWidth
                clip: true
                ColumnLayout {
                    id: warningsColumn
                    width: parent.width
                    Repeater { model: s.review.warnings || []; Body { required property string modelData; text: modelData; Layout.fillWidth: true; font.pixelSize: 12 } }
                }
            }
            ComboBox {
                id: fileSelect
                Layout.fillWidth: true
                model: s.review.changes || []
                textRole: "path"
                currentIndex: diffIndex
                onActivated: function(index) { diffIndex = index }
                Accessible.name: "Changed file"
            }
            Code {
                Layout.fillWidth: true
                Layout.fillHeight: true
                text: ((s.review.changes || [])[diffIndex] || ({})).diff || (s.review.kind === "undo" ? "Files already match their original state. Restore completes recovery by marking this transaction as undone." : "No file changes.")
            }
            RowLayout {
                Layout.fillWidth: true
                Body { Layout.fillWidth: true; text: (s.review.changes || []).length + " files · original configuration retained for undo"; font.pixelSize: 12 }
                Command { text: "Cancel"; enabled: !s.busy; onClicked: controller.cancelReview() }
                Command { objectName: "approveChanges"; text: s.review.kind === "undo" ? "Restore files" : "Apply changes"; primary: true; enabled: !s.busy && (s.review.kind === "undo" || (s.review.changes || []).length > 0); onClicked: controller.approve() }
            }
        }
    }

    Dialog {
        id: exportDialog
        objectName: "exportDialog"
        anchors.centerIn: parent
        width: Math.min(window.width - 64, 720)
        height: Math.min(window.height - 64, 620)
        modal: true
        title: "Export theme"
        background: Rectangle { color: "#202228"; border.color: "#41434c"; radius: 10 }
        contentItem: ColumnLayout {
            spacing: 16
            Body { Layout.fillWidth: true; text: "Use a standalone theme with your own configuration." }
            Body { Layout.fillWidth: true; visible: !!s.error; text: s.error; color: "#f0b8b5" }
            RowLayout {
                Repeater { model: ["kitty", "ghostty"]; Command { required property string modelData; text: modelData; enabled: !s.busy; onClicked: controller.renderExport(modelData) } }
                Item { Layout.fillWidth: true }
            }
            Code { Layout.fillWidth: true; Layout.fillHeight: true; text: s.exportText || "Choose a terminal format." }
            RowLayout {
                Item { Layout.fillWidth: true }
                Command { text: "Close"; enabled: !s.busy; onClicked: exportDialog.close() }
                Command { text: "Copy"; enabled: !!s.exportText && !s.busy; onClicked: controller.copyText(s.exportText) }
                Command { text: "Save as…"; primary: true; enabled: !!s.exportText && !s.busy; onClicked: exportPicker.open() }
            }
        }
    }
}
