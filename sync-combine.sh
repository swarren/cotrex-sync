#!/bin/bash

# Copyright 2026 Stephen Warren <swarren@wwwdotorg.org>
# SPDX-License-Identifier: MIT

cd "$(dirname -- "$0")"
./cotrex.py sync data/
./gen-combined.sh
