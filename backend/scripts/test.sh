#!/usr/bin/env bash

set -e
set -x

pytest tests/ --cov --cov-context=test --cov-report=
coverage report
coverage html --title "${@-coverage}"
