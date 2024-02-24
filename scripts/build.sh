#!/bin/bash
# -*- coding: utf-8 -*-
# Programmed by CoolCat467
# Build and upload new release.

set -ex -o pipefail

python3 -m pip install --upgrade pip build twine --break-system-packages

if [ -e dist/ ]; then
    rm -rf dist/
fi
python3 -m build

python3 -m twine upload dist/*
