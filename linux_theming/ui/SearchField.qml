import QtQuick
import QtQuick.Controls

TextField {
    id: field
    implicitHeight: Theme.controlHeight
    leftPadding: 34
    rightPadding: clearButton.visible ? 34 : 10
    font.pixelSize: Theme.body
    color: Theme.text
    placeholderTextColor: Theme.textFaint
    selectionColor: Theme.accentBorder
    selectedTextColor: Theme.text
    selectByMouse: true
    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: field.activeFocus ? 2 : 1
        border.color: field.activeFocus ? Theme.accentBorder : Theme.border
        Icon { x: 11; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 15; color: Theme.textFaint }
    }
    Command {
        id: clearButton
        anchors.right: parent.right
        anchors.rightMargin: 3
        anchors.verticalCenter: parent.verticalCenter
        compact: true
        quiet: true
        iconName: "close"
        implicitWidth: 28
        implicitHeight: 28
        focusPolicy: Qt.NoFocus
        visible: !!field.text
        Accessible.name: "Clear search"
        onClicked: field.clear()
    }
}
