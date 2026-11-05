import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    required property QtObject controller
    required property real windowWidth
    required property real windowHeight
    readonly property var info: controller.state.connection
    signal exportRequested(string component)
    objectName: "connectionDialog"
    anchors.centerIn: parent
    width: Math.min(windowWidth - 32, 660)
    height: Math.min(windowHeight - 48, Math.max(320, form.implicitHeight + 130))
    modal: true
    title: info.blocked ? "Configuration needs attention" : "Use this palette in " + (info.name || "this terminal")
    closePolicy: Popup.CloseOnEscape
    background: Rectangle { color: "#202228"; border.color: "#41434c"; radius: 10 }
    onOpened: { localCopy.checked = false; replaceColors.checked = false; details.checked = false }
    onRejected: controller.cancelConnection()
    contentItem: ColumnLayout {
        spacing: 16
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            ColumnLayout {
                id: form
                width: parent.width
                spacing: 14
                Body {
                    Layout.fillWidth: true
                    text: info.blocked
                        ? info.explanation || "This configuration cannot be changed safely yet."
                        : "Before selecting this terminal, confirm how its existing configuration should be handled. Nothing changes until you review and apply."
                }
                Choice {
                    id: localCopy
                    objectName: "allowLocalCopy"
                    Layout.fillWidth: true
                    visible: !!info.linked && !info.blocked
                    text: "Create a separate local configuration"
                }
                Body {
                    Layout.fillWidth: true
                    visible: localCopy.visible
                    text: "The current configuration links to another file. Its contents will be copied and the original left untouched. Future edits to the original will no longer reach this terminal. Undo can restore the link."
                }
                Choice {
                    id: replaceColors
                    objectName: "allowReplaceColors"
                    Layout.fillWidth: true
                    visible: !!info.existingColors && !info.blocked
                    text: "Replace the existing color settings"
                }
                Body {
                    Layout.fillWidth: true
                    visible: replaceColors.visible
                    text: "Use the previewed palette instead of the current colors. Fonts, shortcuts and other preferences stay as they are. Included color files are preserved."
                }
                Body {
                    Layout.fillWidth: true
                    visible: !!info.blocked
                    color: "#f0b8b5"
                    text: "The current files will be preserved. Exporting creates a theme file; you would still need to include it in your own configuration."
                }
                Command {
                    id: details
                    checkable: true
                    quiet: true
                    text: checked ? "Hide configuration details" : "Show configuration details"
                }
                ColumnLayout {
                    visible: details.checked
                    Layout.fillWidth: true
                    spacing: 10
                    Body { Layout.fillWidth: true; text: (info.path || "") + (info.target ? "\nLinked original: " + info.target : ""); font.family: "monospace"; font.pixelSize: 12 }
                    Repeater { model: info.issues || []; Body { required property string modelData; Layout.fillWidth: true; text: modelData; color: "#f0b8b5" } }
                    Repeater {
                        model: info.sources || []
                        Body { required property var modelData; Layout.fillWidth: true; text: modelData.path + ":" + modelData.line + " · " + modelData.directive + " " + modelData.value; font.pixelSize: 12 }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Command { objectName: "connectionExport"; text: "Export theme…"; quiet: true; onClicked: dialog.exportRequested(info.id) }
            Item { Layout.fillWidth: true }
            Command { objectName: "cancelConnection"; text: "Cancel"; onClicked: controller.cancelConnection() }
            Command {
                objectName: "confirmConnection"
                visible: !info.blocked
                text: info.continueReview ? "Continue to review" : "Use this palette"
                primary: true
                enabled: !controller.state.busy && (!info.linked || localCopy.checked) && (!info.existingColors || replaceColors.checked)
                onClicked: controller.confirmConnection(localCopy.checked, replaceColors.checked)
            }
        }
    }
}
