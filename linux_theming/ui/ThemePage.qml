import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Choose an image, see the palette on sample windows, set the options.
Item {
    id: page
    required property QtObject controller
    readonly property var s: controller.state
    readonly property var folder: controller.imageFolder
    readonly property var preview: s.palette || ({})
    readonly property int imageCount: images.count
    readonly property bool narrow: width < 860
    property string lastCandidate: ""
    signal imageRequested()
    signal folderRequested()
    signal applicationsRequested()
    signal exportRequested()
    signal undoRequested()

    function focusSearch() { search.forceActiveFocus(); search.selectAll() }
    function handleEscape() {
        if (search.text) { search.clear(); search.forceActiveFocus(); return true }
        return false
    }
    function previewFirstMatch() {
        if (images.count > 0) {
            images.forceActiveFocus()
            images.currentIndex = 0
            controller.chooseWallpaper(folder.images[0].fileUrl)
        }
    }
    readonly property int nextStep: !s.profile.wallpaper ? 0 : !s.profile.components.length ? 1 : 2
    readonly property var addedApps: s.profile.components.filter(id => s.applied.components.indexOf(id) < 0)
    readonly property var removedApps: s.hasApplied ? s.applied.components.filter(id => s.profile.components.indexOf(id) < 0) : []
    function fileName(path) { return path ? path.split("/").pop() : "" }
    function componentName(id) {
        const item = s.overview.components.find(c => c.id === id)
        return item ? item.name : id
    }
    function homePath(path) {
        const home = controller.homePath
        return home && path && (path === home || path.startsWith(home + "/")) ? "~" + path.slice(home.length) : path
    }
    // A watched folder that gains or loses images keeps the reader's place.
    property real keptContentY: 0
    property bool keepScroll: false
    function restoreScroll() {
        for (let i = 0; i < images.count; ++i) {
            if (folder.images[i].filePath === s.profile.wallpaper) { images.currentIndex = i; break }
        }
        images.contentY = Math.max(images.originY, Math.min(page.keptContentY, images.originY + images.contentHeight - images.height))
        page.keepScroll = false
    }
    function syncSelection() {
        for (let i = 0; i < images.count; ++i) {
            if (folder.images[i].filePath === s.profile.wallpaper) {
                images.currentIndex = i
                images.positionViewAtIndex(i, ListView.Contain)
                return
            }
        }
    }
    Connections {
        target: page.controller
        function onFolderRefreshing() { page.keptContentY = images.contentY; page.keepScroll = true }
        function onFolderChanged() { Qt.callLater(page.keepScroll ? page.restoreScroll : page.syncSelection) }
        function onChanged() {
            if (page.lastCandidate !== page.s.profile.wallpaper) {
                page.lastCandidate = page.s.profile.wallpaper
                Qt.callLater(page.syncSelection)
            }
        }
    }
    // Arrow keys preview the highlighted image after a short pause. Previewing
    // never applies; approval always needs the separate review.
    Timer {
        id: browseTimer
        interval: 280
        onTriggered: {
            const item = page.folder.images[images.currentIndex]
            if (item && images.activeFocus && item.filePath !== page.s.profile.wallpaper)
                page.controller.chooseWallpaper(item.fileUrl)
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 20

        // Image library
        ColumnLayout {
            Layout.fillHeight: true
            Layout.preferredWidth: Math.max(280, Math.min(400, page.width * 0.36))
            Layout.maximumWidth: 400
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                SearchField {
                    id: search
                    objectName: "imageSearch"
                    Layout.fillWidth: true
                    placeholderText: page.folder.path ? "Search " + page.folder.total + " images" : "Search images"
                    text: page.folder.query || ""
                    enabled: !!page.folder.path
                    Accessible.name: "Search image library"
                    onTextChanged: page.controller.searchImages(text)
                    Keys.onDownPressed: { images.forceActiveFocus(); if (images.currentIndex < 0) images.currentIndex = 0 }
                    Keys.onReturnPressed: page.previewFirstMatch()
                    // Ctrl+Z in an empty search field reviews undo, as elsewhere in the window.
                    Keys.onPressed: function(event) {
                        if (event.matches(StandardKey.Undo) && !text && !canUndo) { page.undoRequested(); event.accepted = true }
                    }
                    Keys.onEnterPressed: page.previewFirstMatch()
                }
                Command {
                    objectName: "randomImage"
                    iconName: "shuffle"
                    implicitWidth: Theme.controlHeight
                    enabled: !page.s.busy && page.folder.images.length > 0
                    hint: "Ctrl+Shift+R"
                    Accessible.name: "Preview a random image"
                    onClicked: page.controller.chooseRandom()
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 120
                color: Theme.surface
                border.color: images.activeFocus ? Theme.borderStrong : Theme.border
                radius: Theme.radius
                ListView {
                    id: images
                    objectName: "imageList"
                    anchors.fill: parent
                    anchors.margins: 5
                    model: page.folder.images
                    clip: true
                    spacing: 2
                    keyNavigationEnabled: true
                    activeFocusOnTab: true
                    boundsBehavior: Flickable.StopAtBounds
                    highlightMoveDuration: 0
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    Accessible.role: Accessible.List
                    Accessible.name: "Images"
                    onCurrentIndexChanged: if (activeFocus) browseTimer.restart()
                    Keys.onReturnPressed: if (currentItem && !page.s.busy) { browseTimer.stop(); currentItem.clicked() }
                    Keys.onSpacePressed: if (currentItem && !page.s.busy) { browseTimer.stop(); currentItem.clicked() }
                    delegate: ItemDelegate {
                        id: row
                        required property int index
                        required property var modelData
                        readonly property bool candidate: page.s.profile.wallpaper === modelData.filePath
                        readonly property bool applied: page.s.hasApplied && page.s.applied.wallpaper === modelData.filePath
                        readonly property bool keyboardCurrent: images.activeFocus && images.currentIndex === index
                        objectName: "image-row-" + index
                        width: images.width - 10
                        height: 58
                        padding: 6
                        highlighted: candidate
                        activeFocusOnTab: false
                        hoverEnabled: true
                        Accessible.role: Accessible.ListItem
                        Accessible.name: modelData.relativePath || modelData.fileName
                        Accessible.selected: candidate
                        Accessible.description: (candidate ? "Previewing. " : "") + (applied ? "Currently applied." : "")
                        onClicked: { images.currentIndex = index; page.controller.chooseWallpaper(modelData.fileUrl) }
                        contentItem: RowLayout {
                            spacing: 10
                            Rectangle {
                                Layout.preferredWidth: 80
                                Layout.preferredHeight: 45
                                radius: 4
                                color: Theme.canvas
                                clip: true
                                Image {
                                    anchors.fill: parent
                                    source: row.modelData.fileUrl
                                    sourceSize: Qt.size(160, 90)
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    autoTransform: true
                                    cache: false
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3
                                Text {
                                    Layout.fillWidth: true
                                    text: row.modelData.fileName
                                    elide: Text.ElideMiddle
                                    color: Theme.text
                                    font.pixelSize: Theme.body
                                    font.weight: row.candidate ? Font.DemiBold : Font.Normal
                                    textFormat: Text.PlainText
                                }
                                Text {
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: {
                                        const rel = row.modelData.relativePath || ""
                                        return rel.indexOf("/") >= 0 ? rel.slice(0, rel.lastIndexOf("/")) : ""
                                    }
                                    elide: Text.ElideMiddle
                                    color: Theme.textFaint
                                    font.pixelSize: Theme.caption
                                    textFormat: Text.PlainText
                                }
                            }
                            Chip { visible: row.applied; text: "Applied"; tone: "accent" }
                            Chip { visible: row.candidate && !row.applied; text: page.s.hasApplied ? "Not applied" : "Preview"; tone: "warning" }
                        }
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: row.candidate ? Theme.hover : row.hovered ? Theme.raised : "transparent"
                            border.width: row.keyboardCurrent ? 2 : row.candidate ? 1 : 0
                            border.color: row.keyboardCurrent ? Theme.focus : Theme.textFaint
                        }
                        ToolTip.visible: hovered && (modelData.relativePath || "").length > 34
                        ToolTip.text: modelData.relativePath || modelData.fileName
                        ToolTip.delay: 600
                    }
                }
                // Empty states
                ColumnLayout {
                    anchors.centerIn: parent
                    width: parent.width - 40
                    spacing: 10
                    visible: images.count === 0 && !page.s.folderLoading
                    Icon { Layout.alignment: Qt.AlignHCenter; name: !page.folder.path ? "folder" : "search"; size: 28; color: Theme.textFaint }
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        color: Theme.text
                        font.pixelSize: Theme.bodyLarge
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        text: !page.folder.path ? "Choose a wallpaper folder"
                            : page.folder.query ? "No images match “" + page.folder.query + "”"
                            : "No images in this folder"
                    }
                    Body {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: !page.folder.path ? "Browse your images here. Choosing a folder only lists its files."
                            : page.folder.query ? "Try another name or clear the search."
                            : "Supported formats: PNG, JPEG, WebP, BMP and TIFF."
                    }
                    Command {
                        Layout.alignment: Qt.AlignHCenter
                        text: !page.folder.path ? "Choose folder…" : page.folder.query ? "Clear search" : "Choose another folder…"
                        primary: !page.folder.path
                        iconName: page.folder.query ? "close" : "folder"
                        enabled: !page.s.busy
                        onClicked: page.folder.query ? search.clear() : page.folderRequested()
                    }
                }
                BusyIndicator {
                    anchors.centerIn: parent
                    running: page.s.folderLoading && images.count === 0
                    visible: running
                }
            }
            Text {
                Layout.fillWidth: true
                visible: !!page.folder.path
                text: page.homePath(page.folder.path) + " · " + (page.folder.query ? images.count + " of " + page.folder.total : page.folder.total) + " images"
                color: Theme.textFaint
                font.pixelSize: Theme.caption
                elide: Text.ElideMiddle
                textFormat: Text.PlainText
                Accessible.name: "Image folder: " + page.folder.path
            }
            Body {
                Layout.fillWidth: true
                visible: !!page.folder.limited
                text: "Only part of this library is listed: the size limit was reached or some subfolders were unreadable."
                font.pixelSize: Theme.caption
                color: Theme.warning
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Command {
                    objectName: "chooseFolder"
                    visible: !!page.folder.path
                    Layout.fillWidth: true
                    Layout.maximumWidth: implicitWidth
                    Layout.minimumWidth: Math.min(implicitWidth, 110)
                    compact: true
                    iconName: "folder"
                    text: "Change folder…"
                    enabled: !page.s.busy && page.s.loaded
                    Accessible.name: page.folder.path ? "Change image folder, currently " + page.folder.path : "Choose image folder"
                    ToolTip.visible: hovered
                    ToolTip.text: page.folder.path ? page.homePath(page.folder.path) + " — choose another folder" : "Choose a folder of images"
                    ToolTip.delay: 400
                    onClicked: page.folderRequested()
                }
                Command {
                    objectName: "chooseImage"
                    compact: true
                    quiet: true
                    iconName: "image"
                    text: page.narrow && page.folder.path ? "" : "Single image…"
                    enabled: !page.s.busy && page.s.loaded
                    Accessible.name: "Choose one image file"
                    onClicked: page.imageRequested()
                }
                Item { Layout.fillWidth: true }
                Choice {
                    objectName: "includeSubfolders"
                    text: "Subfolders"
                    visible: !!page.folder.path
                    checked: !!page.folder.recursive
                    enabled: !page.s.busy && !page.s.folderLoading
                    font.pixelSize: Theme.caption
                    onClicked: page.controller.setRecursive(checked)
                }
            }
        }

        // Preview and options
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 320
            ScrollView {
                id: previewScroll
                objectName: "appearanceScroll"
                anchors.fill: parent
                contentWidth: availableWidth
                clip: true
                ScrollBar.vertical.policy: contentHeight > height + 1 ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded
                Item {
                    width: previewScroll.availableWidth
                    implicitHeight: column.implicitHeight
                    ColumnLayout {
                        id: column
                        // Keep the controls aligned with the desktop-shaped preview on wide windows.
                        width: parent.width - 14
                        spacing: 14

                        // First use: the three steps, with the next one marked.
                        Rectangle {
                            visible: !page.s.hasApplied
                            Layout.fillWidth: true
                            implicitHeight: steps.implicitHeight + 20
                            radius: Theme.radius
                            color: Theme.surface
                            border.color: Theme.border
                            Flow {
                                id: steps
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                spacing: 14
                                Repeater {
                                    model: [
                                        { label: "Choose an image", done: !!page.s.profile.wallpaper },
                                        { label: "Choose applications", done: page.s.profile.components.length > 0 },
                                        { label: "Review and apply", done: false }
                                    ]
                                    Row {
                                        required property var modelData
                                        required property int index
                                        spacing: 7
                                        readonly property bool next: index === page.nextStep
                                        Rectangle {
                                            width: 20
                                            height: 20
                                            radius: 10
                                            color: modelData.done ? Theme.accent : "transparent"
                                            border.width: modelData.done ? 0 : parent.next ? 2 : 1
                                            border.color: parent.next ? Theme.accent : Theme.borderStrong
                                            Icon { anchors.centerIn: parent; visible: modelData.done; name: "check"; size: 13; color: Theme.accentInk }
                                            Text { anchors.centerIn: parent; visible: !modelData.done; text: index + 1; color: parent.parent.next ? Theme.accent : Theme.textMuted; font.pixelSize: Theme.caption; font.weight: Font.DemiBold }
                                        }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: modelData.label
                                            color: modelData.done ? Theme.textMuted : parent.next ? Theme.text : Theme.textMuted
                                            font.pixelSize: Theme.body
                                            font.weight: parent.next ? Font.DemiBold : Font.Normal
                                        }
                                    }
                                }
                            }
                            Accessible.role: Accessible.StaticText
                            Accessible.name: "Steps: choose an image, choose applications, review and apply"
                        }

                        WallpaperPreview {
                            id: wallpaperPreview
                            Layout.fillWidth: true
                            source: page.s.wallpaperUrl
                            special: page.preview.special || ({ background: "#14171c", foreground: "#d6dae1", cursor: "#cad8cb" })
                            colors: page.preview.colors || ({})
                            busy: page.s.previewing
                            minimumCanvasHeight: 170
                            // Leave room for the options and "When you apply" without scrolling.
                            availableHeight: previewScroll.availableHeight * 0.76
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 8
                            Segmented {
                                accessibleName: "Background mode"
                                interactive: !page.s.busy && page.s.loaded
                                current: page.s.profile.polarity
                                options: [
                                    { value: "dark", label: "Dark", icon: "moon", objectName: "polarity-dark", description: "Dark backgrounds · Alt+D" },
                                    { value: "light", label: "Light", icon: "sun", objectName: "polarity-light", description: "Light backgrounds · Alt+D" }
                                ]
                                onPicked: function(value) { page.controller.setOption("polarity", value) }
                            }
                            Segmented {
                                accessibleName: "Color source"
                                interactive: !page.s.busy && page.s.loaded
                                current: page.s.profile.wallpaper ? page.s.profile.mode : "safe"
                                options: [
                                    { value: "adaptive", label: "From image", objectName: "mode-adaptive", enabled: !!page.s.profile.wallpaper, description: "Derive the palette from the image · Alt+M" },
                                    { value: "safe", label: "Default colors", objectName: "mode-safe", description: "Use the built-in accessible palette · Alt+M" }
                                ]
                                onPicked: function(value) { page.controller.setOption("mode", value) }
                            }
                        }

                        // Palette
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.maximumWidth: 760
                            spacing: 6
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 9
                                columnSpacing: 4
                                rowSpacing: 4
                                opacity: page.s.previewing ? 0.55 : 1
                                Behavior on opacity { NumberAnimation { duration: 120 } }
                                Repeater {
                                    model: page.narrow ? ["", "blk", "red", "grn", "yel", "blu", "mag", "cyn", "wht"] : ["", "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
                                    Text {
                                        required property string modelData
                                        Layout.fillWidth: !!modelData
                                        Layout.preferredWidth: modelData ? 10 : 46
                                        text: modelData
                                        color: Theme.textFaint
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                        Accessible.ignored: true
                                    }
                                }
                                Repeater {
                                    model: 18
                                    Item {
                                        id: cell
                                        required property int index
                                        readonly property bool label: index % 9 === 0
                                        readonly property int colorIndex: index < 9 ? index - 1 : index - 2
                                        readonly property color swatch: (page.preview.colors || ({}))["color" + colorIndex] || Theme.raised
                                        Layout.fillWidth: !label
                                        Layout.preferredWidth: label ? 46 : 10
                                        implicitHeight: 22
                                        Text {
                                            visible: cell.label
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: cell.index === 0 ? "Normal" : "Bright"
                                            color: Theme.textFaint
                                            font.pixelSize: Theme.caption
                                        }
                                        Rectangle {
                                            visible: !cell.label
                                            anchors.fill: parent
                                            radius: 4
                                            color: cell.swatch
                                            border.width: 1
                                            border.color: Qt.rgba(1, 1, 1, 0.08)
                                            Accessible.role: Accessible.Graphic
                                            readonly property string role: ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"][cell.colorIndex % 8] + (cell.colorIndex >= 8 ? ", bright" : "")
                                            Accessible.name: "Color " + cell.colorIndex + ", " + role + ": " + cell.swatch + ". Copy"
                                            property bool copied: false
                                            Timer { id: copiedTimer; interval: 1200; onTriggered: parent.copied = false }
                                            HoverHandler { id: swatchHover; cursorShape: Qt.PointingHandCursor }
                                            TapHandler { onTapped: { page.controller.copyText(cell.swatch.toString()); parent.copied = true; copiedTimer.restart() } }
                                            ToolTip.visible: swatchHover.hovered || copied
                                            ToolTip.text: copied ? "Copied " + cell.swatch : role.charAt(0).toUpperCase() + role.slice(1) + " (color " + cell.colorIndex + ") · " + cell.swatch + " · click to copy"
                                            ToolTip.delay: 300
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Body {
                                    objectName: "effectivePalette"
                                    Layout.fillWidth: true
                                    readonly property bool fallback: !!page.preview.effective && page.s.profile.mode === "adaptive" && page.preview.effective === "safe" && !!page.s.profile.wallpaper
                                    text: fallback ? "Using default colors: " + (page.preview.reason || "this image's colors do not have enough contrast.")
                                        : !page.s.profile.wallpaper ? "Default colors are used until you choose an image."
                                        : page.preview.reason || "Colors are checked for terminal contrast."
                                    color: fallback ? Theme.warning : Theme.textFaint
                                    font.pixelSize: Theme.caption
                                }
                                Command {
                                    objectName: "exportTheme"
                                    compact: true
                                    quiet: true
                                    iconName: "export"
                                    text: "Export file…"
                                    enabled: !page.s.busy && !!page.preview.special
                                    Accessible.description: "Save a theme file for your own configuration. Does not connect an application."
                                    onClicked: page.exportRequested()
                                }
                            }
                        }

                        // What applying affects
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: effects.implicitHeight + 24
                            radius: Theme.radiusLarge
                            color: Theme.surface
                            border.color: page.s.profile.components.length ? Theme.border : Theme.infoBorder
                            ColumnLayout {
                                id: effects
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: 8
                                Text {
                                    text: "When you apply"
                                    color: Theme.textFaint
                                    font.pixelSize: Theme.caption
                                    font.weight: Font.DemiBold
                                    font.capitalization: Font.AllUppercase
                                    font.letterSpacing: 0.6
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 10
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Text {
                                            Layout.fillWidth: true
                                            text: page.s.profile.components.length ? "The palette is used in these applications"
                                                : page.removedApps.length ? "No application will use the palette" : "No applications chosen yet"
                                            color: Theme.text
                                            font.pixelSize: Theme.body
                                            wrapMode: Text.Wrap
                                        }
                                        Flow {
                                            Layout.fillWidth: true
                                            visible: page.s.profile.components.length > 0 || page.removedApps.length > 0
                                            spacing: 6
                                            Repeater {
                                                model: page.s.profile.components
                                                Chip {
                                                    required property string modelData
                                                    readonly property bool added: page.s.hasApplied && page.addedApps.indexOf(modelData) >= 0
                                                    text: page.componentName(modelData) + (added ? " · new" : "")
                                                    tone: added ? "warning" : "neutral"
                                                }
                                            }
                                            Repeater {
                                                model: page.removedApps
                                                Chip { required property string modelData; text: page.componentName(modelData) + " · previous colors restored"; tone: "faint" }
                                            }
                                        }
                                        Body {
                                            Layout.fillWidth: true
                                            visible: !page.s.profile.components.length
                                            text: "Choose terminals, bars and other applications. Everything else stays as it is."
                                            font.pixelSize: Theme.caption + 1
                                        }
                                    }
                                    Command {
                                        objectName: "manageApplications"
                                        Layout.alignment: Qt.AlignTop
                                        compact: true
                                        quiet: true
                                        text: page.s.profile.components.length ? "Change…" : "Choose…"
                                        iconName: "apps"
                                        Accessible.name: page.s.profile.components.length ? "Change applications" : "Choose applications"
                                        onClicked: page.applicationsRequested()
                                    }
                                }
                                Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                                Toggle {
                                    objectName: "setDesktopWallpaper"
                                    Layout.fillWidth: true
                                    text: "Set as desktop wallpaper"
                                    description: !page.s.profile.wallpaper ? "Choose an image first." : page.s.profile.set_wallpaper ? "Your current background is kept for undo." : "Your current background stays as it is."
                                    checked: !!page.s.profile.set_wallpaper
                                    enabled: !page.s.busy && page.s.loaded && !!page.s.profile.wallpaper
                                    onToggled: page.controller.setWallpaperEnabled(checked)
                                }
                            }
                        }
                        Item { implicitHeight: 4 }
                    }
                }
            }
            // A fade shows that the column continues below the window edge.
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.rightMargin: 14
                anchors.bottom: parent.bottom
                height: 28
                visible: previewScroll.contentItem.contentY + previewScroll.height < previewScroll.contentHeight - 4
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 1; color: Theme.window }
                }
            }
        }
    }
}
