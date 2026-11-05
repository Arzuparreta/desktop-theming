import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    required property QtObject controller
    readonly property var s: controller.state
    readonly property var imageFolder: controller.imageFolder
    readonly property int folderImageCount: imageList.count
    property int page: 0
    property var inspected: ({})
    property int diffIndex: 0
    property bool showAllComponents: false
    property bool problemDetails: false
    readonly property string latestActive: (s.overview.history.filter(h => ["applied", "prepared", "recovery-needed", "undoing"].indexOf(h.status) >= 0)[0] || ({})).id || ""
    readonly property bool recoveryNeeded: s.overview.history.some(h => ["prepared", "recovery-needed", "undoing"].indexOf(h.status) >= 0)
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

    function openWallpaperPicker() { if (controller.navigationFolderUrl) wallpaperPicker.currentFolder = controller.navigationFolderUrl; wallpaperPicker.open() }
    function closeWallpaperPicker() { wallpaperPicker.close() }
    function openFolderPicker() { if (controller.navigationFolderUrl) folderPicker.currentFolder = controller.navigationFolderUrl; folderPicker.open() }
    function closeFolderPicker() { folderPicker.close() }
    function selected(id) { return s.profile.components.indexOf(id) >= 0 }
    function evidence(c) {
        return (c.installed === null ? "Availability unknown" : c.installed ? "Available" : "Not found")
             + " · " + (c.running ? "Running" : "Not running")
             + (c.current_session ? " · Active session" : "")
             + (c.managed ? " · Theme configured" : "")
    }
    function inspect(c) { inspected = c; inspector.open() }
    function componentStatus(c) {
        if (c.wallpaper_provider && !c.supported) return "Managed by the reviewed wallpaper control when its session adapter is compatible."
        if (!c.supported) return "Theme changes are not supported yet."
        if (selected(c.id) && !c.managed) return "Will use this palette after review and apply."
        if (!selected(c.id) && c.managed) return "Will restore its previous colors after review and apply."
        if (c.managed) return "Appearance is configured. " + (c.capability || "")
        return c.installed !== false ? c.capability : "Not found on this computer. Nothing will be installed."
    }
    function sessionName() {
        const active = s.overview.components.find(c => c.current_session)
        const desktop = active ? active.name : s.overview.session.desktop
        return (desktop && desktop !== "Unknown" ? desktop : "Desktop") + (s.overview.session.type === "unknown" ? "" : " / " + (s.overview.session.type || "").toUpperCase())
    }
    function historyStatus(status) {
        return ({"applied": "Applied", "undone": "Restored", "rolled-back": "Cancelled after an error",
                 "prepared": "Interrupted — recovery needed", "recovery-needed": "Recovery needed",
                 "undoing": "Restoration interrupted"})[status] || "Unknown state"
    }
    function handleProblem() {
        switch (s.problem.action) {
        case "image": openWallpaperPicker(); break
        case "folder": openFolderPicker(); break
        case "save": exportPicker.open(); break
        case "review": controller.review(); break
        case "history": page = 2; break
        default: controller.refresh()
        }
    }

    Connections {
        target: controller
        function onChanged() {
            if (s.connection.id && !connectionDialog.visible) connectionDialog.open()
            if (!s.connection.id && connectionDialog.visible) connectionDialog.close()
            if (s.review.kind && !reviewDialog.visible) { diffIndex = 0; reviewDialog.open() }
            if (!s.review.kind && reviewDialog.visible) reviewDialog.close()
        }
    }
    Shortcut { sequence: "Ctrl+Return"; enabled: !s.busy && s.loaded && !reviewDialog.visible && !inspector.visible && !exportDialog.visible && !connectionDialog.visible; onActivated: controller.review() }
    Shortcut { sequence: "Ctrl+R"; enabled: !s.busy && !reviewDialog.visible && !inspector.visible && !exportDialog.visible && !connectionDialog.visible; onActivated: controller.refresh() }
    FileDialog {
        id: wallpaperPicker
        objectName: "wallpaperPicker"
        options: FileDialog.DontUseNativeDialog
        title: "Choose an image for the palette"
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)", "All files (*)"]
        onAccepted: controller.chooseWallpaper(selectedFile.toString())
    }
    FolderDialog {
        id: folderPicker
        objectName: "wallpaperFolderPicker"
        options: FolderDialog.DontUseNativeDialog
        title: "Choose a folder of images"
        onAccepted: controller.chooseFolder(selectedFolder.toString())
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
            Body { text: sessionName(); font.pixelSize: 12 }
            Command { text: "Check desktop"; quiet: true; enabled: !s.busy; onClicked: controller.refresh(); Accessible.description: "Check available applications again; keep your pending choices" }
        }
        RowLayout {
            spacing: 4
            Repeater {
                model: ["Appearance", "Components", "History"]
                Command { required property int index; required property string modelData; text: modelData; quiet: window.page !== index; onClicked: window.page = index }
            }
            Item { Layout.fillWidth: true }
            Body { visible: s.busy; text: s.activity; color: "#cad8cb"; Accessible.role: Accessible.StaticText }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#34363d" }
        Rectangle {
            visible: !!s.error || !!s.notice
            Layout.fillWidth: true
            implicitHeight: messageColumn.implicitHeight + 24
            color: s.error ? "#35282a" : "#263029"
            radius: 6
            ColumnLayout {
                id: messageColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 12
                spacing: 8
                Body { Layout.fillWidth: true; text: s.error ? s.problem.title || "Something needs attention" : s.notice; color: s.error ? "#f0b8b5" : "#d0dfd1" }
                Body { visible: !!s.error; Layout.fillWidth: true; text: s.problem.body || "" }
                RowLayout {
                    visible: !!s.error
                    Command { text: s.problem.label || "Check again"; onClicked: handleProblem(); enabled: !s.busy }
                    Command { text: problemDetails ? "Hide details" : "Show details"; quiet: true; onClicked: problemDetails = !problemDetails }
                }
                Body { visible: !!s.error && problemDetails; Layout.fillWidth: true; text: s.error; font.pixelSize: 12 }
            }
        }
        RowLayout {
            visible: recoveryNeeded
            Layout.fillWidth: true
            Body { Layout.fillWidth: true; text: "An earlier change was interrupted. Recover it before applying another palette."; color: "#e4c793" }
            Command { text: "Open recovery"; onClicked: page = 2 }
        }
        StackLayout {
            currentIndex: window.page
            Layout.fillWidth: true
            Layout.fillHeight: true

            RowLayout {
                spacing: 24
                ScrollView {
                    id: sourceScroll
                    objectName: "appearanceScroll"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 460
                    Layout.minimumWidth: 330
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: sourceScroll.availableWidth
                        spacing: 12
                        Label { text: "A palette for your desktop"; font.pixelSize: 19; color: "#e7e7eb" }
                        Body { visible: !imageFolder.path; Layout.fillWidth: true; text: "Choose colors, then select the applications to theme." }
                        WallpaperPreview {
                            id: wallpaperPreview
                            Layout.fillWidth: true
                            source: s.wallpaperUrl
                            availableHeight: sourceScroll.availableHeight
                        }
                        RowLayout {
                            Command { objectName: "chooseImage"; text: "Image…"; enabled: !s.busy && s.loaded; onClicked: openWallpaperPicker() }
                            Command { objectName: "chooseFolder"; text: "Folder…"; enabled: !s.busy && s.loaded; onClicked: openFolderPicker() }
                            Command { visible: !!s.profile.wallpaper; text: "Clear"; quiet: true; enabled: !s.busy; onClicked: controller.setOption("wallpaper", "") }
                        }
                        CheckBox {
                            objectName: "setDesktopWallpaper"
                            text: "Set as desktop wallpaper"
                            checked: !!s.profile.set_wallpaper
                            enabled: !s.busy && s.loaded && !!s.profile.wallpaper
                            onToggled: controller.setWallpaperEnabled(checked)
                            Accessible.description: "Wallpaper changes require review and approval"
                        }
                        Body { visible: !imageFolder.path; Layout.fillWidth: true; text: "Wallpaper changes require review and approval."; font.pixelSize: 12 }
                        ColumnLayout {
                            visible: !!imageFolder.path
                            Layout.fillWidth: true
                            spacing: 6
                            Body { Layout.fillWidth: true; text: "Folder images · " + folderImageCount; color: "#e7e7eb" }
                            Label {
                                Layout.fillWidth: true
                                text: imageFolder.path
                                textFormat: Text.PlainText
                                elide: Text.ElideMiddle
                                color: "#b9bbc4"
                                font.pixelSize: 11
                                Accessible.name: "Image folder: " + text
                                HoverHandler { id: folderHover }
                                ToolTip.visible: folderHover.hovered
                                ToolTip.text: text
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: Math.max(180, sourceScroll.availableHeight - wallpaperPreview.height - 260)
                                color: "#111318"
                                border.color: "#3c3e45"
                                radius: 6
                                ListView {
                                    id: imageList
                                    objectName: "wallpaperImageList"
                                    anchors.fill: parent
                                    anchors.margins: 4
                                    clip: true
                                    model: imageFolder.images
                                    spacing: 3
                                    boundsBehavior: Flickable.StopAtBounds
                                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                    Accessible.name: "Images in selected folder"
                                    Accessible.role: Accessible.List
                                    keyNavigationEnabled: true
                                    activeFocusOnTab: true
                                    Keys.onReturnPressed: if (currentItem && !s.busy) currentItem.clicked()
                                    Keys.onSpacePressed: if (currentItem && !s.busy) currentItem.clicked()
                                    delegate: ItemDelegate {
                                        id: imageRow
                                        objectName: "wallpaper-row-" + index
                                        required property int index
                                        required property var modelData
                                        width: imageList.width - 14
                                        height: 58
                                        padding: 6
                                        highlighted: s.profile.wallpaper === modelData.filePath
                                        enabled: !s.busy && s.loaded
                                        activeFocusOnTab: false
                                        Accessible.name: modelData.fileName
                                        Accessible.role: Accessible.ListItem
                                        Accessible.selected: highlighted
                                        Accessible.description: highlighted ? "Selected palette image" : "Choose this image for the palette"
                                        onClicked: { imageList.currentIndex = index; controller.chooseWallpaper(modelData.fileUrl) }
                                        Keys.onReturnPressed: clicked()
                                        contentItem: RowLayout {
                                            spacing: 10
                                            Rectangle {
                                                Layout.preferredWidth: 68
                                                Layout.preferredHeight: 46
                                                color: "#25272d"
                                                Image {
                                                    objectName: "wallpaper-thumbnail-" + imageRow.index
                                                    anchors.fill: parent
                                                    source: imageRow.modelData.fileUrl
                                                    sourceSize.width: 136
                                                    sourceSize.height: 92
                                                    fillMode: Image.PreserveAspectFit
                                                    asynchronous: true
                                                    autoTransform: true
                                                    cache: false
                                                }
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: imageRow.modelData.fileName
                                                textFormat: Text.PlainText
                                                elide: Text.ElideMiddle
                                                color: "#e7e7eb"
                                            }
                                            Label { visible: imageRow.highlighted; text: "✓"; color: "#cad8cb" }
                                        }
                                        background: Rectangle {
                                            radius: 4
                                            color: imageRow.highlighted ? "#303d35" : imageRow.hovered ? "#292c33" : "transparent"
                                            border.width: (imageRow.activeFocus || (imageList.activeFocus && imageList.currentIndex === imageRow.index)) ? 2 : 1
                                            border.color: (imageRow.activeFocus || (imageList.activeFocus && imageList.currentIndex === imageRow.index)) ? "#cad8cb" : imageRow.highlighted ? "#78977d" : "transparent"
                                        }
                                        ToolTip.visible: hovered
                                        ToolTip.text: modelData.fileName
                                    }
                                    Body {
                                        anchors.centerIn: parent
                                        width: parent.width - 24
                                        visible: folderImageCount === 0
                                        text: "No supported images found. Choose another folder or check its permissions."
                                    }
                                }
                            }
                        }
                        Label {
                            Layout.fillWidth: true
                            visible: !!s.profile.wallpaper && !imageFolder.path
                            text: s.profile.wallpaper
                            textFormat: Text.PlainText
                            elide: Text.ElideMiddle
                            color: "#b9bbc4"
                            font.pixelSize: 11
                            Accessible.name: "Selected image: " + text
                            HoverHandler { id: selectedImageHover }
                            ToolTip.visible: selectedImageHover.hovered
                            ToolTip.text: text
                        }
                    }
                }
                ScrollView {
                    id: previewScroll
                    Layout.fillWidth: true
                    Layout.preferredWidth: 400
                    Layout.minimumWidth: 310
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: previewScroll.availableWidth
                        spacing: 12
                        RowLayout {
                            Body { text: "Terminal preview"; color: "#e7e7eb" }
                            Item { Layout.fillWidth: true }
                            Body { text: preview.effective ? (preview.effective === "safe" ? "Default colors" : "Image colors") + " / " + (preview.polarity === "light" ? "Light" : "Dark") : ""; font.pixelSize: 11 }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: terminalContent.implicitHeight + 24
                            radius: 8
                            color: special.background
                            border.color: "#3c3e45"
                            ColumnLayout {
                                id: terminalContent
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 6
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
                            }
                        }
                        GridLayout {
                            Layout.alignment: Qt.AlignLeft
                            columns: 8
                            columnSpacing: 7
                            rowSpacing: 7
                            Repeater {
                                model: 16
                                Rectangle {
                                    required property int index
                                    implicitWidth: 28
                                    implicitHeight: 28
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
                        GridLayout {
                            Layout.fillWidth: true
                            columns: previewScroll.availableWidth >= 410 ? 2 : 1
                            columnSpacing: 16
                            rowSpacing: 10
                            ColumnLayout {
                                Body { text: "Appearance"; color: "#e7e7eb" }
                                RowLayout {
                                    Repeater {
                                        model: ["dark", "light"]
                                        Command { required property string modelData; text: modelData === "dark" ? "Dark" : "Light"; primary: s.profile.polarity === modelData; enabled: !s.busy && s.loaded; onClicked: controller.setOption("polarity", modelData) }
                                    }
                                }
                            }
                            ColumnLayout {
                                Body { text: "Palette"; color: "#e7e7eb" }
                                RowLayout {
                                    Repeater {
                                        model: ["adaptive", "safe"]
                                        Command { required property string modelData; text: modelData === "adaptive" ? "From image" : "Default colors"; primary: (s.profile.wallpaper ? s.profile.mode : "safe") === modelData; enabled: !s.busy && s.loaded && (modelData !== "adaptive" || !!s.profile.wallpaper); onClicked: controller.setOption("mode", modelData) }
                                    }
                                }
                            }
                        }
                        Body { Layout.fillWidth: true; text: !s.profile.wallpaper ? "Default colors are shown until you choose an image." : preview.reason || "Colors are checked for terminal contrast and distinction."; font.pixelSize: 12 }
                        RowLayout {
                            Command { text: "Export theme…"; quiet: true; enabled: !s.busy && !!preview.special; onClicked: { exportDialog.open() } }
                            Item { Layout.fillWidth: true }
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
                    Body { Layout.fillWidth: true; text: "Choose which applications use this palette. Changes are applied only after review."; bottomPadding: 20 }
                    Repeater {
                        model: s.overview.components.filter(c => c.supported || showAllComponents || c.installed || c.running || c.configs.some(f => f.exists))
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
                                    Body { visible: modelData.supported; Layout.fillWidth: true; text: componentStatus(modelData); font.pixelSize: 12 }
                                }
                                Command { objectName: "details-" + modelData.id; text: "Details…"; quiet: true; enabled: !s.busy; onClicked: inspect(modelData) }
                                Choice {
                                    visible: modelData.supported
                                    objectName: "connect-" + modelData.id
                                    text: modelData.id === "swaybg" ? "Use image" : ["gnome", "xfce"].indexOf(modelData.id) >= 0 ? "Use appearance" : "Use palette"
                                    checked: selected(modelData.id)
                                    enabled: !s.busy && s.loaded && (modelData.installed !== false || checked)
                                    onClicked: { controller.selectComponent(modelData.id, !selected(modelData.id)); checked = Qt.binding(function() { return selected(modelData.id) }) }
                                    Accessible.name: text + " in " + modelData.name
                                }
                                Body { visible: !modelData.supported; text: modelData.category === "Wallpaper" ? "Automatic wallpaper" : "Detection only"; font.pixelSize: 12; Layout.preferredWidth: 100 }
                            }
                            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#2c2e35" }
                        }
                    }
                    Command { text: showAllComponents ? "Hide unavailable components" : "Show all checked components"; quiet: true; onClicked: showAllComponents = !showAllComponents }
                    Body { Layout.fillWidth: true; text: "Detection checks common configuration locations and running applications. Custom launch options and sandboxed apps may differ."; font.pixelSize: 11; topPadding: 20 }
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
                                    Body { text: historyStatus(modelData.status) + " · " + modelData.files + " files · " + (modelData.components.join(", ") || "Palette profile"); font.pixelSize: 12 }
                                    Body { visible: !pending && modelData.status === "applied" && modelData.id !== latestActive; text: "Undo the more recent changes first."; font.pixelSize: 12 }
                                }
                                Command { text: pending ? "Recover…" : "Undo…"; visible: pending || modelData.status === "applied"; enabled: !s.busy && modelData.id === latestActive; onClicked: controller.reviewUndo(modelData.id, pending) }
                            }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#34363d" }
        RowLayout {
            Layout.fillWidth: true
            Body { Layout.fillWidth: true; text: s.profile.components.length ? "Use palette in: " + s.profile.components.join(", ") : "No applications selected · palette only"; font.pixelSize: 12 }
            Command { objectName: "reviewChanges"; text: "Review changes"; primary: true; enabled: !s.busy && s.loaded; onClicked: controller.review() }
        }
    }

    ConnectionDialog {
        id: connectionDialog
        controller: window.controller
        windowWidth: window.width
        windowHeight: window.height
        onExportRequested: function(component) {
            controller.cancelConnection()
            exportDialog.open()
            controller.renderExport(component)
        }
    }

    Dialog {
        id: inspector
        objectName: "inspector"
        anchors.centerIn: parent
        width: Math.min(window.width - 64, 720)
        height: Math.min(window.height - 64, 680)
        modal: true
        title: (inspected.name || "Component") + " — configuration details"
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
                    Body { Layout.fillWidth: true; text: inspected.id === "swaybg" ? "Select Use image to configure Sway's background for your next manual reload. No running process is replaced."
                        : inspected.category === "Wallpaper" ? "Wallpaper changes are selected beside the image. The compatible method is detected during review; an installed tool alone does not establish support."
                        : inspected.supported ? "Select the appearance control in the components list. These details are read-only." : "Detected only. Theme changes for this component are not supported yet." }
                    Body { Layout.fillWidth: true; text: inspected.capability || "" }
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
        onOpened: technicalNotes.checked = false
        background: Rectangle { color: "#202228"; border.color: "#41434c"; radius: 10 }
        onRejected: controller.cancelReview()
        contentItem: ColumnLayout {
            spacing: 14
            ScrollView {
                Layout.fillWidth: true
                Layout.maximumHeight: 190
                Layout.preferredHeight: warningsColumn.implicitHeight
                contentWidth: availableWidth
                clip: true
                ColumnLayout {
                    id: warningsColumn
                    width: parent.width
                    Repeater { model: s.review.summary || []; Body { required property string modelData; text: modelData; Layout.fillWidth: true; font.pixelSize: 12 } }
                }
            }
            ComboBox {
                id: fileSelect
                Layout.fillWidth: true
                model: s.review.changes || []
                textRole: "label"
                currentIndex: diffIndex
                onActivated: function(index) { diffIndex = index }
                Accessible.name: "Changed file"
            }
            Body { Layout.fillWidth: true; text: ((s.review.changes || [])[diffIndex] || ({})).path || ""; font.pixelSize: 11 }
            Code {
                Layout.fillWidth: true
                Layout.fillHeight: true
                text: ((s.review.changes || [])[diffIndex] || ({})).diff || (s.review.kind === "undo" ? "Files already match their original state. Restore completes recovery by marking this transaction as undone." : "No file changes.")
            }
            Command { id: technicalNotes; quiet: true; checkable: true; text: checked ? "Hide technical notes" : "Show technical notes"; visible: !!(s.review.warnings || []).length }
            Body { visible: technicalNotes.checked; Layout.fillWidth: true; text: (s.review.warnings || []).join("\n"); font.pixelSize: 11 }
            RowLayout {
                Layout.fillWidth: true
                Body { Layout.fillWidth: true; text: (s.review.changes || []).length + " changes · " + (s.review.kind === "undo" ? "Restoration is checked for conflicts" : "You can undo these changes from History"); font.pixelSize: 12 }
                Command { text: "Cancel"; enabled: !s.busy; onClicked: controller.cancelReview() }
                Command { objectName: "approveChanges"; text: s.review.kind === "undo" ? "Restore changes" : "Apply changes"; primary: true; enabled: !s.busy && (s.review.kind === "undo" || (s.review.changes || []).length > 0); onClicked: controller.approve() }
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
            Body { Layout.fillWidth: true; text: "Save or copy a theme file for your own configuration. Export does not connect an application or change its settings." }
            Body { Layout.fillWidth: true; visible: !!s.notice; text: s.notice; color: "#d0dfd1" }
            Body { Layout.fillWidth: true; visible: !!s.error; text: (s.problem.title || "") + "\n" + (s.problem.body || ""); color: "#f0b8b5" }
            RowLayout {
                ComboBox {
                    id: exportFormat
                    objectName: "exportFormat"
                    Layout.preferredWidth: 250
                    model: s.overview.components.filter(c => c.supported && ["gnome", "xfce"].indexOf(c.id) < 0)
                    textRole: "name"
                    enabled: !s.busy
                    onActivated: controller.renderExport(model[currentIndex].id)
                }
                Command { text: "Preview format"; enabled: !s.busy && exportFormat.currentIndex >= 0; onClicked: controller.renderExport(exportFormat.model[exportFormat.currentIndex].id) }
                Item { Layout.fillWidth: true }
            }
            Code { Layout.fillWidth: true; Layout.fillHeight: true; text: s.exportText || "Choose a format to preview, copy or save." }
            RowLayout {
                Item { Layout.fillWidth: true }
                Command { text: "Close"; enabled: !s.busy; onClicked: exportDialog.close() }
                Command { text: "Copy"; enabled: !!s.exportText && !s.busy; onClicked: controller.copyText(s.exportText) }
                Command { text: "Save as…"; primary: true; enabled: !!s.exportText && !s.busy; onClicked: exportPicker.open() }
            }
        }
    }
}
