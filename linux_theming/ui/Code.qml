import QtQuick
import QtQuick.Controls

// Selectable read-only text. Unified diffs are colored by line type.
Rectangle {
    id: panel
    property string text: ""
    property bool diff: false
    color: Theme.canvas
    radius: Theme.radius
    border.color: Theme.border
    clip: true
    function escapeHtml(value) { return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
    function renderDiff(value) {
        const lines = value.split("\n")
        const rows = lines.map(function(line) {
            let color = Theme.text, background = ""
            if (line.startsWith("+++") || line.startsWith("---")) color = Theme.textFaint
            else if (line.startsWith("+")) { color = Theme.diffAddText; background = Theme.diffAdd }
            else if (line.startsWith("-")) { color = Theme.diffRemoveText; background = Theme.diffRemove }
            else if (line.startsWith("@@")) color = Theme.diffHunk
            else color = Theme.textMuted
            return "<tr><td" + (background ? " bgcolor=\"" + background + "\"" : "") + "><span style=\"color:" + color + "\">"
                + (escapeHtml(line) || "&nbsp;") + "</span></td></tr>"
        })
        return "<table width=\"100%\" cellspacing=\"0\" cellpadding=\"1\" style=\"white-space:pre-wrap\">" + rows.join("") + "</table>"
    }
    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.margins: 1
        contentWidth: availableWidth
        contentHeight: editor.height + 24
        clip: true
        TextEdit {
            id: editor
            objectName: "fileContents"
            x: 12
            y: 12
            width: Math.max(0, scroll.availableWidth - 24)
            height: contentHeight
            readOnly: true
            selectByMouse: true
            persistentSelection: true
            textFormat: panel.diff ? TextEdit.RichText : TextEdit.PlainText
            text: panel.diff ? panel.renderDiff(panel.text) : panel.text
            wrapMode: TextEdit.WrapAnywhere
            color: Theme.textMuted
            selectedTextColor: Theme.text
            selectionColor: Theme.accentBorder
            font.family: Theme.mono
            font.pixelSize: 12
            Accessible.name: "File contents"
        }
    }
}
