import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    spacing: 10
    font.pixelSize: 13
    activeFocusOnTab: true
    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: 4
        color: control.checked ? "#cad8cb" : "#1b1d22"
        border.color: control.activeFocus ? "#ffffff" : control.checked ? "#cad8cb" : "#62646e"
        Text { anchors.centerIn: parent; text: "✓"; color: "#17191d"; font.pixelSize: 13; visible: control.checked }
    }
    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? "#e7e7eb" : "#777a84"
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
}
