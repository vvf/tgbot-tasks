#!/bin/bash
PROJECT_PATH=$(dirname $(readlink -f $(dirname $0)))
echo PROJECT_PATH=$PROJECT_PATH
cd $PROJECT_PATH
. .venv/bin/activate
. .env
python -m taskbot.main