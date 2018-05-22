#!/bin/bash
pass="$1";ask='/tmp/p'; shift;
rm -f "$ask"; echo 'read d; echo "$d"' > "$ask"; chmod 700 "$ask"; export SSH_ASKPASS="$ask"; export DISPLAY=:0
echo "$pass" | setsid ssh $@ &
