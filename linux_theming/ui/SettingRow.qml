import QtQuick
import QtQuick.Layouts

// One row of a SettingsGroup: a title, an optional caption and extra content
// on the left, the row's own controls on the right. A caption can instead run
// below the whole row when the controls leave too little room beside them.
Item {
    id: row
    property string title: ""
    property string caption: ""
    property color captionColor: Theme.textFaint
    property bool captionBelow: false
    property bool divider: true
    // The caption shown below the row (captionBelow).
    property alias captionItem: captionText
    property alias extra: extraColumn.data
    default property alias controls: trailing.data
    Layout.fillWidth: true
    Layout.fillHeight: true
    implicitHeight: Math.max(40, content.implicitHeight + 20)
    Rectangle {
        visible: row.divider
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 14
        height: 1
        color: Theme.border
    }
    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 14
        anchors.rightMargin: 10
        spacing: 6
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                Text {
                    Layout.fillWidth: true
                    text: row.title
                    color: Theme.text
                    font.pixelSize: Theme.body
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                }
                Text {
                    id: sideCaption
                    Layout.fillWidth: true
                    visible: !!row.caption && !row.captionBelow
                    text: row.caption
                    color: row.captionColor
                    font.pixelSize: Theme.caption
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                    lineHeight: 1.15
                }
                ColumnLayout {
                    id: extraColumn
                    Layout.fillWidth: true
                    Layout.topMargin: 3
                    visible: children.length > 0
                    spacing: 0
                }
            }
            RowLayout {
                id: trailing
                Layout.alignment: Qt.AlignVCenter
                spacing: 6
            }
        }
        Text {
            id: captionText
            Layout.fillWidth: true
            visible: !!row.caption && row.captionBelow
            text: row.caption
            color: row.captionColor
            font.pixelSize: Theme.caption
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
            lineHeight: 1.15
        }
    }
}
