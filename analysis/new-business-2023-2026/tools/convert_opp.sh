#!/bin/bash
# usage: convert_opp.sh <saved_json_file> <out_tsv>   (appends rows; prints record count)
S=/tmp/claude-0/-home-user-test/4450fde6-d7f1-5400-906d-a37991314de6/scratchpad
jq -r -f $S/tools/opp_to_tsv.jq "$1" >> "$2"
jq '.records|length, .totalSize, .done' "$1" | paste -sd' '
