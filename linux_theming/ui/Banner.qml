import QtQuick
import QtQuick.Layouts

// Inline message with optional actions. Tones: info, success, warning, danger.
Rectangle {
    id: banner
    property string tone: "info"
    property string title: ""
    property string body: ""
    default property alias actions: actionRow.data
    readonly property color foreground: ({ success: Theme.accent, warning: Theme.warning, danger: Theme.danger })[tone] || Theme.info
    implicitHeight: layout.implicitHeight + 24
    radius: Theme.radius
    color: ({ success: Theme.accentSoft, warning: Theme.warningSoft, danger: Theme.dangerSoft })[tone] || Theme.infoSoft
    border.color: ({ success: Theme.accentBorder, warning: Theme.warningBorder, danger: Theme.dangerBorder })[tone] || Theme.infoBorder
    Accessible.role: Accessible.AlertMessage
    Accessible.name: title
    Accessible.description: body
    GridLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 14
        anchors.rightMargin: 12
        columns: banner.width > 620 ? 3 : 2
        columnSpacing: 12
        rowSpacing: 8
        Icon {
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: 1
            name: banner.tone === "success" ? "check" : banner.tone === "info" ? "info" : "alert"
            size: 18
            color: banner.foreground
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                Layout.fillWidth: true
                text: banner.title
                visible: !!text
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true
                text: banner.body
                visible: !!text
                color: Theme.textMuted
                font.pixelSize: Theme.body
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
            }
        }
        Item { visible: layout.columns === 2 && actionRow.children.length > 0; implicitWidth: 18 }
        RowLayout {
            id: actionRow
            Layout.alignment: layout.columns === 3 ? Qt.AlignVCenter | Qt.AlignRight : Qt.AlignLeft
            spacing: 6
        }
    }
}
