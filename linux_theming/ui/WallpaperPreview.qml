import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// A desktop-shaped preview: the selected image with sample windows painted in
// the previewed palette. Fit/Fill and the sample windows affect only this view.
ColumnLayout {
    id: preview
    property url source
    property real availableHeight: 600
    property bool fill: true
    property bool samples: true
    property bool busy: false
    property var special: ({ background: "#14171c", foreground: "#d6dae1", cursor: "#cad8cb" })
    property var colors: ({})
    property real minimumCanvasHeight: 160
    property string objectPrefix: "wallpaperPreview"
    spacing: 8

    function tone(index, fallback) { return preview.colors["color" + index] || fallback }

    Item {
        Layout.fillWidth: true
        // Keep a desktop-shaped canvas without letting a wide/short window
        // push all the controls away. The surrounding ScrollView handles overflow.
        implicitHeight: Math.min(width * 9 / 16, Math.max(preview.minimumCanvasHeight, preview.availableHeight * 0.58))
        Rectangle {
            id: frame
            objectName: preview.objectPrefix + "Frame"
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height * 16 / 9)
            height: width * 9 / 16
            color: Theme.canvas
            radius: Theme.radius
            clip: true
            readonly property real unit: height / 100
            Image {
                id: image
                objectName: preview.objectPrefix + "Image"
                anchors.fill: parent
                source: preview.source
                visible: status === Image.Ready
                fillMode: preview.fill ? Image.PreserveAspectCrop : Image.PreserveAspectFit
                horizontalAlignment: Image.AlignHCenter
                verticalAlignment: Image.AlignVCenter
                asynchronous: true
                autoTransform: true
                // Bound decoding in both dimensions, including portrait images.
                // A stable size avoids repeated decoding during window resizing.
                sourceSize.width: 2560
                sourceSize.height: 1440
                Accessible.role: Accessible.Graphic
                Accessible.name: "Wallpaper preview"
                Accessible.description: preview.fill ? "Centered crop in a 16:9 frame" : "Entire image fitted in a 16:9 frame"
            }
            Column {
                anchors.centerIn: parent
                width: parent.width - 24
                spacing: 6
                visible: image.status !== Image.Ready && !preview.samples
                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "image"; size: 22; color: Theme.textFaint }
                Body {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: image.status === Image.Loading ? "Loading image…"
                        : image.status === Image.Error ? "Image preview unavailable"
                        : "No image selected"
                }
            }

            // Sample bar along the top edge.
            Rectangle {
                id: bar
                visible: preview.samples
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: Math.max(16, frame.unit * 6.5)
                color: preview.special.background
                opacity: 0.94
                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: frame.unit * 2
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: frame.unit * 1
                    Repeater {
                        model: 4
                        Rectangle {
                            required property int index
                            width: bar.height * 1.1
                            height: bar.height * 0.7
                            radius: 2
                            color: index === 0 ? preview.tone(4, "#9babcc") : "transparent"
                            Text {
                                anchors.centerIn: parent
                                text: parent.index + 1
                                font.pixelSize: Math.max(7, bar.height * 0.5)
                                color: parent.index === 0 ? preview.special.background : preview.special.foreground
                            }
                        }
                    }
                }
                Text {
                    anchors.centerIn: parent
                    text: "Mon 09:41"
                    font.pixelSize: Math.max(7, bar.height * 0.5)
                    color: preview.special.foreground
                }
                Row {
                    anchors.right: parent.right
                    anchors.rightMargin: frame.unit * 2
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: frame.unit * 1.2
                    Repeater {
                        model: [2, 3, 5]
                        Rectangle {
                            required property int modelData
                            width: bar.height * 0.42
                            height: width
                            radius: width / 2
                            color: preview.tone(modelData, preview.special.foreground)
                        }
                    }
                }
            }

            // Sample terminal window.
            Rectangle {
                id: term
                visible: preview.samples
                x: frame.width * 0.38
                y: bar.height + frame.height * 0.045
                width: frame.width * 0.56
                // End above the view options in the bottom corner.
                height: Math.min(frame.height * 0.7, frame.height - y - 48)
                radius: Math.max(3, frame.unit * 1.4)
                color: preview.special.background
                border.color: preview.tone(8, "#555761")
                border.width: 1
                clip: true
                readonly property real fontSize: Math.max(9, frame.unit * 4.2)
                // Small previews show fewer sample lines instead of unreadable text.
                readonly property bool compact: height < fontSize * 15.5
                Rectangle {
                    id: titleBar
                    width: parent.width
                    height: term.fontSize * 1.9
                    color: "transparent"
                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: term.fontSize * 0.8
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: term.fontSize * 0.45
                        Repeater {
                            model: [1, 3, 2]
                            Rectangle {
                                required property int modelData
                                width: term.fontSize * 0.7
                                height: width
                                radius: width / 2
                                color: preview.tone(modelData, "#888888")
                                opacity: 0.9
                            }
                        }
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "~/projects"
                        font.family: Theme.mono
                        font.pixelSize: term.fontSize * 0.85
                        color: preview.special.foreground
                        opacity: 0.6
                    }
                }
                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: titleBar.bottom
                    anchors.margins: term.fontSize * 0.9
                    anchors.topMargin: term.fontSize * 0.3
                    spacing: term.fontSize * 0.32
                    Row {
                        spacing: term.fontSize * 0.5
                        Text { text: "❯"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(4, "#9babcc") }
                        Text { text: "git status"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.special.foreground }
                    }
                    Text { text: "On branch main"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.special.foreground }
                    Text { text: "  modified:  colors.conf"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(3, "#d7bc82") }
                    Text { text: "  added:     theme.conf"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(2, "#99bd98") }
                    Text { visible: !term.compact; text: "  deleted:   old.conf"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(1, "#e08a8a") }
                    Row {
                        visible: !term.compact
                        spacing: term.fontSize * 0.5
                        Text { text: "❯"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(4, "#9babcc") }
                        Text { text: "ls"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.special.foreground }
                    }
                    Row {
                        visible: !term.compact
                        spacing: term.fontSize * 0.9
                        Text { text: "docs/"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(4, "#9babcc"); font.bold: true }
                        Text { text: "build.sh"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(2, "#99bd98") }
                        Text { text: "notes.md"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(5, "#c9a0dc") }
                        Text { text: "link"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(6, "#88c0d0") }
                    }
                    Row {
                        spacing: term.fontSize * 0.5
                        Text { text: "❯"; font.family: Theme.mono; font.pixelSize: term.fontSize; color: preview.tone(4, "#9babcc") }
                        Rectangle { width: term.fontSize * 0.6; height: term.fontSize * 1.2; color: preview.special.cursor }
                    }
                }
            }

            Rectangle {
                visible: preview.busy
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.margins: 8
                width: busyRow.implicitWidth + 16
                height: 26
                radius: 13
                color: "#d9121418"
                Row {
                    id: busyRow
                    anchors.centerIn: parent
                    spacing: 6
                    BusyIndicator { width: 16; height: 16; running: preview.busy; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "Building palette…"; color: Theme.text; font.pixelSize: Theme.caption; anchors.verticalCenter: parent.verticalCenter }
                }
            }

            // View options for this preview only.
            Rectangle {
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 8
                width: viewRow.implicitWidth + 8
                height: viewRow.implicitHeight + 8
                radius: Theme.radius
                color: "#e6121418"
                border.color: Theme.border
                RowLayout {
                    id: viewRow
                    anchors.centerIn: parent
                    spacing: 4
                    Command {
                        objectName: preview.objectPrefix + "Samples"
                        compact: true
                        quiet: !checked
                        checkable: true
                        checked: preview.samples
                        iconName: "terminal"
                        implicitWidth: 30
                        implicitHeight: 28
                        Accessible.name: checked ? "Hide sample windows" : "Show sample windows"
                        Accessible.description: "Only affects this preview"
                        onClicked: preview.samples = !preview.samples
                    }
                    Segmented {
                        visible: !!preview.source.toString()
                        implicitHeight: 28
                        accessibleName: "Preview framing"
                        current: preview.fill ? "fill" : "fit"
                        options: [
                            { value: "fit", label: "Fit", objectName: preview.objectPrefix + "Fit", description: "Show the entire image; only affects this preview" },
                            { value: "fill", label: "Fill", objectName: preview.objectPrefix + "Fill", description: "Fill the preview with a centered crop; only affects this preview" }
                        ]
                        onPicked: function(value) { preview.fill = value === "fill" }
                    }
                }
            }
        }
    }
}
