#!/bin/bash

# Read current in microwatts (uW)
# Some kernels use power_now, others use voltage_now * current_now
get_power() {
  local bat=$1
  if [ -f "/sys/class/power_supply/$bat/power_now" ]; then
    cat "/sys/class/power_supply/$bat/power_now"
  else
    # Fallback: Power = (Voltage * Current) / 10^12 to get Watts
    local voltage=$(cat "/sys/class/power_supply/$bat/voltage_now" 2>/dev/null || echo 0)
    local current=$(cat "/sys/class/power_supply/$bat/current_now" 2>/dev/null || echo 0)
    echo $((voltage * current / 1000000))
  fi
}

P0=$(get_power "BAT0")
P1=$(get_power "BAT1")

# Sum and convert microwatts to Watts with two decimal places
TOTAL_UW=$((P0 + P1))
TOTAL_W=$(echo "scale=2; $TOTAL_UW / 1000000" | bc)

# Determine status symbol (charging if power is being added)
STAT0=$(cat /sys/class/power_supply/BAT0/status)
STAT1=$(cat /sys/class/power_supply/BAT1/status)

if [[ "$STAT0" == "Charging" || "$STAT1" == "Charging" ]]; then
  echo "+${TOTAL_W}W"
else
  echo "-${TOTAL_W}W"
fi
