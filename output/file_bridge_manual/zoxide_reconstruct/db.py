"""Database operations and scoring for zoxide."""

import fnmatch
import math
import os
import platform
import sys


def get_data_dir():
    data_dir = os.environ.get("_ZO_DATA_DIR")
    if data_dir:
        if not os.path.isabs(data_dir):
            sys.stderr.write("zoxide: _ZO_DATA_DIR must be an absolute path\n")
            sys.exit(1)
        return data_dir
    system = platform.system()
    if system == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "org.ajeetdsouza.zoxide")
    elif system == "Windows":
        base = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
        return os.path.join(base, "zoxide")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
        return os.path.join(base, "zoxide")


def get_db_path():
    return os.path.join(get_data_dir(), "db.zo")


def load_db():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []
    try:
        data = []
        with open(db_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.rsplit("\t", 1)
                    if len(parts) == 2:
                        try:
                            data.append({"path": parts[0], "score": float(parts[1])})
                        except ValueError:
                            continue
        return data
    except Exception:
        return []


def save_db(data):
    db_path = get_db_path()
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with open(db_path, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(f"{entry['path']}\t{entry['score']}\n")


def age_db(data):
    maxage = int(os.environ.get("_ZO_MAXAGE", "10000"))
    total_score = sum(entry["score"] for entry in data)
    if total_score > maxage and data:
        factor = maxage / total_score
        for entry in data:
            entry["score"] *= factor
        data = [e for e in data if e["score"] >= 0.0001]
    return data


def match_path(path, keyword, is_last=False):
    path_lower = path.lower()
    key_lower = keyword.lower()
    if is_last and keyword.endswith("/"):
        norm_path = os.path.normpath(path).lower()
        norm_key = os.path.normpath(keyword.rstrip("/")).lower()
        return (norm_key + os.sep) in (norm_path + os.sep)
    return key_lower in path_lower


def compute_rank(score, path, keywords):
    path_lower = path.lower()
    total = 0.0
    for kw in keywords:
        kw_lower = kw.lower()
        idx = path_lower.find(kw_lower)
        if idx < 0:
            return -1
        total += 1.0 / (idx + 1)
    return score * total


def is_excluded(path):
    exclude_dirs = os.environ.get("_ZO_EXCLUDE_DIRS", "")
    system = platform.system()
    sep = ";" if system == "Windows" else ":"
    patterns = [p for p in exclude_dirs.split(sep) if p]
    home = os.path.expanduser("~")
    if not patterns:
        patterns = [home]
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if os.path.isabs(pattern):
            if path.startswith(pattern + os.sep) or path == pattern:
                return True
    return False