#!/usr/bin/env bash
#rm -r ./dist
#python setup.py sdist
#twine upload dist/*
poetry build
poetry publish --username='aitirga' --password='(39721ekaina12)'