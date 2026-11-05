import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property bool quiet: false
    implicitHeight: 38
    implicitWidth: Math.max(80, contentItem.implicitWidth + 28)
    hoverEnabled: true
    font.pixelSize: 13
    activeFocusOnTab: true
    contentItem: Text {
        text: control.text
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: !control.enabled ? "#696b72" : control.primary ? "#17191d" : "#e7e7eb"
    }
    background: Rectangle {
        radius: 6
        color: !control.enabled ? "#26282d" : control.primary ? (control.down ? "#adbcae" : control.hovered ? "#dce6dc" : "#cad8cb") : control.down ? "#36383f" : control.hovered ? "#2d2f35" : control.quiet ? "transparent" : "#25272d"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? "#cad8cb" : control.quiet ? "transparent" : "#36383f"
    }
}
