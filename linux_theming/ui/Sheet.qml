import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Modal dialog frame: title, optional subtitle, scrim and consistent padding.
Dialog {
    id: sheet
    property string subtitle: ""
    anchors.centerIn: parent
    modal: true
    padding: 22
    topPadding: 4
    bottomPadding: 20
    Overlay.modal: Rectangle { color: Theme.scrim }
    background: Rectangle { color: Theme.surface; border.color: Theme.borderStrong; radius: Theme.radiusLarge }
    header: ColumnLayout {
        spacing: 4
        Label {
            Layout.fillWidth: true
            Layout.topMargin: 20
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            text: sheet.title
            color: Theme.text
            font.pixelSize: Theme.title + 1
            font.weight: Font.DemiBold
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }
        Label {
            Layout.fillWidth: true
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            Layout.bottomMargin: 10
            visible: !!sheet.subtitle
            text: sheet.subtitle
            color: Theme.textMuted
            font.pixelSize: Theme.body
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
        }
        Item { visible: !sheet.subtitle; implicitHeight: 8 }
    }
}
