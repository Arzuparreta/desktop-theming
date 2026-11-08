import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: daily
    required property QtObject controller
    readonly property var s: controller.state
    readonly property var folder: controller.imageFolder
    readonly property var preview: s.palette || ({})
    property string lastCandidate: ""
    signal imageRequested()
    signal folderRequested()
    signal componentsRequested()
    signal activationRequested()

    function focusSearch() { search.forceActiveFocus() }
    function name(path) { return path ? path.split("/").pop() : "Default palette" }
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
        target: controller
        function onFolderChanged() { Qt.callLater(daily.syncSelection) }
        function onChanged() {
            if (daily.lastCandidate !== s.profile.wallpaper) {
                daily.lastCandidate = s.profile.wallpaper
                Qt.callLater(daily.syncSelection)
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 14
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label { text: s.hasApplied ? "Last applied by Linux Theming" : "Make this desktop yours"; color: "#b9bbc4"; font.pixelSize: 12 }
                Label {
                    objectName: "appliedTheme"
                    Layout.fillWidth: true
                    text: s.hasApplied ? daily.name(s.applied.wallpaper) + " · " + (s.applied.polarity === "light" ? "Light" : "Dark") : "Choose an image, then connect the applications you want."
                    color: "#e7e7eb"; font.pixelSize: 16; elide: Text.ElideMiddle
                    textFormat: Text.PlainText
                }
            }
            Command { objectName: "dailyUndo"; text: "Undo…"; enabled: !s.busy && s.overview.history.some(h => ["applied", "prepared", "recovery-needed", "undoing"].indexOf(h.status) >= 0); onClicked: controller.undoLatest(); Accessible.description: "Review restoration of the last change, Ctrl+Z" }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 20
            ColumnLayout {
                Layout.preferredWidth: 370
                Layout.minimumWidth: 280
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8
                TextField {
                    id: search
                    objectName: "dailySearch"
                    Layout.fillWidth: true
                    placeholderText: "Search images…"
                    text: folder.query || ""
                    enabled: !s.busy
                    selectByMouse: true
                    Accessible.name: "Search image library"
                    onTextChanged: controller.searchImages(text)
                    Keys.onDownPressed: { images.forceActiveFocus(); if (images.currentIndex < 0) images.currentIndex = 0 }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Command { objectName: "dailyRandom"; text: "Random"; enabled: !s.busy && folder.images.length > 0; onClicked: controller.chooseRandom(); Accessible.description: "Preview a random matching image, Ctrl+Shift+R" }
                    Command { text: "Folder…"; enabled: !s.busy; onClicked: daily.folderRequested() }
                    Command { text: "Image…"; quiet: true; enabled: !s.busy; onClicked: daily.imageRequested() }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Choice { text: "Subfolders"; checked: !!folder.recursive; enabled: !s.busy && !s.folderLoading; onClicked: controller.setRecursive(checked) }
                    Item { Layout.fillWidth: true }
                    Body { text: s.folderLoading ? "Reading…" : folder.images.length + " / " + folder.total; font.pixelSize: 11 }
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 80
                    color: "#111318"; border.color: "#3c3e45"; radius: 6
                    ListView {
                        id: images
                        objectName: "dailyImageList"
                        anchors.fill: parent
                        anchors.margins: 4
                        model: folder.images
                        clip: true
                        spacing: 3
                        keyNavigationEnabled: true
                        activeFocusOnTab: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        Accessible.role: Accessible.List
                        Accessible.name: "Matching images"
                        Keys.onReturnPressed: if (currentItem && !s.busy) currentItem.clicked()
                        Keys.onSpacePressed: if (currentItem && !s.busy) currentItem.clicked()
                        delegate: ItemDelegate {
                            id: row
                            required property int index
                            required property var modelData
                            objectName: "daily-image-" + index
                            width: images.width - 12
                            height: 58
                            enabled: !s.busy
                            padding: 6
                            highlighted: s.profile.wallpaper === modelData.filePath
                            activeFocusOnTab: false
                            Accessible.name: modelData.relativePath || modelData.fileName
                            Accessible.selected: highlighted
                            Accessible.description: highlighted ? "Preview candidate, not applied until approval" : "Select image to preview"
                            onClicked: { images.currentIndex = index; controller.chooseWallpaper(modelData.fileUrl) }
                            contentItem: RowLayout {
                                spacing: 9
                                Image { Layout.preferredWidth: 58; Layout.preferredHeight: 44; source: row.modelData.fileUrl; asynchronous: true; autoTransform: true; sourceSize: Qt.size(116, 88); fillMode: Image.PreserveAspectFit }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Label { Layout.fillWidth: true; text: row.modelData.relativePath || row.modelData.fileName; elide: Text.ElideMiddle; color: "#e7e7eb"; textFormat: Text.PlainText; font.pixelSize: 12 }
                                    Label { visible: s.hasApplied && s.applied.wallpaper === row.modelData.filePath; text: "Last applied"; color: "#99bba2"; font.pixelSize: 10 }
                                }
                                Label { text: row.highlighted ? "✓" : ""; color: "#cad8cb" }
                            }
                            background: Rectangle {
                                radius: 4
                                color: row.highlighted ? "#303d35" : row.hovered ? "#292c33" : "transparent"
                                border.width: images.activeFocus && images.currentIndex === row.index ? 2 : 1
                                border.color: images.activeFocus && images.currentIndex === row.index ? "#cad8cb" : row.highlighted ? "#78977d" : "transparent"
                            }
                        }
                        Body {
                            anchors.centerIn: parent
                            width: parent.width - 24
                            visible: images.count === 0
                            text: !folder.path ? "Choose a folder to keep your images one shortcut away." : "No matching images. Change the search or choose another folder."
                        }
                    }
                }
                Label { Layout.fillWidth: true; text: folder.path || "No image folder chosen"; color: "#b9bbc4"; font.pixelSize: 10; elide: Text.ElideMiddle; textFormat: Text.PlainText }
                Body { Layout.fillWidth: true; visible: !!folder.limited; text: "Library limit reached or some subfolders were unreadable. Choose a smaller folder to see the rest."; font.pixelSize: 11; color: "#e4c793" }
            }
            ScrollView {
                id: previewScroll
                Layout.preferredWidth: 360
                Layout.minimumWidth: 290
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true
                ColumnLayout {
                    width: previewScroll.availableWidth
                    spacing: 8
                    RowLayout {
                        Label { text: "Preview"; color: "#e7e7eb"; font.pixelSize: 15 }
                        Item { Layout.fillWidth: true }
                        Body { text: s.previewing ? "Building palette…" : s.pending ? "Not applied" : "Saved choices"; color: s.pending ? "#e4c793" : "#b9bbc4"; font.pixelSize: 11 }
                    }
                    RowLayout {
                        Repeater { model: ["dark", "light"]; Command { required property string modelData; text: modelData === "dark" ? "Dark" : "Light"; primary: s.profile.polarity === modelData; enabled: !s.busy && s.loaded; onClicked: controller.setOption("polarity", modelData) } }
                    }
                    RowLayout {
                        Repeater { model: ["adaptive", "safe"]; Command { required property string modelData; text: modelData === "adaptive" ? "From image" : "Default colors"; primary: s.profile.mode === modelData; enabled: !s.busy && s.loaded && (modelData !== "adaptive" || !!s.profile.wallpaper); onClicked: controller.setOption("mode", modelData) } }
                    }
                    Body { objectName: "dailyEffectivePalette"; Layout.fillWidth: true; text: preview.effective ? "Effective: " + (preview.effective === "safe" ? "Default colors" : "Image colors") + (preview.reason ? ". " + preview.reason : "") : "Select an image to preview its colors."; font.pixelSize: 11 }
                    Choice { text: "Set as desktop wallpaper"; checked: s.profile.set_wallpaper; enabled: !s.busy && !!s.profile.wallpaper; onClicked: controller.setWallpaperEnabled(checked) }
                    Body { Layout.fillWidth: true; text: s.profile.components.length ? "Selected applications: " + s.profile.components.join(", ") : "No applications connected. Choose which ones use these colors."; font.pixelSize: 12 }
                    Command { text: s.profile.components.length ? "Manage applications…" : "Choose applications…"; quiet: true; enabled: !s.busy; onClicked: daily.componentsRequested() }
                    Command { visible: s.activation.length > 0; text: "Activation status…"; quiet: true; onClicked: daily.activationRequested() }
                    WallpaperPreview { objectPrefix: "dailyWallpaperPreview"; Layout.fillWidth: true; source: s.wallpaperUrl; minimumCanvasHeight: 100; availableHeight: Math.max(120, previewScroll.availableHeight - 360) }
                    Label { Layout.fillWidth: true; text: daily.name(s.profile.wallpaper); color: "#e7e7eb"; font.pixelSize: 12; elide: Text.ElideMiddle; textFormat: Text.PlainText }
                    GridLayout {
                        columns: 8; columnSpacing: 6; rowSpacing: 6
                        Repeater {
                            model: 16
                            Rectangle { required property int index; implicitWidth: 24; implicitHeight: 24; radius: 4; color: (preview.colors || ({}))["color" + index] || "#36383f"; Accessible.name: "ANSI " + index + ": " + color }
                        }
                    }

                }
            }
        }
    }
}
