import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Button with three emphasis levels: primary (one per view), default and quiet.
Button {
    id: control
    property bool primary: false
    property bool quiet: false
    property bool danger: false
    property bool compact: false
    property string iconName: ""
    property string hint: ""
    readonly property color foreground: !enabled ? Theme.disabled
        : primary ? Theme.accentInk
        : danger ? Theme.danger
        : quiet ? Theme.accent : Theme.text
    implicitHeight: compact ? 30 : Theme.controlHeight
    implicitWidth: Math.max(implicitHeight, contentItem.implicitWidth + leftPadding + rightPadding)
    // Buttons keep their label inside layouts; long text beside them wraps instead.
    Layout.minimumWidth: implicitWidth
    leftPadding: text ? (compact ? 10 : 14) : 0
    rightPadding: leftPadding
    topPadding: 0
    bottomPadding: 0
    hoverEnabled: true
    font.pixelSize: Theme.body
    font.weight: primary ? Font.DemiBold : Font.Normal
    activeFocusOnTab: true
    ToolTip.visible: !text && hovered && !!Accessible.name
    ToolTip.text: Accessible.name + (hint ? " · " + hint : "")
    ToolTip.delay: 400
    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        RowLayout {
            id: row
            anchors.centerIn: parent
            width: Math.min(implicitWidth, parent.width)
            spacing: 7
            Icon {
                visible: !!control.iconName
                name: control.iconName
                size: control.compact ? 15 : 16
                color: control.foreground
            }
            Text {
                visible: !!control.text
                Layout.fillWidth: true
                // Layouts allocate whole pixels; a fractional label width would elide.
                Layout.preferredWidth: Math.ceil(implicitWidth)
                Layout.maximumWidth: Math.ceil(implicitWidth)
                text: control.text
                font: control.font
                color: control.foreground
                elide: Text.ElideRight
            }
            Text {
                visible: !!control.hint && !!control.text
                text: control.hint
                font.pixelSize: Theme.caption
                color: control.primary ? Qt.rgba(Theme.accentInk.r, Theme.accentInk.g, Theme.accentInk.b, 0.68) : Theme.textFaint
            }
        }
    }
    background: Item {
        implicitHeight: control.implicitHeight
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: Theme.radius + 3
            color: "transparent"
            border.width: 2
            border.color: Theme.focus
            visible: control.visualFocus
        }
        Rectangle {
            anchors.fill: parent
            radius: Theme.radius
            color: control.primary
                ? (!control.enabled ? Theme.raised : control.down ? Theme.accentPressed : control.hovered ? Theme.accentHover : Theme.accent)
                : control.down ? Theme.pressed
                : control.hovered && control.enabled ? Theme.hover
                : control.quiet || !control.enabled ? "transparent" : Theme.raised
            border.width: control.quiet || (control.primary && control.enabled) ? 0 : 1
            border.color: control.danger && control.enabled ? Theme.dangerBorder : Theme.border
        }
    }
}
