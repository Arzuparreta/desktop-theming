#!/usr/bin/env sh

# Terminate already running bar instances
killall -q polybar

# Wait until the processes have been shut down
while pgrep -u $UID -x polybar >/dev/null; do sleep 2; done

# Pywal: load colors into xrdb so Polybar ${xrdb:...} matches your theme (optional if file exists)
for _wal_xrdb in "${HOME}/.cache/wal/colors.Xresources" "${HOME}/.config/wal/colors.Xresources"; do
  if [ -f "$_wal_xrdb" ]; then
    xrdb -merge "$_wal_xrdb" 2>/dev/null && break
  fi
done

# for multimonitor
if type "xrandr"; then
  for m in $(xrandr --query | grep " connected" | cut -d" " -f1); do
    MONITOR=$m polybar --reload example &
    disown
  done
else
  polybar --reload example &
  disown
fi
