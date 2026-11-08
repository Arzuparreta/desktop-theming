import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: preview
    property url source
    property real availableHeight: 600
    property bool fill: false
    property real minimumCanvasHeight: 160
    property string objectPrefix: "wallpaperPreview"
    spacing: 6

    Item {
        Layout.fillWidth: true
        // Keep a desktop-shaped canvas without letting a wide/short window
        // push all the controls away. The surrounding ScrollView handles overflow.
        implicitHeight: Math.min(width * 9 / 16, Math.max(preview.minimumCanvasHeight, preview.availableHeight * 0.65))
        Rectangle {
            objectName: preview.objectPrefix + "Frame"
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height * 16 / 9)
            height: width * 9 / 16
            color: "#111318"
            clip: true
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
            Body {
                anchors.centerIn: parent
                width: parent.width - 24
                horizontalAlignment: Text.AlignHCenter
                visible: image.status !== Image.Ready
                text: image.status === Image.Loading ? "Loading image…"
                    : image.status === Image.Error ? "Image preview unavailable"
                    : "No image selected"
            }
        }
    }
    RowLayout {
        Layout.alignment: Qt.AlignRight
        visible: !!preview.source.toString()
        Body { text: "Preview"; font.pixelSize: 11 }
        Command {
            objectName: preview.objectPrefix + "Fit"
            text: "Fit"
            primary: !preview.fill
            onClicked: preview.fill = false
            Accessible.description: "Show the entire image; only affects this preview"
        }
        Command {
            objectName: preview.objectPrefix + "Fill"
            text: "Fill"
            primary: preview.fill
            onClicked: preview.fill = true
            Accessible.description: "Fill the preview with a centered crop; only affects this preview"
        }
    }
}
