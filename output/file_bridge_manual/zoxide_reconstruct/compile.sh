#!/bin/sh
set -eu
cat > executable <<'EOF'
#!/bin/sh
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$DIR/main.py" "$@"
EOF
chmod +x executable
