#!/bin/bash

for file in ./data/*.json; do
    filename=$(basename "$file" .json)
    ./teardown.sh "$filename"
done