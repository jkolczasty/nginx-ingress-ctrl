#!/bin/bash

if [ -n "$TIMEZONE" -a -f "/usr/share/zoneinfo/$TIMEZONE" ] ; then
  ln -sf "/usr/share/zoneinfo/$TIMEZONE" /etc/localtime
fi

exec python3 -u /ingress/ingressd.py
