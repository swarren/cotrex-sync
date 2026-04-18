#!/bin/bash

# Copyright 2026 Stephen Warren <swarren@wwwdotorg.org>
# SPDX-License-Identifier: MIT

cd "$(dirname -- "$0")"
cd data/
combined_regex='combined.*.gpx'
gpsbabel -i gpx $(
    for f in *.gpx; do
        if [[ "$f" =~ ${combined_regex} ]]; then
            continue
        fi
        echo "-f $f"
    done
) -o gpx -F combined.gpx
