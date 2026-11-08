import QtQuick
import QtQuick.Controls

Switch {
    id: control
    property string description: ""
    spacing: 12
    padding: 4
    font.pixelSize: Theme.body
    hoverEnabled: true
    activeFocusOnTab: true
    Accessible.description: description
    indicator: Rectangle {
        implicitWidth: 38
        implicitHeight: 22
        x: control.text ? control.leftPadding : (control.width - width) / 2
        y: control.topPadding + (control.availableHeight - height) / 2
        radius: height / 2
        color: control.checked ? (control.enabled ? Theme.accent : Theme.accentSoft) : control.hovered && control.enabled ? Theme.pressed : Theme.hover
        border.width: control.checked ? 0 : 1
        border.color: Theme.borderStrong
        Rectangle {
            width: 16
            height: 16
            radius: 8
            y: 3
            x: control.checked ? parent.width - width - 3 : 3
            color: control.checked ? Theme.accentInk : control.enabled ? Theme.textMuted : Theme.disabled
            Behavior on x { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: height / 2
            color: "transparent"
            border.width: 2
            border.color: Theme.focus
            visible: control.visualFocus
        }
    }
    contentItem: Column {
        leftPadding: control.text ? control.indicator.width + control.spacing : 0
        spacing: 2
        visible: !!control.text
        Text {
            width: parent.width - parent.leftPadding
            text: control.text
            font: control.font
            color: control.enabled ? Theme.text : Theme.disabled
            wrapMode: Text.Wrap
        }
        Text {
            width: parent.width - parent.leftPadding
            visible: !!control.description
            text: control.description
            font.pixelSize: Theme.caption
            color: Theme.textFaint
            wrapMode: Text.Wrap
        }
    }
}
