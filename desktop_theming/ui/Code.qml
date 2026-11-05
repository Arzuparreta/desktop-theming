import QtQuick
import QtQuick.Controls

Rectangle {
    id: panel
    property alias text: editor.text
    color: "#111318"
    radius: 6
    clip: true
    ScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: editor.height + 32
        clip: true
        TextEdit {
            id: editor
            objectName: "fileContents"
            x: 16
            y: 16
            width: Math.max(0, scroll.availableWidth - 32)
            height: contentHeight
            readOnly: true
            selectByMouse: true
            persistentSelection: true
            textFormat: TextEdit.PlainText
            wrapMode: TextEdit.WrapAnywhere
            renderType: TextEdit.NativeRendering
            color: "#d3d5dd"
            selectedTextColor: "#111318"
            selectionColor: "#cad8cb"
            font.family: "monospace"
            font.pixelSize: 12
            Accessible.name: "File contents"
        }
    }
}
