import QtQuick
import QtQuick.Controls

ScrollView {
    id: scroll
    property alias text: area.text
    clip: true
    TextArea {
        id: area
        readOnly: true
        selectByMouse: true
        persistentSelection: true
        textFormat: TextEdit.PlainText
        wrapMode: TextEdit.WrapAnywhere
        color: "#d3d5dd"
        selectedTextColor: "#111318"
        selectionColor: "#cad8cb"
        font.family: "monospace"
        font.pixelSize: 12
        padding: 16
        background: Rectangle { color: "#111318"; radius: 6 }
        Accessible.name: "File contents"
    }
}
