import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Shows the plain-language consequences first, then every exact change.
// Approval authorizes only this reviewed plan.
Sheet {
    id: dialog
    required property QtObject controller
    required property real windowWidth
    required property real windowHeight
    readonly property var s: controller.state
    readonly property var review: s.review || ({})
    // The user's own files first, then the app's generated themes and restoration records.
    readonly property var changes: {
        // Restoration records and the saved profile support undo; theme files are real changes.
        const record = c => /\/linux-theming\/(ownership|launcher)\/|\/linux-theming\/profile\.json$/.test(c.path || "") || c.role === "registration-record"
        const all = (review.changes || []).map(c => Object.assign({ record: record(c) }, c))
        return all.filter(c => !c.record).concat(all.filter(c => c.record))
    }
    readonly property int recordCount: changes.filter(c => c.record).length
    function firstAttentionChange() {
        const apps = attention.map(i => (i.app || "").toLowerCase()).filter(a => a)
        for (let i = 0; i < changes.length; ++i) {
            const label = (changes[i].label || "").toLowerCase()
            if (!changes[i].record && apps.some(a => label.startsWith(a))) return i
        }
        return 0
    }
    readonly property bool routine: review.level === "routine"
    readonly property bool undo: review.kind === "undo"
    readonly property var items: review.items || (review.summary || []).map(t => ({ text: t, tone: "info", app: "" }))
    readonly property var attention: items.filter(i => i.tone === "attention")
    property bool showChanges: false
    property int diffIndex: 0
    readonly property bool expanded: showChanges || !routine
    readonly property bool wide: width > 760

    objectName: "reviewDialog"
    width: Math.min(windowWidth - 40, expanded ? 1120 : 640)
    height: expanded ? windowHeight - 40 : Math.min(windowHeight - 40, implicitHeight)
    closePolicy: s.busy ? Popup.NoAutoClose : Popup.CloseOnEscape
    title: review.title || "Review changes"
    readonly property int ownCount: changes.length - recordCount
    subtitle: (review.kind === "apply"
        ? (s.profile.components.length ? s.profile.components.length + (s.profile.components.length === 1 ? " application" : " applications") : "No applications") + " · "
        : "")
        + countText + " · Nothing is written until you " + (review.kind === "apply" ? "apply" : "confirm")
    readonly property string countText: (ownCount || !recordCount ? ownCount : changes.length) + ((ownCount || !recordCount ? ownCount : changes.length) === 1 ? " change" : " changes")
        + (recordCount && ownCount ? " · undo data is saved" : "")
    function homePath(path) {
        const home = controller.homePath
        return home && path && path.startsWith(home + "/") ? "~" + path.slice(home.length) : path
    }
    onOpened: { technicalNotes.checked = false; showChanges = !routine; diffIndex = firstAttentionChange()
        // A closing consent dialog may restore focus afterwards; take it back for Cancel.
        cancelButton.forceActiveFocus(Qt.TabFocusReason)
        Qt.callLater(function() { if (dialog.visible) cancelButton.forceActiveFocus(Qt.TabFocusReason) })
    }
    onRejected: controller.cancelReview()

    // Modal popups block window shortcuts outside their own content.
    Shortcut {
        sequences: ["Alt+Return", "Alt+Enter"]
        enabled: dialog.visible && approveButton.enabled
        onActivated: dialog.controller.approve()
    }

    contentItem: ColumnLayout {
        spacing: 14
        // Decisions that need attention stay visible however long the summary is.
        Rectangle {
            visible: dialog.attention.length > 0
            Layout.fillWidth: true
            implicitHeight: attentionColumn.implicitHeight + 22
            radius: Theme.radius
            color: Theme.warningSoft
            border.color: Theme.warningBorder
            Accessible.role: Accessible.AlertMessage
            Accessible.name: "Needs your attention"
            ColumnLayout {
                id: attentionColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                spacing: 6
                Repeater {
                    model: dialog.attention
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 10
                        Icon { Layout.alignment: Qt.AlignTop; Layout.topMargin: 1; name: "alert"; size: 15; color: Theme.warning }
                        Text { Layout.fillWidth: true; text: modelData.text; color: Theme.text; wrapMode: Text.Wrap; textFormat: Text.PlainText; font.pixelSize: Theme.body }
                    }
                }
            }
        }
        ScrollView {
            id: summaryScroll
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(summary.implicitHeight, dialog.expanded ? Math.max(110, dialog.height * 0.3) : 420)
            ScrollBar.vertical.policy: summary.implicitHeight > height + 1 ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded
            contentWidth: availableWidth
            clip: true
            ColumnLayout {
                id: summary
                width: summaryScroll.availableWidth
                spacing: 10
                // Theme being applied
                Rectangle {
                    visible: dialog.review.kind === "apply"
                    Layout.fillWidth: true
                    implicitHeight: 64
                    radius: Theme.radius
                    color: Theme.raised
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 12
                        Rectangle {
                            Layout.preferredWidth: 78
                            Layout.preferredHeight: 44
                            radius: 4
                            color: (dialog.s.palette.special || ({})).background || Theme.canvas
                            clip: true
                            Image {
                                anchors.fill: parent
                                source: dialog.s.wallpaperUrl
                                sourceSize: Qt.size(156, 88)
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                visible: status === Image.Ready
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                Layout.fillWidth: true
                                text: (dialog.s.profile.wallpaper ? dialog.s.profile.wallpaper.split("/").pop() : "Default colors")
                                    + " · " + (dialog.s.profile.polarity === "light" ? "Light" : "Dark")
                                    + " · " + ((dialog.s.palette.effective || dialog.s.profile.mode) === "safe" ? "Default colors" : "Colors from image")
                                color: Theme.text
                                font.pixelSize: Theme.body
                                font.weight: Font.DemiBold
                                elide: Text.ElideMiddle
                                textFormat: Text.PlainText
                            }
                            Row {
                                spacing: 3
                                Repeater {
                                    model: 16
                                    Rectangle {
                                        required property int index
                                        width: 16
                                        height: 12
                                        radius: 2
                                        color: (dialog.s.palette.colors || ({}))["color" + index] || Theme.hover
                                    }
                                }
                            }
                        }
                    }
                }
                Repeater {
                    model: dialog.items
                    RowLayout {
                        id: line
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        Layout.topMargin: !!modelData.app && index > 0 && dialog.items[index - 1].app !== modelData.app ? 6 : 0
                        spacing: 10
                        visible: modelData.tone !== "attention" && ((modelData.tone !== "lead" && modelData.tone !== "theme") || dialog.review.kind !== "apply")
                        Icon {
                            Layout.alignment: Qt.AlignTop
                            Layout.topMargin: 1
                            name: line.modelData.tone === "attention" ? "alert" : line.modelData.tone === "change" ? "check" : line.modelData.tone === "note" ? "" : "info"
                            size: 15
                            color: line.modelData.tone === "attention" ? Theme.warning : line.modelData.tone === "change" ? Theme.accent : Theme.textFaint
                        }
                        Item { visible: line.modelData.tone === "note"; implicitWidth: 15 }
                        Text {
                            Layout.fillWidth: true
                            text: line.modelData.text
                            wrapMode: Text.Wrap
                            textFormat: Text.PlainText
                            font.pixelSize: line.modelData.tone === "note" ? Theme.caption + 1 : Theme.body
                            font.weight: line.modelData.tone === "change" ? Font.DemiBold : Font.Normal
                            color: line.modelData.tone === "attention" ? Theme.warning
                                : line.modelData.tone === "note" ? Theme.textFaint
                                : line.modelData.tone === "change" ? Theme.text : Theme.textMuted
                        }
                    }
                }
            }
        }

        Command {
            objectName: "toggleExactChanges"
            visible: dialog.routine
            compact: true
            quiet: true
            iconName: dialog.showChanges ? "chevron-down" : "chevron-right"
            text: dialog.showChanges ? "Hide exact changes" : "Show exact changes (" + (dialog.ownCount || dialog.changes.length) + ")"
            Accessible.description: dialog.countText
            onClicked: dialog.showChanges = !dialog.showChanges
        }

        // Exact changes: file list and the selected file's diff.
        GridLayout {
            visible: dialog.expanded
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: dialog.wide ? 2 : 1
            columnSpacing: 12
            rowSpacing: 10
            Rectangle {
                Layout.preferredWidth: dialog.wide ? 280 : -1
                Layout.fillWidth: !dialog.wide
                Layout.fillHeight: dialog.wide
                Layout.preferredHeight: dialog.wide ? -1 : Math.min(files.contentHeight + 10, 130)
                color: Theme.canvas
                radius: Theme.radius
                border.color: Theme.border
                ListView {
                    id: files
                    objectName: "reviewFiles"
                    anchors.fill: parent
                    anchors.margins: 5
                    clip: true
                    model: dialog.changes
                    currentIndex: dialog.diffIndex
                    spacing: 2
                    keyNavigationEnabled: true
                    activeFocusOnTab: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: files.contentHeight > files.height + 1 ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded }
                    Accessible.role: Accessible.List
                    Accessible.name: "Changed files and settings"
                    onCurrentIndexChanged: dialog.diffIndex = currentIndex
                    delegate: ItemDelegate {
                        id: fileRow
                        required property var modelData
                        required property int index
                        width: files.width - 8
                        padding: 8
                        hoverEnabled: true
                        activeFocusOnTab: false
                        highlighted: dialog.diffIndex === index
                        Accessible.name: modelData.label + ", " + modelData.path
                        onClicked: { files.currentIndex = index; dialog.diffIndex = index }
                        contentItem: ColumnLayout {
                            spacing: 2
                            Text {
                                visible: fileRow.modelData.record && (fileRow.index === 0 || !dialog.changes[fileRow.index - 1].record)
                                Layout.fillWidth: true
                                Layout.topMargin: fileRow.index > 0 ? 6 : 0
                                Layout.bottomMargin: 4
                                text: "Undo records"
                                color: Theme.textFaint
                                font.pixelSize: Theme.caption
                                font.weight: Font.DemiBold
                                font.capitalization: Font.AllUppercase
                            }
                            Text {
                                Layout.fillWidth: true
                                text: fileRow.modelData.label || fileRow.modelData.path
                                color: fileRow.modelData.record ? Theme.textMuted : Theme.text
                                font.pixelSize: Theme.body
                                font.weight: fileRow.highlighted ? Font.DemiBold : Font.Normal
                                elide: Text.ElideRight
                                textFormat: Text.PlainText
                            }
                            Text {
                                Layout.fillWidth: true
                                text: dialog.homePath(fileRow.modelData.path || "")
                                color: Theme.textFaint
                                font.pixelSize: Theme.caption
                                elide: Text.ElideLeft
                                textFormat: Text.PlainText
                            }
                        }
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: fileRow.highlighted ? Theme.hover : fileRow.hovered ? Theme.raised : "transparent"
                            border.width: files.activeFocus && files.currentIndex === fileRow.index ? 2 : 0
                            border.color: Theme.focus
                        }
                    }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 6
                Text {
                    Layout.fillWidth: true
                    text: dialog.homePath((dialog.changes[dialog.diffIndex] || ({})).path || "")
                    color: Theme.textFaint
                    font.pixelSize: Theme.caption
                    font.family: Theme.mono
                    elide: Text.ElideMiddle
                    textFormat: Text.PlainText
                    visible: !!text
                }
                Code {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 120
                    diff: true
                    text: (dialog.changes[dialog.diffIndex] || ({})).diff || (dialog.undo ? "Files already match their original state. Restore completes recovery by marking this change as undone." : "No file changes.")
                }
            }
        }

        Command {
            id: technicalNotes
            compact: true
            quiet: true
            checkable: true
            iconName: checked ? "chevron-down" : "chevron-right"
            text: checked ? "Hide technical notes" : "Show technical notes (" + (dialog.review.warnings || []).length + ")"
            visible: !!(dialog.review.warnings || []).length
        }
        Body {
            visible: technicalNotes.checked
            Layout.fillWidth: true
            text: (dialog.review.warnings || []).join("\n")
            font.pixelSize: Theme.caption
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Icon { name: "undo"; size: 14; color: Theme.textFaint }
            Body {
                Layout.fillWidth: true
                text: dialog.undo ? "Restoration is checked for conflicts; later edits are kept." : "You can undo this from History."
                font.pixelSize: Theme.caption + 1
                elide: Text.ElideRight
                maximumLineCount: 2
            }
            Command { id: cancelButton; objectName: "cancelReview"; text: "Cancel"; enabled: !dialog.s.busy; onClicked: dialog.controller.cancelReview() }
            Command {
                id: approveButton
                objectName: "approveChanges"
                primary: true
                text: dialog.undo ? "Restore" : dialog.review.kind === "migration" ? "Migrate" : dialog.review.kind === "launcher" ? "Confirm" : "Apply"
                hint: "Alt+Enter"
                enabled: !dialog.s.busy && (dialog.undo || !!dialog.review.allowEmpty || dialog.changes.length > 0)
                onClicked: dialog.controller.approve()
            }
        }
    }
}
