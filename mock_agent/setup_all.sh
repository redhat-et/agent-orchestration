#!/bin/bash

for file in ./data/*.json; do
    filename=$(basename "$file" .json)
    KB_FILE="$file" ./deploy.sh "$filename"
done