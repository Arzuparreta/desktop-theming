import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Mutually exclusive options. Each option: { value, label, icon?, objectName?, enabled?, description? }.
Rectangle {
    id: group
    property var options: []
    property string current: ""
    property bool interactive: true
    property string accessibleName: ""
    signal picked(string value)
    // Arrow keys move between options and pick the neighbour, like radio buttons.
    function step(from, delta) {
        for (let i = from + delta; i >= 0 && i < options.length; i += delta) {
            const item = buttons.itemAt(i)
            if (item && item.enabled) {
                item.forceActiveFocus(Qt.TabFocusReason)
                picked(options[i].value)
                return
            }
        }
    }
    implicitHeight: 34
    implicitWidth: row.implicitWidth + 6
    radius: Theme.radius
    color: Theme.canvas
    border.color: Theme.border
    Accessible.role: Accessible.Grouping
    Accessible.name: accessibleName
    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 3
        spacing: 2
        Repeater {
            id: buttons
            model: group.options
            Button {
                id: option
                required property var modelData
                required property int index
                objectName: modelData.objectName || ""
                Keys.onLeftPressed: group.step(index, -1)
                Keys.onRightPressed: group.step(index, 1)
                Layout.fillWidth: true
                Layout.fillHeight: true
                checkable: true
                checked: group.current === modelData.value
                enabled: group.interactive && modelData.enabled !== false
                hoverEnabled: true
                activeFocusOnTab: true
                leftPadding: 12
                rightPadding: 12
                topPadding: 0
                bottomPadding: 0
                text: modelData.label
                font.pixelSize: Theme.body
                font.weight: checked ? Font.DemiBold : Font.Normal
                Accessible.role: Accessible.RadioButton
                Accessible.checked: checked
                Accessible.description: modelData.description || ""
                ToolTip.visible: hovered && !!modelData.description
                ToolTip.text: modelData.description || ""
                ToolTip.delay: 500
                onClicked: {
                    group.picked(modelData.value)
                    checked = Qt.binding(function() { return group.current === option.modelData.value })
                }
                contentItem: Item {
                    implicitWidth: content.implicitWidth
                    implicitHeight: content.implicitHeight
                    RowLayout {
                        id: content
                        anchors.centerIn: parent
                        spacing: 6
                        Icon {
                            visible: !!option.modelData.icon
                            name: option.modelData.icon || ""
                            size: 15
                            color: !option.enabled ? Theme.disabled : option.checked ? Theme.accent : Theme.textMuted
                        }
                        Text {
                            text: option.text
                            font: option.font
                            color: !option.enabled ? Theme.disabled : option.checked ? Theme.text : Theme.textMuted
                        }
                    }
                }
                background: Rectangle {
                    radius: Theme.radius - 2
                    color: option.checked ? Theme.accentSoft : option.hovered && option.enabled ? Theme.raised : "transparent"
                    border.width: option.visualFocus ? 2 : option.checked ? 1 : 0
                    border.color: option.visualFocus ? Theme.focus : Theme.accentBorder
                }
            }
        }
    }
}
