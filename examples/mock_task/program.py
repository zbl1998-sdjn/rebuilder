#!/usr/bin/env python3
"""
Mock ProgramBench Task: Reverse Line Tool
A simple CLI tool that reads lines from stdin or a file and outputs them in reverse order.
Usage:
    python program.py < input.txt
    python program.py input.txt
    python program.py --unique input.txt   # Remove duplicate lines before reversing
Exit codes:
    0 - Success
    1 - File not found
    2 - Empty input
"""

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Reverse lines of input")
    parser.add_argument("input_file", nargs="?", help="Input file (default: stdin)")
    parser.add_argument("--unique", "-u", action="store_true", help="Remove duplicate lines")
    args = parser.parse_args()
    
    try:
        if args.input_file:
            with open(args.input_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = sys.stdin.readlines()
    except FileNotFoundError:
        print(f"Error: File not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    
    if not lines:
        print("Error: Empty input", file=sys.stderr)
        sys.exit(2)
    
    # Strip newlines, process, then re-add
    lines = [line.rstrip("\n") for line in lines]
    
    if args.unique:
        seen = set()
        unique_lines = []
        for line in lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)
        lines = unique_lines
    
    # Reverse order
    lines.reverse()
    
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
