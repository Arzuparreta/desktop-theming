import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    spacing: 10
    font.pixelSize: Theme.body
    activeFocusOnTab: true
    hoverEnabled: true
    padding: 4
    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: 5
        color: control.checked ? Theme.accent : control.hovered ? Theme.hover : Theme.surface
        border.width: control.checked ? 0 : 1
        border.color: control.enabled ? Theme.borderStrong : Theme.border
        opacity: control.enabled ? 1 : 0.5
        Icon { anchors.centerIn: parent; name: "check"; size: 13; color: Theme.accentInk; visible: control.checked }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: 7
            color: "transparent"
            border.width: 2
            border.color: Theme.focus
            visible: control.visualFocus
        }
    }
    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? Theme.text : Theme.disabled
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
}
