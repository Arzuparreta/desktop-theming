import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: page
    required property QtObject controller
    required property string latestActive
    readonly property var s: controller.state
    signal previewRequested(string wallpaper, string polarity, string mode)
    contentWidth: availableWidth
    clip: true

    function statusText(status) {
        return ({"applied": "Applied", "undone": "Undone", "rolled-back": "Cancelled after an error",
                 "prepared": "Interrupted", "recovery-needed": "Recovery needed",
                 "undoing": "Undo interrupted"})[status] || "Unknown state"
    }
    function statusTone(status) {
        return ({"applied": "accent", "undone": "neutral", "rolled-back": "faint"})[status] || "danger"
    }
    function name(id) {
        const item = s.overview.components.find(c => c.id === id)
        return item ? item.name : id
    }
    function when(value) {
        const date = new Date(value)
        return isNaN(date.getTime()) ? "" : date.toLocaleString(Qt.locale(), "d MMM yyyy, HH:mm")
    }

    ColumnLayout {
        width: page.availableWidth - 12
        spacing: 10
        Text { text: "History"; color: Theme.text; font.pixelSize: Theme.heading; font.weight: Font.DemiBold }
        Body {
            Layout.fillWidth: true
            Layout.bottomMargin: 8
            text: "Every applied change is kept here. Undo restores the previous files after showing you exactly what will change; later edits to other settings are preserved."
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.topMargin: 40
            visible: !page.s.overview.history.length
            spacing: 8
            Icon { Layout.alignment: Qt.AlignHCenter; name: "history"; size: 28; color: Theme.textFaint }
            Text { Layout.alignment: Qt.AlignHCenter; text: "No changes yet"; color: Theme.text; font.pixelSize: Theme.bodyLarge; font.weight: Font.DemiBold }
            Body { Layout.alignment: Qt.AlignHCenter; text: "Applied themes and recovery options will appear here." }
        }
        Repeater {
            model: page.s.overview.history
            Rectangle {
                id: card
                required property var modelData
                required property int index
                readonly property bool pending: ["prepared", "recovery-needed", "undoing"].indexOf(modelData.status) >= 0
                readonly property bool latest: modelData.id === page.latestActive
                readonly property var themeInfo: modelData.theme || null
                Layout.fillWidth: true
                implicitHeight: layout.implicitHeight + 24
                radius: Theme.radius
                color: card.latest ? Theme.raised : Theme.surface
                border.color: card.pending ? Theme.dangerBorder : Theme.border
                RowLayout {
                    id: layout
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 14
                    Rectangle {
                        Layout.preferredWidth: 96
                        Layout.preferredHeight: 54
                        Layout.alignment: Qt.AlignTop
                        radius: 5
                        color: Theme.canvas
                        clip: true
                        Image {
                            id: thumb
                            anchors.fill: parent
                            source: card.themeInfo && card.themeInfo.wallpaper ? page.controller.fileUrl(card.themeInfo.wallpaper) : ""
                            sourceSize: Qt.size(192, 108)
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            cache: false
                        }
                        Icon {
                            anchors.centerIn: parent
                            visible: thumb.status !== Image.Ready
                            name: card.modelData.migration ? "refresh" : card.themeInfo ? "palette" : "history"
                            size: 20
                            color: Theme.textFaint
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        Flow {
                            Layout.fillWidth: true
                            spacing: 8
                            Text {
                                height: 22
                                verticalAlignment: Text.AlignVCenter
                                text: card.modelData.migration ? "Data migration to Linux Theming"
                                    : card.themeInfo ? ((card.themeInfo.wallpaper || "Default colors").split("/").pop()
                                        + " · " + (card.themeInfo.polarity === "light" ? "Light" : "Dark")
                                        + (card.themeInfo.effective === "safe" && card.themeInfo.wallpaper ? " · Default colors" : ""))
                                    : "Theme change"
                                color: Theme.text
                                font.pixelSize: Theme.bodyLarge
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                                elide: Text.ElideMiddle
                                width: Math.min(implicitWidth, layout.width - 320)
                            }
                            Chip {
                                readonly property bool current: card.latest && card.modelData.status === "applied"
                                text: current ? "Applied now" : page.statusText(card.modelData.status)
                                tone: current ? "accent" : page.statusTone(card.modelData.status)
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.when(card.modelData.created) + " · "
                                + (card.modelData.components.length ? card.modelData.components.map(page.name).join(", ") : "Palette only")
                                + " · " + card.modelData.files + (card.modelData.files === 1 ? " file" : " files")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption + 1
                            wrapMode: Text.Wrap
                            textFormat: Text.PlainText
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: card.latest && card.modelData.status === "applied" && !card.modelData.migration
                            text: "Undo returns to " + (card.modelData.previous_theme
                                ? ((card.modelData.previous_theme.wallpaper || "Default colors").split("/").pop() + " · " + (card.modelData.previous_theme.polarity === "light" ? "Light" : "Dark"))
                                : "your settings from before Linux Theming") + "."
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption + 1
                            wrapMode: Text.Wrap
                            textFormat: Text.PlainText
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !card.pending && card.modelData.status === "applied" && !card.latest
                            text: "Undo the newer changes first."
                            color: Theme.textFaint
                            font.pixelSize: Theme.caption
                        }
                    }
                    Command {
                        objectName: "reuse-" + card.index
                        visible: !!card.themeInfo && !card.pending && !(card.latest && card.modelData.status === "applied" && !page.s.pending)
                        compact: true
                        quiet: true
                        text: "Preview again"
                        enabled: !page.s.busy && page.s.loaded
                        Accessible.description: "Load this image and mode as a preview. Nothing is applied until you review."
                        onClicked: page.previewRequested(card.themeInfo.wallpaper || "", card.themeInfo.polarity || "", card.themeInfo.mode || "")
                    }
                    Command {
                        objectName: "undo-" + card.index
                        text: card.pending ? "Recover…" : "Undo…"
                        iconName: "undo"
                        compact: true
                        danger: card.pending
                        visible: card.pending || card.modelData.status === "applied"
                        enabled: !page.s.busy && card.latest
                        onClicked: page.controller.reviewUndo(card.modelData.id, card.pending)
                    }
                }
            }
        }
        Body {
            Layout.fillWidth: true
            Layout.topMargin: 6
            visible: page.s.overview.history.length > 0 && page.s.overview.history.length < 3
            text: "Earlier changes will appear here as you apply new themes."
            font.pixelSize: Theme.caption
            color: Theme.textFaint
        }
        Item { implicitHeight: 8 }
    }
}
