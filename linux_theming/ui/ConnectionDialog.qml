import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Required decisions before an application can use the palette. Every choice
// starts unchecked; cancelling leaves the selection and files unchanged.
Sheet {
    id: dialog
    required property QtObject controller
    required property real windowWidth
    required property real windowHeight
    readonly property var info: controller.state.connection
    readonly property bool needsCopy: !!info.linked && !info.blocked
    readonly property bool needsReplace: !!info.existingColors && !info.blocked
    readonly property bool ready: (!info.linked || localCopy.checked) && (!info.existingColors || replaceColors.checked)
    signal exportRequested(string component)
    objectName: "connectionDialog"
    width: Math.min(windowWidth - 40, 640)
    height: Math.min(windowHeight - 40, implicitHeight)
    closePolicy: Popup.CloseOnEscape
    title: info.blocked ? (info.name || "This application") + " can't be changed safely" : "Use the palette in " + (info.name || "this application")
    subtitle: info.blocked ? "" : "Confirm how its current settings should be handled. Nothing changes until you review and apply."
    onOpened: {
        localCopy.checked = false; replaceColors.checked = false; details.checked = false
        if (needsCopy) localCopy.forceActiveFocus(Qt.TabFocusReason); else if (needsReplace) replaceColors.forceActiveFocus(Qt.TabFocusReason)
    }
    onRejected: controller.cancelConnection()

    function homePath(path) {
        const home = controller.homePath
        return home && path && path.startsWith(home + "/") ? "~" + path.slice(home.length) : path
    }

    component Decision: Rectangle {
        id: card
        property alias choice: box
        property string title
        property string body
        property string objectId
        Layout.fillWidth: true
        implicitHeight: content.implicitHeight + 26
        radius: Theme.radius
        color: box.checked ? Theme.accentSoft : Theme.raised
        border.color: box.checked ? Theme.accentBorder : Theme.border
        ColumnLayout {
            id: content
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 10
            anchors.rightMargin: 14
            spacing: 2
            Choice {
                id: box
                objectName: card.objectId
                Layout.fillWidth: true
                text: card.title
                font.weight: Font.DemiBold
                Accessible.description: card.body
            }
            Body {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                text: card.body
                font.pixelSize: Theme.caption + 1
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: 12
        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: form.implicitHeight
            clip: true
            contentWidth: availableWidth
            ColumnLayout {
                id: form
                width: scroll.availableWidth
                spacing: 12
                Banner {
                    Layout.fillWidth: true
                    visible: !!dialog.info.blocked
                    tone: "danger"
                    title: dialog.info.explanation || "This configuration cannot be changed safely yet."
                    body: dialog.info.canExport === false ? "Your current preferences are kept. Resolve the issue in your desktop settings, then try again."
                        : "Your current files are kept. You can export a theme file and include it in your own configuration instead."
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: !!dialog.info.linked && !dialog.info.blocked
                    spacing: 10
                    Icon { name: "link"; size: 16; color: Theme.textMuted; Layout.alignment: Qt.AlignTop; Layout.topMargin: 2 }
                    Body {
                        Layout.fillWidth: true
                        text: dialog.homePath(dialog.info.path || "") + " is a link to " + (dialog.homePath(dialog.info.target || "") || "another file") + "."
                        color: Theme.text
                    }
                }
                Decision {
                    id: copyCard
                    visible: dialog.needsCopy
                    objectId: "allowLocalCopy"
                    title: "Make a separate local copy"
                    body: "The application gets its own copy of the configuration. "
                        + (dialog.info.target ? dialog.homePath(dialog.info.target) : "The linked original") + " stays untouched, but future edits to it will no longer reach this application. Undo restores the link."
                }
                Decision {
                    id: replaceCard
                    visible: dialog.needsReplace
                    objectId: "allowReplaceColors"
                    title: dialog.info.native ? "Replace the native appearance preferences" : dialog.info.imageOnly ? "Replace the configured background" : "Replace the current colors"
                    body: dialog.info.native ? "Only the preferences described in the review change. Each previous value is kept for undo."
                        : dialog.info.imageOnly ? "Use the selected image in the Sway background configuration. The running background changes only when you reload Sway yourself."
                        : ((dialog.info.sources || []).length ? (dialog.info.sources.length === 1 ? "1 existing color setting" : dialog.info.sources.length + " existing color settings") + " will be replaced by the previewed palette. "
                           : "The previewed palette replaces the existing color settings. ")
                          + "Fonts, shortcuts and other preferences stay as they are; included color files are kept."
                }
                Body {
                    Layout.fillWidth: true
                    visible: !!dialog.info.capability && !dialog.info.blocked
                    text: dialog.info.capability || ""
                    font.pixelSize: Theme.caption + 1
                    color: Theme.textFaint
                }
                Command {
                    id: details
                    compact: true
                    quiet: true
                    checkable: true
                    iconName: checked ? "chevron-down" : "chevron-right"
                    text: checked ? "Hide configuration details" : "Show configuration details"
                }
                ColumnLayout {
                    visible: details.checked
                    Layout.fillWidth: true
                    spacing: 8
                    Code {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(220, 40 + 18 * (2 + (dialog.info.sources || []).length + (dialog.info.issues || []).length))
                        text: (dialog.info.path || "") + (dialog.info.target ? "\n→ " + dialog.info.target : "")
                            + ((dialog.info.issues || []).length ? "\n\n" + dialog.info.issues.join("\n") : "")
                            + ((dialog.info.sources || []).length ? "\n\nExisting color settings:\n" + dialog.info.sources.map(s => s.path + ":" + s.line + "  " + s.directive + " " + s.value).join("\n") : "")
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Command {
                objectName: "connectionExport"
                visible: dialog.info.canExport !== false
                compact: true
                quiet: !dialog.info.blocked
                iconName: "export"
                text: "Export theme file…"
                onClicked: dialog.exportRequested(dialog.info.id)
            }
            Body {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignRight
                visible: !dialog.info.blocked && !dialog.ready
                text: dialog.needsCopy && dialog.needsReplace ? "Confirm both to continue" : "Confirm the option above to continue"
                font.pixelSize: Theme.caption
                color: Theme.textFaint
            }
            Item { Layout.fillWidth: true; visible: !!dialog.info.blocked || dialog.ready }
            Command { objectName: "cancelConnection"; text: "Cancel"; onClicked: dialog.controller.cancelConnection() }
            Command {
                objectName: "confirmConnection"
                visible: !dialog.info.blocked
                text: dialog.info.continueReview ? "Continue to review" : dialog.info.native ? "Use these preferences" : dialog.info.imageOnly ? "Use this image" : "Use the palette"
                primary: true
                enabled: !dialog.controller.state.busy && dialog.ready
                onClicked: dialog.controller.confirmConnection(localCopy.checked, replaceColors.checked)
            }
        }
    }
    readonly property var localCopy: copyCard.choice
    readonly property var replaceColors: replaceCard.choice
}
