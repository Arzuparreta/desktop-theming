import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    required property QtObject controller
    readonly property var s: controller.state
    readonly property var imageFolder: controller.imageFolder
    readonly property int folderImageCount: themePage.imageCount
    // Quick mode: opened to change the theme. Starts on the Theme page with
    // search focused; Escape closes the window without applying anything.
    property bool dailyMode: false
    property int page: 0
    readonly property bool canNavigate: !s.busy && s.loaded && !reviewDialog.visible && !inspector.visible && !exportDialog.visible && !connectionDialog.visible && !accessDialog.visible && !activationDialog.visible && !shortcutsDialog.visible && !moreMenu.visible && !wallpaperPicker.visible && !folderPicker.visible && !exportPicker.visible
    onDailyModeChanged: {
        if (dailyMode) page = 0
        if (dailyMode && canNavigate) Qt.callLater(themePage.focusSearch)
    }
    Component.onCompleted: if (dailyMode) { width = 980; Qt.callLater(themePage.focusSearch) }
    property var inspected: ({})
    property bool problemDetails: false
    readonly property string latestActive: (s.overview.history.filter(h => ["applied", "prepared", "recovery-needed", "undoing"].indexOf(h.status) >= 0)[0] || ({})).id || ""
    readonly property bool recoveryNeeded: s.overview.history.some(h => ["prepared", "recovery-needed", "undoing"].indexOf(h.status) >= 0)
    readonly property bool compactHeader: width < 900
    readonly property var addedApps: s.hasApplied ? s.profile.components.filter(id => s.applied.components.indexOf(id) < 0) : []
    readonly property var removedApps: s.hasApplied ? s.applied.components.filter(id => s.profile.components.indexOf(id) < 0) : []
    function componentName(id) { const c = s.overview.components.find(item => item.id === id); return c ? c.name : id }
    function themeName(t) { return t ? (t.wallpaper ? fileName(t.wallpaper) : "Default colors") + " · " + (t.polarity === "light" ? "Light" : "Dark") : "" }
    width: 1120
    height: 780
    minimumWidth: 760
    minimumHeight: 600
    visible: true
    title: "Linux Theming"
    color: Theme.window
    font.family: "sans-serif"
    font.pixelSize: Theme.body
    palette.window: Theme.window
    palette.windowText: Theme.text
    palette.text: Theme.text
    palette.base: Theme.surface
    palette.alternateBase: Theme.raised
    palette.button: Theme.raised
    palette.buttonText: Theme.text
    palette.highlight: Theme.accentBorder
    palette.highlightedText: Theme.text
    palette.toolTipBase: Theme.raised
    palette.toolTipText: Theme.text
    palette.placeholderText: Theme.textFaint
    palette.mid: Theme.borderStrong
    palette.dark: Theme.border
    palette.light: Theme.hover
    onClosing: function(close) { if (s.busy) { close.accepted = false; controller.explainBusyClose() } }

    function openWallpaperPicker() { if (controller.navigationFolderUrl) wallpaperPicker.currentFolder = controller.navigationFolderUrl; wallpaperPicker.open() }
    function closeWallpaperPicker() { wallpaperPicker.close() }
    function openFolderPicker() { if (controller.navigationFolderUrl) folderPicker.currentFolder = controller.navigationFolderUrl; folderPicker.open() }
    function closeFolderPicker() { folderPicker.close() }
    function setDailyMode(enabled) { dailyMode = enabled }
    function fileName(path) { return path ? path.split("/").pop() : "" }
    function evidence(c) {
        return (c.installed === null ? "Availability unknown" : c.installed ? "Installed" : "Not found")
             + " · " + (c.running ? "Running" : "Not running")
             + (c.current_session ? " · Active session" : "")
             + (c.managed ? " · Uses the palette" : "")
    }
    function inspect(c) { inspected = c; inspector.open() }
    function sessionName() {
        const active = s.overview.components.find(c => c.current_session)
        const desktop = active ? active.name : s.overview.session.desktop
        const type = s.overview.session.type
        return (desktop && desktop !== "Unknown" ? desktop : "Desktop") + (type && type !== "unknown" ? " · " + (type === "x11" ? "X11" : type.charAt(0).toUpperCase() + type.slice(1)) : "")
    }
    function handleProblem() {
        switch (s.problem.action) {
        case "image": openWallpaperPicker(); break
        case "folder": openFolderPicker(); break
        case "save": exportPicker.open(); break
        case "review": controller.review(); break
        case "history": page = 2; break
        case "access": controller.refreshLauncher(); accessDialog.open(); break
        default: controller.refresh()
        }
    }
    function openExport() { exportDialog.open(); if (!s.exportText && exportFormat.count > 0) controller.renderExport(exportFormat.model[Math.max(0, exportFormat.currentIndex)].id) }

    Connections {
        target: window.controller
        function onChanged() {
            if (s.connection.id && !connectionDialog.visible) connectionDialog.open()
            if (!s.connection.id && connectionDialog.visible) connectionDialog.close()
            if (s.review.kind && !reviewDialog.visible) reviewDialog.open()
            if (!s.review.kind && reviewDialog.visible) reviewDialog.close()
        }
    }
    Shortcut { sequence: "Ctrl+Return"; enabled: window.canNavigate && !recoveryNeeded; onActivated: controller.review() }
    Shortcut { sequence: "Ctrl+R"; enabled: window.canNavigate && !s.scanning; onActivated: controller.refresh() }
    Shortcut { sequence: "Ctrl+F"; enabled: window.canNavigate; onActivated: { page = 0; themePage.focusSearch() } }
    // Escape clears the search, returns to the Theme page, then closes a quick theme change.
    Shortcut { sequence: "Escape"; enabled: window.canNavigate; onActivated: { if (page !== 0) page = 0; else if (!themePage.handleEscape() && dailyMode) window.close() } }
    Shortcut { sequence: "Ctrl+Shift+R"; enabled: window.canNavigate; onActivated: controller.chooseRandom() }
    Shortcut { sequence: "Alt+D"; enabled: window.canNavigate; onActivated: controller.setOption("polarity", s.profile.polarity === "dark" ? "light" : "dark") }
    Shortcut { sequence: "Alt+M"; enabled: window.canNavigate; onActivated: controller.setOption("mode", s.profile.mode === "adaptive" ? "safe" : "adaptive") }
    Shortcut { sequence: "Ctrl+Z"; enabled: window.canNavigate && !(window.activeFocusItem instanceof TextInput) && !(window.activeFocusItem instanceof TextEdit); onActivated: controller.undoLatest() }
    Shortcut { sequence: "Ctrl+1"; enabled: window.canNavigate; onActivated: page = 0 }
    Shortcut { sequence: "Ctrl+2"; enabled: window.canNavigate; onActivated: page = 1 }
    Shortcut { sequence: "Ctrl+3"; enabled: window.canNavigate; onActivated: page = 2 }
    Shortcut { sequences: ["F1", "Ctrl+?"]; enabled: window.canNavigate; onActivated: shortcutsDialog.open() }
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
        spacing: 0

        // Header: identity, sections, desktop status and secondary actions.
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 56
            color: Theme.window
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 14
                spacing: 6
                Image { source: "icon.svg"; sourceSize: Qt.size(26, 26); Layout.preferredWidth: 26; Layout.preferredHeight: 26; Accessible.ignored: true }
                Text {
                    visible: !window.compactHeader
                    Layout.leftMargin: 4
                    Layout.rightMargin: 18
                    text: "Linux Theming"
                    color: Theme.text
                    font.pixelSize: Theme.title
                    font.weight: Font.DemiBold
                }
                Item { visible: window.compactHeader; implicitWidth: 10 }
                Repeater {
                    model: [{ label: "Theme", icon: "palette", name: "tabTheme" },
                            { label: "Applications", icon: "apps", name: "tabApplications" },
                            { label: "History", icon: "history", name: "tabHistory" }]
                    Button {
                        id: tab
                        required property var modelData
                        required property int index
                        objectName: modelData.name
                        readonly property bool current: window.page === index
                        Layout.fillHeight: true
                        hoverEnabled: true
                        activeFocusOnTab: true
                        leftPadding: 12
                        rightPadding: 12
                        readonly property bool flagged: (index === 1 && (window.addedApps.length > 0 || window.removedApps.length > 0)) || (index === 2 && window.recoveryNeeded)
                        Accessible.role: Accessible.PageTab
                        Accessible.name: modelData.label + (flagged ? (index === 2 ? ", recovery needed" : ", changes waiting for review") : "")
                        Accessible.selected: current
                        ToolTip.visible: hovered
                        ToolTip.text: Accessible.name + " · Ctrl+" + (index + 1)
                        ToolTip.delay: 700
                        onClicked: window.page = index
                        contentItem: RowLayout {
                            spacing: 7
                            Icon { name: tab.modelData.icon; size: 16; color: tab.current ? Theme.accent : Theme.textMuted }
                            Text {
                                text: tab.modelData.label
                                color: tab.current ? Theme.text : tab.hovered ? Theme.text : Theme.textMuted
                                font.pixelSize: Theme.body
                                font.weight: tab.current ? Font.DemiBold : Font.Normal
                            }
                            Rectangle {
                                visible: tab.flagged
                                implicitWidth: 7
                                implicitHeight: 7
                                radius: 4
                                color: tab.index === 2 ? Theme.danger : Theme.warning
                            }
                        }
                        background: Item {
                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                height: 2
                                radius: 1
                                color: tab.current ? Theme.accent : "transparent"
                            }
                            Rectangle {
                                anchors.fill: parent
                                anchors.topMargin: 10
                                anchors.bottomMargin: 10
                                radius: Theme.radiusSmall
                                color: tab.hovered && !tab.current ? Theme.raised : "transparent"
                                border.width: tab.visualFocus ? 2 : 0
                                border.color: Theme.focus
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                Chip {
                    visible: !window.compactHeader && s.loaded
                    text: sessionName()
                    tone: "neutral"
                    Accessible.name: "Current session: " + text
                }
                Command {
                    objectName: "checkDesktop"
                    quiet: true
                    iconName: "refresh"
                    text: s.scanning ? "Checking…" : ""
                    enabled: !s.busy && !s.scanning
                    hint: "Ctrl+R"
                    Accessible.name: "Check desktop again"
                    Accessible.description: "Look for applications again; your pending choices are kept"
                    onClicked: controller.refresh()
                }
                Command {
                    id: moreButton
                    objectName: "moreActions"
                    quiet: true
                    iconName: "menu-dots"
                    Accessible.name: "More actions"
                    onClicked: moreMenu.open()
                    Menu {
                        id: moreMenu
                        y: moreButton.height + 4
                        x: moreButton.width - width
                        MenuItem { text: "Export theme file…"; enabled: !s.busy && !!(s.palette || ({})).special; onTriggered: window.openExport() }
                        MenuItem { text: "Menu entry and shortcut…"; enabled: !s.busy; onTriggered: { controller.refreshLauncher(); accessDialog.open() } }
                        MenuSeparator {}
                        MenuItem { text: "Keyboard shortcuts    F1"; onTriggered: shortcutsDialog.open() }
                    }
                }
            }
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: Theme.border }
        }

        // Messages that need attention appear above every page.
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.topMargin: visible ? 14 : 0
            spacing: 8
            visible: window.recoveryNeeded || (!!s.migration.needed && !window.recoveryNeeded) || !!s.error || !!s.notice
            Banner {
                Layout.fillWidth: true
                visible: window.recoveryNeeded
                tone: "danger"
                title: "An earlier change was interrupted"
                body: "Recover it before applying another theme. Recovery shows exactly what will be restored."
                Command { text: "Open recovery"; onClicked: window.page = 2 }
            }
            Banner {
                Layout.fillWidth: true
                visible: !!s.migration.needed && !window.recoveryNeeded
                tone: "warning"
                title: "Desktop Theming data can be moved"
                body: s.migration.summary || ""
                Command { objectName: "reviewDataMigration"; text: "Review migration…"; enabled: !s.busy; onClicked: controller.reviewMigration() }
            }
            Banner {
                objectName: "messageBanner"
                Layout.fillWidth: true
                visible: !!s.error || !!s.notice
                tone: s.error ? "danger" : "success"
                title: s.error ? s.problem.title || "Something needs attention" : s.notice
                body: s.error ? (s.problem.body || "") + (problemDetails ? "\n\n" + s.error : "") : ""
                Command { visible: !!s.error; compact: true; text: s.problem.label || "Check again"; onClicked: handleProblem(); enabled: !s.busy }
                Command { visible: !!s.error; compact: true; quiet: true; text: problemDetails ? "Hide details" : "Details"; onClicked: problemDetails = !problemDetails }
                Command { visible: !s.error && s.activation.length > 0; compact: true; text: "How to see the colors…"; onClicked: activationDialog.open() }
            }
        }

        StackLayout {
            currentIndex: window.page
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 20
            Layout.bottomMargin: 14

            ThemePage {
                id: themePage
                controller: window.controller
                onImageRequested: window.openWallpaperPicker()
                onFolderRequested: window.openFolderPicker()
                onApplicationsRequested: window.page = 1
                onExportRequested: window.openExport()
                onUndoRequested: if (window.latestActive && !window.recoveryNeeded && window.canNavigate) controller.undoLatest()
            }
            ApplicationsPage {
                id: applicationsPage
                controller: window.controller
                onDetailsRequested: function(component) { window.inspect(component) }
            }
            HistoryPage {
                controller: window.controller
                latestActive: window.latestActive
                onPreviewRequested: function(wallpaper, polarity, mode) { window.controller.previewTheme(wallpaper, polarity, mode); window.page = 0 }
            }
        }

        // Status and decision bar: applied theme, preview candidate, actions.
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 68
            color: Theme.surface
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 1; color: Theme.border }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                spacing: 12
                Rectangle {
                    Layout.preferredWidth: 56
                    Layout.preferredHeight: 34
                    radius: 4
                    color: Theme.canvas
                    clip: true
                    visible: !!s.profile.wallpaper || s.hasApplied
                    Image {
                        anchors.fill: parent
                        source: s.wallpaperUrl
                        sourceSize: Qt.size(112, 68)
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }
                    Row {
                        visible: !s.profile.wallpaper
                        anchors.centerIn: parent
                        spacing: 2
                        Repeater { model: [1, 2, 4, 5]; Rectangle { required property int modelData; width: 7; height: 14; radius: 2; color: (s.palette.colors || ({}))["color" + modelData] || Theme.hover } }
                    }
                }
                ColumnLayout {
                    objectName: "appliedReference"
                    Layout.fillWidth: true
                    spacing: 3
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            Layout.fillWidth: true
                            Layout.maximumWidth: implicitWidth
                            text: (s.profile.wallpaper ? fileName(s.profile.wallpaper) : "Default colors") + " · " + (s.profile.polarity === "light" ? "Light" : "Dark")
                            color: Theme.text
                            font.pixelSize: Theme.body
                            font.weight: Font.DemiBold
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                        }
                        Chip {
                            objectName: "draftState"
                            text: s.pending ? (s.hasApplied ? "Not applied" : "Preview") : s.hasApplied ? "Applied" : "Preview"
                            tone: s.pending ? "warning" : s.hasApplied ? "accent" : "neutral"
                        }
                        Item { Layout.fillWidth: true }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: s.pending && s.hasApplied
                            ? "Applied now: " + themeName(s.applied)
                              + (window.addedApps.length ? " · adds " + window.addedApps.map(componentName).join(", ") : "")
                              + (window.removedApps.length ? " · restores " + window.removedApps.map(componentName).join(", ") : "")
                              + (s.profile.set_wallpaper && s.profile.wallpaper && s.profile.wallpaper !== s.applied.wallpaper ? " · sets wallpaper" : "")
                            : !s.hasApplied ? "Nothing applied by Linux Theming yet"
                            : s.profile.components.length ? "Used by " + s.profile.components.map(componentName).join(", ") : "Palette only"
                        color: Theme.textFaint
                        font.pixelSize: Theme.caption
                        elide: Text.ElideMiddle
                        textFormat: Text.PlainText
                    }
                }
                Command {
                    objectName: "discardDraft"
                    visible: s.pending && s.hasApplied
                    quiet: true
                    text: "Discard"
                    enabled: !s.busy
                    Accessible.description: "Return to the applied theme and applications"
                    onClicked: controller.discardDraft()
                }
                Command {
                    objectName: "undoLatest"
                    // Undo reverts files on disk; keep it apart from discarding a draft.
                    visible: !!window.latestActive && !window.recoveryNeeded
                    quiet: s.pending
                    iconName: "undo"
                    text: s.pending && window.width < 980 ? "Undo…" : "Undo last apply…"
                    enabled: !s.busy
                    Accessible.name: "Undo last apply"
                    Accessible.description: "Review restoring the configuration from before " + themeName(s.applied) + " was applied. Ctrl+Z"
                    ToolTip.visible: hovered
                    ToolTip.text: "Shows exactly what will be restored before anything changes · Ctrl+Z"
                    ToolTip.delay: 500
                    onClicked: controller.undoLatest()
                }
                Command {
                    objectName: "chooseApplications"
                    visible: !s.profile.components.length && window.page !== 1 && s.loaded
                    primary: !!s.profile.wallpaper
                    iconName: "apps"
                    text: "Choose applications"
                    onClicked: window.page = 1
                }
                Command {
                    objectName: "reviewChanges"
                    primary: (s.pending || !s.hasApplied) && (s.profile.components.length > 0 || window.page === 1)
                    text: s.busy ? s.activity : s.pending || !s.hasApplied ? "Review changes" : "Review again"
                    hint: s.busy ? "" : "Ctrl+Enter"
                    enabled: !s.busy && s.loaded && !recoveryNeeded
                    Accessible.description: "Prepare the exact changes for approval. Nothing is applied yet."
                    onClicked: controller.review()
                }
            }
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

    ReviewDialog {
        id: reviewDialog
        controller: window.controller
        windowWidth: window.width
        windowHeight: window.height
    }

    Sheet {
        id: inspector
        objectName: "inspector"
        width: Math.min(window.width - 40, 720)
        height: Math.min(window.height - 40, 640)
        title: (inspected.name || "Application") + " details"
        subtitle: evidence(inspected)
        contentItem: ColumnLayout {
            spacing: 14
            ScrollView {
                id: inspectorScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true
                ColumnLayout {
                    width: inspectorScroll.availableWidth
                    spacing: 12
                    Body {
                        Layout.fillWidth: true
                        color: Theme.text
                        text: inspected.id === "swaybg" ? "Turn on the switch in Applications to configure Sway's background for your next manual reload. No running process is replaced."
                            : inspected.category === "Wallpaper" ? "Wallpaper changes are chosen on the Theme page. The compatible method is detected during review; an installed tool alone does not establish support."
                            : inspected.supported ? "Use the switch in Applications to connect it. These details are read-only." : "Detected only. Theme changes for this application are not supported yet." }
                    Body { Layout.fillWidth: true; visible: !!text; text: inspected.capability || "" }
                    Text { text: "Configuration files"; color: Theme.text; font.pixelSize: Theme.body; font.weight: Font.DemiBold; visible: (inspected.configs || []).length > 0 }
                    Repeater {
                        model: inspected.configs || []
                        Body { required property var modelData; Layout.fillWidth: true; text: modelData.path + (modelData.symlink ? " → " + modelData.target : "") + (modelData.exists ? "" : " (missing)"); font.family: Theme.mono; font.pixelSize: Theme.caption }
                    }
                    Repeater {
                        model: (inspected.configuration || ({})).issues || []
                        Body { required property string modelData; Layout.fillWidth: true; text: modelData; color: Theme.danger }
                    }
                    Text { visible: !!inspected.supported; text: "Existing color settings"; color: Theme.text; font.pixelSize: Theme.body; font.weight: Font.DemiBold }
                    Body { visible: !!inspected.supported && !((inspected.configuration || ({})).sources || []).length; text: "None found in the usual configuration files." }
                    Repeater {
                        model: (inspected.configuration || ({})).sources || []
                        Body { required property var modelData; Layout.fillWidth: true; text: modelData.path + ":" + modelData.line + "\n" + modelData.directive + " " + modelData.value + (modelData.target ? "\n→ " + modelData.target : ""); font.family: Theme.mono; font.pixelSize: Theme.caption }
                    }
                    Body { Layout.fillWidth: true; text: (inspected.configuration || ({})).scope || "Checked usual paths and your own processes only."; font.pixelSize: Theme.caption; color: Theme.textFaint }
                }
            }
            Command { text: "Done"; Layout.alignment: Qt.AlignRight; onClicked: inspector.close() }
        }
    }

    Sheet {
        id: activationDialog
        width: Math.min(680, window.width - 40)
        height: Math.min(560, window.height - 40)
        title: "How to see the new colors"
        subtitle: "The files were saved. Linux Theming has not signalled, restarted or observed these running applications."
        contentItem: ColumnLayout {
            spacing: 12
            ScrollView {
                id: activationScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true
                ColumnLayout {
                    width: activationScroll.availableWidth
                    spacing: 8
                    Repeater {
                        model: s.activation
                        Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: activationRow.implicitHeight + 22
                            radius: Theme.radius
                            color: Theme.raised
                            ColumnLayout {
                                id: activationRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: 14
                                spacing: 4
                                RowLayout {
                                    Text { text: modelData.name; color: Theme.text; font.pixelSize: Theme.body; font.weight: Font.DemiBold }
                                    Chip { text: "Saved"; tone: "accent"; iconName: "check" }
                                }
                                Body { Layout.fillWidth: true; text: modelData.message; font.pixelSize: Theme.caption + 1 }
                            }
                        }
                    }
                }
            }
            Command { text: "Close"; Layout.alignment: Qt.AlignRight; onClicked: activationDialog.close() }
        }
    }

    Sheet {
        id: accessDialog
        objectName: "accessDialog"
        width: Math.min(660, window.width - 40)
        height: Math.min(window.height - 40, implicitHeight)
        title: "Menu entry and shortcut"
        subtitle: "Add a reversible entry to your application menu. Choose your own shortcut in your desktop's keyboard settings; no key binding is changed here."
        contentItem: ColumnLayout {
            spacing: 14
            Banner {
                Layout.fillWidth: true
                visible: !!s.migration.needed
                tone: "warning"
                title: "Data migration available"
                body: s.migration.summary || ""
                Command { objectName: "migrateIdentity"; text: "Review migration…"; enabled: !s.busy; onClicked: { accessDialog.close(); controller.reviewMigration() } }
            }
            Banner { Layout.fillWidth: true; visible: !!s.launcher.error; tone: "warning"; title: s.launcher.error || "" }
            Banner {
                Layout.fillWidth: true
                visible: !!s.launcher.repair_needed
                tone: "warning"
                title: "The menu entry needs repair"
                body: "Open this AppImage from its stable location and choose Update entry."
            }
            Command { visible: !!s.launcher.interrupted; text: "Recover interrupted menu change…"; onClicked: { accessDialog.close(); controller.recoverLauncher() } }
            Body { Layout.fillWidth: true; text: "Use this command for a keyboard shortcut. It opens Linux Theming ready to change the theme; opening it again brings the existing window forward where your desktop allows it." }
            Code { Layout.fillWidth: true; Layout.preferredHeight: 64; text: s.launcher.command || "Open the AppImage from a stable location to register a menu entry." }
            RowLayout {
                Command { text: "Copy command"; compact: true; enabled: !!s.launcher.command; onClicked: controller.copyText(s.launcher.command) }
                Item { Layout.fillWidth: true }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
            RowLayout {
                Command { text: "Close"; onClicked: accessDialog.close() }
                Item { Layout.fillWidth: true }
                Command { objectName: "removeLauncher"; text: "Remove entry…"; danger: true; enabled: !s.busy && !!s.launcher.registered; onClicked: { accessDialog.close(); controller.reviewLauncher(true) } }
                Command { objectName: "registerLauncher"; text: s.launcher.registered ? "Update entry…" : "Add to menu…"; primary: true; enabled: !s.busy && !!s.launcher.available; onClicked: { accessDialog.close(); controller.reviewLauncher(false) } }
            }
        }
    }

    Sheet {
        id: exportDialog
        objectName: "exportDialog"
        width: Math.min(window.width - 40, 760)
        height: Math.min(window.height - 40, 640)
        title: "Export theme file"
        subtitle: "Save or copy a theme file for your own configuration. Exporting does not connect an application or change its settings."
        contentItem: ColumnLayout {
            spacing: 12
            Banner { Layout.fillWidth: true; visible: !!s.notice && exportDialog.visible; tone: "success"; title: s.notice }
            Banner { Layout.fillWidth: true; visible: !!s.error && exportDialog.visible; tone: "danger"; title: s.problem.title || ""; body: s.problem.body || "" }
            RowLayout {
                spacing: 10
                Text { text: "Format"; color: Theme.textMuted; font.pixelSize: Theme.body }
                ComboBox {
                    id: exportFormat
                    objectName: "exportFormat"
                    Layout.preferredWidth: 260
                    model: s.overview.components.filter(c => c.supported && ["gnome", "xfce"].indexOf(c.id) < 0)
                    textRole: "name"
                    enabled: !s.busy
                    onActivated: controller.renderExport(model[currentIndex].id)
                }
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

    Sheet {
        id: shortcutsDialog
        objectName: "shortcutsDialog"
        width: Math.min(560, window.width - 40)
        height: Math.min(window.height - 40, implicitHeight)
        title: "Keyboard shortcuts"
        subtitle: "Navigating and previewing never applies anything."
        contentItem: ColumnLayout {
            spacing: 14
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 20
                rowSpacing: 8
                Repeater {
                    model: [["Ctrl+F", "Search images"], ["↑ ↓", "Browse and preview images"], ["Enter", "Preview the first match or the highlighted image"],
                            ["Ctrl+Shift+R", "Preview a random image"], ["Alt+D", "Switch dark / light"], ["Alt+M", "Switch image / default colors"],
                            ["Ctrl+Enter", "Review changes"], ["Alt+Enter", "Apply the open review"], ["Ctrl+Z", "Review undo of the last change"],
                            ["Ctrl+1 / 2 / 3", "Theme, Applications, History"], ["Ctrl+R", "Check the desktop again"],
                            ["Escape", "Clear search, cancel a dialog, or close a quick theme change"]]
                    delegate: Item {
                        required property var modelData
                        required property int index
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        implicitHeight: 26
                        Rectangle {
                            id: keyCap
                            width: Math.max(110, keyText.implicitWidth + 16)
                            height: 24
                            radius: 5
                            color: Theme.raised
                            border.color: Theme.borderStrong
                            Text { id: keyText; anchors.centerIn: parent; text: modelData[0]; color: Theme.text; font.pixelSize: Theme.caption; font.family: Theme.mono }
                        }
                        Text { anchors.left: keyCap.right; anchors.leftMargin: 14; anchors.right: parent.right; anchors.verticalCenter: keyCap.verticalCenter; text: modelData[1]; color: Theme.textMuted; font.pixelSize: Theme.body; elide: Text.ElideRight }
                    }
                }
            }
            Command { text: "Close"; Layout.alignment: Qt.AlignRight; onClicked: shortcutsDialog.close() }
        }
    }
}
