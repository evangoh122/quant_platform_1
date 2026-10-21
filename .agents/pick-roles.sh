#!/usr/bin/env bash
# Print "<coder> <validator>" for the given UTC hour (default: now).
#   MiMo peak:     00:00-16:00 UTC
#   DeepSeek peak: 01:00-04:00 and 06:00-10:00 UTC
# Both peak -> MiMo codes. Both off-peak -> DeepSeek codes. MiMo peak + DeepSeek
# off-peak -> DeepSeek codes. So: MiMo codes only while DeepSeek is in peak.
# The other model validates.
# Override: QP1_CODER=mimo|deepseek (the owner can force a coder).
H=$((10#${1:-$(date -u +%H)}))
mimo_peak=0;  [ "$H" -ge 0 ] && [ "$H" -lt 16 ] && mimo_peak=1
ds_peak=0
{ [ "$H" -ge 1 ] && [ "$H" -lt 4 ]; } || { [ "$H" -ge 6 ] && [ "$H" -lt 10 ]; } && ds_peak=1
CODER=deepseek
[ "$ds_peak" = 1 ] && CODER=mimo
CODER="${QP1_CODER:-$CODER}"
if [ "$CODER" = deepseek ]; then echo "dsbuild mimoval"; else echo "mimo deepseek"; fi
