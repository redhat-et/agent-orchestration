#!/bin/bash

for config in ./configs/*.yaml; do
    filename=$(basename "$config" .yaml)
    ./deploy.sh "$filename" "$config"
done