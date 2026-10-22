#!/usr/bin/env bash
# Print "<coder> <validator>" for the given UTC hour (default: now).
#   MiMo peak:     00:00-16:00 UTC
#   DeepSeek peak: 01:00-04:00 and 06:00-10:00 UTC
# Both peak -> MiMo codes. Both off-peak -> DeepSeek codes. MiMo peak + DeepSeek
# off-peak -> DeepSeek codes. So: MiMo codes only while DeepSeek is in peak.
# The other model validates.
# Override: QP1_CODER=mimo|deepseek (the owner can force a coder).
# The hour must be an integer 0-23; anything else is a usage error (exit 2).
if [ "$#" -ge 1 ]; then RAW=$1; else RAW=$(date -u +%H); fi
if ! [[ $RAW =~ ^[0-9]{1,2}$ ]]; then
  printf 'pick-roles.sh: UTC hour must be an integer 0-23 (got: %s)\n' "${RAW:-<empty>}" >&2
  exit 2
fi
H=$((10#$RAW))
if [ "$H" -gt 23 ]; then
  printf 'pick-roles.sh: UTC hour must be an integer 0-23 (got: %s)\n' "$RAW" >&2
  exit 2
fi
ds_peak=0
{ [ "$H" -ge 1 ] && [ "$H" -lt 4 ]; } || { [ "$H" -ge 6 ] && [ "$H" -lt 10 ]; } && ds_peak=1
CODER=deepseek
[ "$ds_peak" = 1 ] && CODER=mimo
CODER="${QP1_CODER:-$CODER}"
if [ "$CODER" = deepseek ]; then echo "dsbuild mimoval"; else echo "mimo deepseek"; fi
