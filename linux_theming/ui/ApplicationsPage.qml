import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Choose which applications use the palette. Rows keep their position when a
// selection changes; only observed activity and availability order them.
ScrollView {
    id: page
    required property QtObject controller
    readonly property var s: controller.state
    property bool showAll: false
    signal detailsRequested(var component)
    contentWidth: availableWidth
    clip: true

    function selected(id) { return s.profile.components.indexOf(id) >= 0 }
    function group(c) { return c.running || c.current_session ? 0 : c.installed === true ? 1 : 2 }
    readonly property var visibleComponents: s.overview.components.filter(c => c.supported || showAll || c.installed || c.running || c.configs.some(f => f.exists))
    readonly property int hiddenCount: s.overview.components.length - visibleComponents.length
    readonly property var connecting: s.overview.components.filter(c => selected(c.id) && !c.managed).map(c => c.name)
    readonly property var restoring: s.overview.components.filter(c => !selected(c.id) && c.managed).map(c => c.name)

    function description(c) {
        if (c.wallpaper_provider && !c.supported) return "Used by the wallpaper option on the Theme page when it is compatible with your session."
        if (!c.supported) return "Detected only. Theme changes are not supported yet."
        if (c.installed === false) return "Not found on this computer. Nothing will be installed."
        return c.capability || ""
    }

    ColumnLayout {
        width: page.availableWidth - 12
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 6
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text { text: "Applications"; color: Theme.text; font.pixelSize: Theme.heading; font.weight: Font.DemiBold }
                Body {
                    Layout.fillWidth: true
                    text: "Turn on the applications that should use the palette. Their other settings are kept, and nothing changes until you review and apply."
                }
            }
        }
        Banner {
            Layout.fillWidth: true
            Layout.topMargin: 10
            visible: page.connecting.length > 0 || page.restoring.length > 0
            tone: "warning"
            title: "Changes waiting for review"
            body: (page.connecting.length ? "Will use the palette: " + page.connecting.join(", ") + ". " : "")
                + (page.restoring.length ? "Will get their previous colors back: " + page.restoring.join(", ") + "." : "")
        }
        Repeater {
            model: page.visibleComponents
            ColumnLayout {
                id: entry
                required property var modelData
                required property int index
                readonly property bool isSelected: page.selected(modelData.id)
                readonly property bool firstOfGroup: index === 0 || page.group(page.visibleComponents[index - 1]) !== page.group(modelData)
                Layout.fillWidth: true
                spacing: 0
                Text {
                    visible: entry.firstOfGroup
                    Layout.topMargin: 22
                    Layout.bottomMargin: 8
                    text: ["Running now", "Installed", "Not running or not found"][page.group(entry.modelData)]
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
                    Layout.bottomMargin: 6
                    implicitHeight: row.implicitHeight + 24
                    radius: Theme.radius
                    color: entry.isSelected ? Theme.raised : Theme.surface
                    border.color: Theme.border
                    RowLayout {
                        id: row
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 16
                        anchors.rightMargin: 12
                        spacing: 14
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Flow {
                                Layout.fillWidth: true
                                spacing: 6
                                Text {
                                    text: entry.modelData.name
                                    color: Theme.text
                                    font.pixelSize: Theme.bodyLarge + 1
                                    font.weight: Font.DemiBold
                                    height: 22
                                    verticalAlignment: Text.AlignVCenter
                                    textFormat: Text.PlainText
                                }
                                Text {
                                    text: entry.modelData.category
                                    color: Theme.textFaint
                                    font.pixelSize: Theme.caption
                                    height: 22
                                    verticalAlignment: Text.AlignVCenter
                                    rightPadding: 4
                                }
                                Chip { visible: !!entry.modelData.current_session; text: "Active session" }
                                Chip { visible: !!entry.modelData.running && !entry.modelData.current_session; text: "Running" }
                                Chip { visible: entry.modelData.installed === false; text: "Not found"; tone: "faint" }
                                Chip { visible: !!entry.modelData.managed; text: "Managed by Linux Theming"; tone: "accent"; iconName: "check" }
                                Chip { visible: entry.isSelected && !entry.modelData.managed; text: "Will use palette"; tone: "warning" }
                                Chip { visible: !entry.isSelected && !!entry.modelData.managed; text: "Will restore previous colors"; tone: "warning" }
                            }
                            Body {
                                Layout.fillWidth: true
                                text: page.description(entry.modelData)
                                font.pixelSize: Theme.caption + 1
                            }
                        }
                        Command {
                            objectName: "details-" + entry.modelData.id
                            compact: true
                            quiet: true
                            text: "Details"
                            iconName: "info"
                            enabled: !page.s.busy
                            Accessible.name: "Configuration details for " + entry.modelData.name
                            onClicked: page.detailsRequested(entry.modelData)
                        }
                        Toggle {
                            visible: !!entry.modelData.supported
                            objectName: "connect-" + entry.modelData.id
                            text: entry.modelData.id === "swaybg" ? "Use image" : ["gnome", "xfce"].indexOf(entry.modelData.id) >= 0 ? "Use appearance" : "Use palette"
                            Layout.preferredWidth: 150
                            checked: entry.isSelected
                            enabled: !page.s.busy && page.s.loaded && (entry.modelData.installed !== false || checked)
                            Accessible.name: text + " in " + entry.modelData.name
                            onClicked: {
                                page.controller.selectComponent(entry.modelData.id, !page.selected(entry.modelData.id))
                                checked = Qt.binding(function() { return page.selected(entry.modelData.id) })
                            }
                        }
                        Text {
                            visible: !entry.modelData.supported
                            Layout.preferredWidth: 150
                            text: entry.modelData.category === "Wallpaper" ? "Automatic wallpaper" : "Detection only"
                            font.pixelSize: Theme.caption
                            color: Theme.textFaint
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 12
            Command {
                objectName: "showAllComponents"
                compact: true
                quiet: true
                visible: page.hiddenCount > 0 || page.showAll
                iconName: page.showAll ? "chevron-down" : "chevron-right"
                text: page.showAll ? "Hide applications that were not found" : "Show " + page.hiddenCount + " more that were not found"
                onClicked: page.showAll = !page.showAll
            }
        }
        Body {
            Layout.fillWidth: true
            Layout.topMargin: 10
            Layout.bottomMargin: 8
            text: "Detection checks common configuration locations and your running applications. Custom launch options and sandboxed apps may differ."
            font.pixelSize: Theme.caption
            color: Theme.textFaint
        }
    }
}
