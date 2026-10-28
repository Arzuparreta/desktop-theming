# Terminal colors for zsh plugins — source after zsh-syntax-highlighting
# and zsh-autosuggestions.
#
# Only ANSI indices are used: walltheme guarantees their contrast against
# the terminal background in every mode (dark/light, adaptive/safe).
# Hex colors here would ignore the theme and break on some backgrounds.

# Suggestions and comments: color8 is the "dim but readable" slot.
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=8'

typeset -gA ZSH_HIGHLIGHT_STYLES
ZSH_HIGHLIGHT_STYLES[unknown-token]='fg=1,bold'
ZSH_HIGHLIGHT_STYLES[comment]='fg=8'          # default is black: invisible on dark themes
ZSH_HIGHLIGHT_STYLES[arg0]='fg=2'
ZSH_HIGHLIGHT_STYLES[precommand]='fg=2,underline'
ZSH_HIGHLIGHT_STYLES[reserved-word]='fg=3'
ZSH_HIGHLIGHT_STYLES[path]='underline'
ZSH_HIGHLIGHT_STYLES[globbing]='fg=4'
ZSH_HIGHLIGHT_STYLES[single-quoted-argument]='fg=3'
ZSH_HIGHLIGHT_STYLES[double-quoted-argument]='fg=3'
ZSH_HIGHLIGHT_STYLES[dollar-double-quoted-argument]='fg=6'
