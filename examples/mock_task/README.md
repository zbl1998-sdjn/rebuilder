# Reverse Line Tool

A command-line utility that reverses the order of lines from input.

## Usage

```bash
# Read from stdin
echo -e "a\nb\nc" | ./program

# Read from file
./program input.txt

# Remove duplicates before reversing
./program --unique input.txt
./program -u input.txt
```

## Features

- Reads from stdin or a file
- Outputs lines in reverse order
- Optional `--unique` / `-u` flag to remove duplicate lines before reversing
- Preserves line content (does not reverse characters within lines)

## Exit Codes

- `0` - Success
- `1` - Input file not found
- `2` - Empty input

## Example

Input:
```
hello
world
hello
```

Command:
```bash
./program --unique input.txt
```

Output:
```
world
hello
```
