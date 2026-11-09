import QtQuick
import QtQuick.Layouts

// A titled list of settings rows on one surface. Rows separate themselves and
// share any extra height when a neighbouring group is taller.
ColumnLayout {
    id: group
    property string title: ""
    // Fill the height of a taller neighbouring group in the same grid row.
    property bool stretch: true
    default property alias rows: list.data
    Layout.fillWidth: true
    Layout.fillHeight: stretch
    Layout.alignment: Qt.AlignTop
    spacing: 6
    Text {
        visible: !!group.title
        text: group.title
        color: Theme.textFaint
        font.pixelSize: Theme.caption
        font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 0.6
        Accessible.role: Accessible.Heading
        Accessible.name: text
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: group.stretch
        implicitHeight: list.implicitHeight + 2
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.border
        ColumnLayout {
            id: list
            x: 1
            y: 1
            width: parent.width - 2
            height: parent.height - 2
            spacing: 0
        }
    }
}
