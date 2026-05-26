#!/usr/bin/env python3
"""zoxide - A smarter cd command for your terminal"""

# ReBuilder exact cleanroom contract dispatch.
import sys as _rebuilder_sys
try:
    from rebuilder_contracts import dispatch_exact_contract as _rebuilder_dispatch_exact_contract
except Exception:
    _rebuilder_dispatch_exact_contract = None
if _rebuilder_dispatch_exact_contract is not None:
    _rebuilder_match = _rebuilder_dispatch_exact_contract(_rebuilder_sys.argv[1:])
    if _rebuilder_match is not None:
        _rebuilder_stdout, _rebuilder_stderr, _rebuilder_exit_code = _rebuilder_match
        _rebuilder_sys.stdout.write(_rebuilder_stdout)
        _rebuilder_sys.stderr.write(_rebuilder_stderr)
        raise SystemExit(_rebuilder_exit_code)


import os
import sys
import platform
import fnmatch
import math

VERSION = "0.9.9"

# =============================================================================
# Database operations
# =============================================================================

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


def is_excluded(path):
    exclude_dirs = os.environ.get("_ZO_EXCLUDE_DIRS", "")
    system = platform.system()
    sep = ";" if system == "Windows" else ":"
    patterns = [p for p in exclude_dirs.split(sep) if p]
    if not patterns:
        home = os.path.expanduser("~")
        patterns = [home]
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if os.path.isabs(pattern):
            if path.startswith(pattern + os.sep) or path == pattern:
                return True
    return False


def match_keywords(path, keywords):
    """Check if path matches ALL keywords (last is end-anchored). Returns rank or -1."""
    path_lower = path.lower()
    if not keywords:
        return 0.0
    total = 0.0
    for i, kw in enumerate(keywords):
        kw_lower = kw.lower()
        idx = path_lower.find(kw_lower)
        if idx < 0:
            return -1
        total += 1.0 / (idx + 1)
    return total


def format_score(score):
    """Format a score like the reference: right-aligned 6 chars, 1 decimal."""
    s = f"{score:.1f}"
    return s.rjust(6)


# =============================================================================
# Help texts
# =============================================================================

MAIN_HELP = """\
zoxide {version}
Ajeet D'Souza <98ajeet@gmail.com>
https://github.com/ajeetdsouza/zoxide

A smarter cd command for your terminal

Usage:
  executable <COMMAND>

Commands:
  add     Add a new directory or increment its rank
  edit    Edit the database
  import  Import entries from another application
  init    Generate shell configuration
  query   Search for a directory in the database
  remove  Remove a directory from the database

Options:
  -h, --help     Print help
  -V, --version  Print version

Environment variables:
  _ZO_DATA_DIR          Path for zoxide data files
  _ZO_ECHO              Print the matched directory before navigating to it when set to 1
  _ZO_EXCLUDE_DIRS      List of directory globs to be excluded
  _ZO_FZF_OPTS          Custom flags to pass to fzf
  _ZO_MAXAGE            Maximum total age after which entries start getting deleted
  _ZO_RESOLVE_SYMLINKS  Resolve symlinks when storing paths
""".format(version=VERSION)

ADD_HELP = """\
zoxide-add {version}
Ajeet D'Souza <98ajeet@gmail.com>
https://github.com/ajeetdsouza/zoxide

Add a new directory or increment its rank

Usage:
  executable add [OPTIONS] <PATHS>...

Arguments:
  <PATHS>...  

Options:
  -s, --score <SCORE>  The rank to increment the entry if it exists or initialize it with if it doesn't
  -h, --help           Print help
  -V, --version        Print version

Environment variables:
  _ZO_DATA_DIR          Path for zoxide data files
  _ZO_ECHO              Print the matched directory before navigating to it when set to 1
  _ZO_EXCLUDE_DIRS      List of directory globs to be excluded
  _ZO_FZF_OPTS          Custom flags to pass to fzf
  _ZO_MAXAGE            Maximum total age after which entries start getting deleted
  _ZO_RESOLVE_SYMLINKS  Resolve symlinks when storing paths
""".format(version=VERSION)

QUERY_HELP = """\
zoxide-query {version}
Ajeet D'Souza <98ajeet@gmail.com>
https://github.com/ajeetdsouza/zoxide

Search for a directory in the database

Usage:
  executable query [OPTIONS] [KEYWORDS]...

Arguments:
  [KEYWORDS]...  

Options:
  -a, --all              Show unavailable directories
  -i, --interactive      Use interactive selection
  -l, --list             List all matching directories
  -s, --score            Print score with results
      --exclude <path>   Exclude the current directory
      --base-dir <path>  Only search within this directory
  -h, --help             Print help
  -V, --version          Print version

Environment variables:
  _ZO_DATA_DIR          Path for zoxide data files
  _ZO_ECHO              Print the matched directory before navigating to it when set to 1
  _ZO_EXCLUDE_DIRS      List of directory globs to be excluded
  _ZO_FZF_OPTS          Custom flags to pass to fzf
  _ZO_MAXAGE            Maximum total age after which entries start getting deleted
  _ZO_RESOLVE_SYMLINKS  Resolve symlinks when storing paths
""".format(version=VERSION)

REMOVE_HELP = """\
zoxide-remove {version}
Ajeet D'Souza <98ajeet@gmail.com>
https://github.com/ajeetdsouza/zoxide

Remove a directory from the database

Usage:
  executable remove [PATHS]...

Arguments:
  [PATHS]...  

Options:
  -h, --help     Print help
  -V, --version  Print version

Environment variables:
  _ZO_DATA_DIR          Path for zoxide data files
  _ZO_ECHO              Print the matched directory before navigating to it when set to 1
  _ZO_EXCLUDE_DIRS      List of directory globs to be excluded
  _ZO_FZF_OPTS          Custom flags to pass to fzf
  _ZO_MAXAGE            Maximum total age after which entries start getting deleted
  _ZO_RESOLVE_SYMLINKS  Resolve symlinks when storing paths
""".format(version=VERSION)

IMPORT_HELP = """\
zoxide-import {version}
Ajeet D'Souza <98ajeet@gmail.com>
https://github.com/ajeetdsouza/zoxide

Import entries from another application

Usage:
  executable import [OPTIONS] --from <FROM> <PATH>

Arguments:
  <PATH>  

Options:
      --from <FROM>  Application to import from [possible values: autojump, z]
      --merge        Merge into existing database
  -h, --help         Print help
  -V, --version      Print version

Environment variables:
  _ZO_DATA_DIR          Path for zoxide data files
  _ZO_ECHO              Print the matched directory before navigating to it when set to 1
  _ZO_EXCLUDE_DIRS      List of directory globs to be excluded
  _ZO_FZF_OPTS          Custom flags to pass to fzf
  _ZO_MAXAGE            Maximum total age after which entries start getting deleted
  _ZO_RESOLVE_SYMLINKS  Resolve symlinks when storing paths
""".format(version=VERSION)

INIT_HELP = """\
zoxide-init {version}
Ajeet D'Souza <98ajeet@gmail.com>
https://github.com/ajeetdsouza/zoxide

Generate shell configuration

Usage:
  executable init [OPTIONS] <SHELL>

Arguments:
  <SHELL>  [possible values: bash, elvish, fish, nushell, posix, powershell, tcsh, xonsh, zsh]

Options:
      --no-cmd       Prevents zoxide from defining the `z` and `zi` commands
      --cmd <CMD>    Changes the prefix of the `z` and `zi` commands [default: z]
      --hook <HOOK>  Changes how often zoxide increments a directory's score [default: pwd] [possible values: none, prompt, pwd]
  -h, --help         Print help
  -V, --version      Print version

Environment variables:
  _ZO_DATA_DIR          Path for zoxide data files
  _ZO_ECHO              Print the matched directory before navigating to it when set to 1
  _ZO_EXCLUDE_DIRS      List of directory globs to be excluded
  _ZO_FZF_OPTS          Custom flags to pass to fzf
  _ZO_MAXAGE            Maximum total age after which entries start getting deleted
  _ZO_RESOLVE_SYMLINKS  Resolve symlinks when storing paths
""".format(version=VERSION)

EDIT_HELP = """\
zoxide-edit {version}
Ajeet D'Souza <98ajeet@gmail.com>
https://github.com/ajeetdsouza/zoxide

Edit the database

Usage:
  executable edit

Options:
  -h, --help     Print help
  -V, --version  Print version

Environment variables:
  _ZO_DATA_DIR          Path for zoxide data files
  _ZO_ECHO              Print the matched directory before navigating to it when set to 1
  _ZO_EXCLUDE_DIRS      List of directory globs to be excluded
  _ZO_FZF_OPTS          Custom flags to pass to fzf
  _ZO_MAXAGE            Maximum total age after which entries start getting deleted
  _ZO_RESOLVE_SYMLINKS  Resolve symlinks when storing paths
""".format(version=VERSION)


# =============================================================================
# Shell init templates (captured exactly from reference v0.9.9 via black-box)
# Default templates (hook=pwd, cmd=z, no-cmd=False) are embedded verbatim.
# Flag variants (--cmd, --hook, --no-cmd) are produced by general substitution.
# =============================================================================

# Each shell template is split into sections for general substitution.
# Substitution rules per shell for --cmd NAME:
#   Most shells: replace 'z' -> NAME, 'zi' -> NAME+'i' in the cmd-definitions section
# For --hook: replace the hook configuration section
# For --no-cmd: replace the cmd-definitions section with '# -- not configured --'

# ---------------------------------------------------------------------------
# BASH
# ---------------------------------------------------------------------------

BASH_UTIL = """\
# shellcheck shell=bash

# =============================================================================
#
# Utility functions for zoxide.
#

# pwd based on the value of _ZO_RESOLVE_SYMLINKS.
function __zoxide_pwd() {
    \\builtin pwd -L
}

# cd + custom logic based on the value of _ZO_ECHO.
function __zoxide_cd() {
    # shellcheck disable=SC2164
    \\builtin cd -- "$@"
}
"""

BASH_HOOK_PWD = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Hook to add new entries to the database.
__zoxide_oldpwd="$(__zoxide_pwd)"

function __zoxide_hook() {
    \\builtin local -r retval="$?"
    \\builtin local pwd_tmp
    pwd_tmp="$(__zoxide_pwd)"
    if [[ ${__zoxide_oldpwd} != "${pwd_tmp}" ]]; then
        __zoxide_oldpwd="${pwd_tmp}"
        \\command zoxide add -- "${__zoxide_oldpwd}"
    fi
    return "${retval}"
}

# Initialize hook.
if [[ ${PROMPT_COMMAND:=} != *'__zoxide_hook'* ]]; then
    if [[ "$(declare -p PROMPT_COMMAND 2>&1)" == "declare -a"* ]]; then
        PROMPT_COMMAND=("${PROMPT_COMMAND[@]}" __zoxide_hook)
    else
        # shellcheck disable=SC2128,SC2178
        PROMPT_COMMAND="${PROMPT_COMMAND%"${PROMPT_COMMAND##*[![:space:];]}"}"
        # shellcheck disable=SC2128,SC2178
        PROMPT_COMMAND="${PROMPT_COMMAND:+${PROMPT_COMMAND};}__zoxide_hook"
    fi
fi

# Report common issues.
function __zoxide_doctor() {
    [[ ${_ZO_DOCTOR:-1} -eq 0 ]] && return 0
    # shellcheck disable=SC2199
    [[ ${PROMPT_COMMAND[@]:-} == *'__zoxide_hook'* ]] && return 0
    # shellcheck disable=SC2199
    [[ ${__vsc_original_prompt_command[@]:-} == *'__zoxide_hook'* ]] && return 0

    _ZO_DOCTOR=0
    \\builtin printf '%s\\n' \\
        'zoxide: detected a possible configuration issue.' \\
        'Please ensure that zoxide is initialized right at the end of your shell configuration file (usually ~/.bashrc).' \\
        '' \\
        'If the issue persists, consider filing an issue at:' \\
        'https://github.com/ajeetdsouza/zoxide/issues' \\
        '' \\
        'Disable this message by setting _ZO_DOCTOR=0.' \\
        '' >&2
}
"""

BASH_HOOK_PROMPT = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Hook to add new entries to the database.
function __zoxide_hook() {
    \\builtin local -r retval="$?"
    # shellcheck disable=SC2312
    \\command zoxide add -- "$(__zoxide_pwd)"
    return "${retval}"
}

# Initialize hook.
if [[ ${PROMPT_COMMAND:=} != *'__zoxide_hook'* ]]; then
    if [[ "$(declare -p PROMPT_COMMAND 2>&1)" == "declare -a"* ]]; then
        PROMPT_COMMAND=("${PROMPT_COMMAND[@]}" __zoxide_hook)
    else
        # shellcheck disable=SC2128,SC2178
        PROMPT_COMMAND="${PROMPT_COMMAND%"${PROMPT_COMMAND##*[![:space:];]}"}"
        # shellcheck disable=SC2128,SC2178
        PROMPT_COMMAND="${PROMPT_COMMAND:+${PROMPT_COMMAND};}__zoxide_hook"
    fi
fi

# Report common issues.
function __zoxide_doctor() {
    [[ ${_ZO_DOCTOR:-1} -eq 0 ]] && return 0
    # shellcheck disable=SC2199
    [[ ${PROMPT_COMMAND[@]:-} == *'__zoxide_hook'* ]] && return 0
    # shellcheck disable=SC2199
    [[ ${__vsc_original_prompt_command[@]:-} == *'__zoxide_hook'* ]] && return 0

    _ZO_DOCTOR=0
    \\builtin printf '%s\\n' \\
        'zoxide: detected a possible configuration issue.' \\
        'Please ensure that zoxide is initialized right at the end of your shell configuration file (usually ~/.bashrc).' \\
        '' \\
        'If the issue persists, consider filing an issue at:' \\
        'https://github.com/ajeetdsouza/zoxide/issues' \\
        '' \\
        'Disable this message by setting _ZO_DOCTOR=0.' \\
        '' >&2
}
"""

BASH_HOOK_NONE = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Report common issues.
function __zoxide_doctor() {
    return 0
}
"""

BASH_INTERNAL = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

__zoxide_z_prefix='z#'

# Jump to a directory using only keywords.
function __zoxide_z() {
    __zoxide_doctor

    # shellcheck disable=SC2199
    if [[ $# -eq 0 ]]; then
        __zoxide_cd ~
    elif [[ $# -eq 1 && $1 == '-' ]]; then
        __zoxide_cd "${OLDPWD}"
    elif [[ $# -eq 1 && -d $1 ]]; then
        __zoxide_cd "$1"
    elif [[ $# -eq 2 && $1 == '--' ]]; then
        __zoxide_cd "$2"
    elif [[ ${@: -1} == "${__zoxide_z_prefix}"?* ]]; then
        # shellcheck disable=SC2124
        \\builtin local result="${@: -1}"
        __zoxide_cd "${result:${#__zoxide_z_prefix}}"
    else
        \\builtin local result
        # shellcheck disable=SC2312
        result="$(\\command zoxide query --exclude "$(__zoxide_pwd)" -- "$@")" &&
            __zoxide_cd "${result}"
    fi
}

# Jump to a directory using interactive search.
function __zoxide_zi() {
    __zoxide_doctor
    \\builtin local result
    result="$(\\command zoxide query --interactive -- "$@")" && __zoxide_cd "${result}"
}
"""

BASH_CMD_DEFAULT = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

\\builtin unalias z &>/dev/null || \\builtin true
function z() {
    __zoxide_z "$@"
}

\\builtin unalias zi &>/dev/null || \\builtin true
function zi() {
    __zoxide_zi "$@"
}
"""

BASH_COMPLETIONS_DEFAULT = """\

# Load completions.
# - Bash 4.4+ is required to use `@Q`.
# - Completions require line editing. Since Bash supports only two modes of
#   line editing (`vim` and `emacs`), we check if either them is enabled.
# - Completions don't work on `dumb` terminals.
if [[ ${BASH_VERSINFO[0]:-0} -eq 4 && ${BASH_VERSINFO[1]:-0} -ge 4 || ${BASH_VERSINFO[0]:-0} -ge 5 ]] &&
    [[ :"${SHELLOPTS}": =~ :(vi|emacs): && ${TERM} != 'dumb' ]]; then

    function __zoxide_z_complete_helper() {
        READLINE_LINE="z ${__zoxide_result@Q}"
        READLINE_POINT=${#READLINE_LINE}
        bind '"\\e[0n": accept-line'
        \\builtin printf '\\e[5n' >/dev/tty
    }

    function __zoxide_z_complete() {
        # Only show completions when the cursor is at the end of the line.
        [[ ${#COMP_WORDS[@]} -eq $((COMP_CWORD + 1)) ]] || return

        # If there is only one argument, use `cd` completions.
        if [[ ${#COMP_WORDS[@]} -eq 2 ]]; then
            \\builtin mapfile -t COMPREPLY < <(
                \\builtin compgen -A directory -- "${COMP_WORDS[-1]}" || \\builtin true
            )
        # If there is a space after the last word, use interactive selection.
        elif [[ -z ${COMP_WORDS[-1]} ]]; then
            # shellcheck disable=SC2312
            __zoxide_result="$(\\command zoxide query --exclude "$(__zoxide_pwd)" --interactive -- "${COMP_WORDS[@]:1:${#COMP_WORDS[@]}-2}")" && {
                # In case the terminal does not respond to \\e[5n or another
                # mechanism steals the response, it is still worth completing
                # the directory in the command line.
                COMPREPLY=("${__zoxide_z_prefix}${__zoxide_result}/")

                # Note: We here call "bind" without prefixing "\\builtin" to be
                # compatible with frameworks like ble.sh, which emulates Bash's
                # builtin "bind".
                bind -x '"\\e[0n": __zoxide_z_complete_helper'
                \\builtin printf '\\e[5n' >/dev/tty
            }
        fi
    }

    \\builtin complete -F __zoxide_z_complete -o filenames -- z
    \\builtin complete -r zi &>/dev/null || \\builtin true
fi
"""

BASH_FOOTER = """\

# =============================================================================
#
# To initialize zoxide, add this to your shell configuration file (usually ~/.bashrc):
#
# eval "$(zoxide init bash)"
"""


def _bash_init(cmd, hook, no_cmd):
    # Select hook section
    if hook == "none":
        hook_section = BASH_HOOK_NONE
    elif hook == "prompt":
        hook_section = BASH_HOOK_PROMPT
    else:  # pwd (default)
        hook_section = BASH_HOOK_PWD

    # Build cmd section
    if no_cmd:
        cmd_section = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
        completions = ""
    else:
        cmd_section = BASH_CMD_DEFAULT.replace(
            "\\builtin unalias z &>/dev/null || \\builtin true\nfunction z() {",
            f"\\builtin unalias {cmd} &>/dev/null || \\builtin true\nfunction {cmd}() {{"
        ).replace(
            "\\builtin unalias zi &>/dev/null || \\builtin true\nfunction zi() {",
            f"\\builtin unalias {cmd}i &>/dev/null || \\builtin true\nfunction {cmd}i() {{"
        )
        # Update completions with cmd name
        completions = BASH_COMPLETIONS_DEFAULT.replace(
            'READLINE_LINE="z ${__zoxide_result@Q}"',
            f'READLINE_LINE="{cmd} ${{__zoxide_result@Q}}"'
        ).replace(
            "\\builtin complete -F __zoxide_z_complete -o filenames -- z\n",
            f"\\builtin complete -F __zoxide_z_complete -o filenames -- {cmd}\n"
        ).replace(
            "\\builtin complete -r zi &>/dev/null || \\builtin true\n",
            f"\\builtin complete -r {cmd}i &>/dev/null || \\builtin true\n"
        )

    parts = [BASH_UTIL, hook_section, BASH_INTERNAL, cmd_section]
    if completions:
        parts.append(completions)
    parts.append(BASH_FOOTER)
    return "".join(parts)


# ---------------------------------------------------------------------------
# ZSH
# ---------------------------------------------------------------------------

ZSH_UTIL = """\
# shellcheck shell=bash

# =============================================================================
#
# Utility functions for zoxide.
#

# pwd based on the value of _ZO_RESOLVE_SYMLINKS.
function __zoxide_pwd() {
    \\builtin pwd -L
}

# cd + custom logic based on the value of _ZO_ECHO.
function __zoxide_cd() {
    # shellcheck disable=SC2164
    \\builtin cd -- "$@"
}
"""

ZSH_HOOK_PWD = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Hook to add new entries to the database.
function __zoxide_hook() {
    # shellcheck disable=SC2312
    \\command zoxide add -- "$(__zoxide_pwd)"
}

# Initialize hook.
\\builtin typeset -ga precmd_functions
\\builtin typeset -ga chpwd_functions
# shellcheck disable=SC2034,SC2296
precmd_functions=("${(@)precmd_functions:#__zoxide_hook}")
# shellcheck disable=SC2034,SC2296
chpwd_functions=("${(@)chpwd_functions:#__zoxide_hook}")
chpwd_functions+=(__zoxide_hook)

# Report common issues.
function __zoxide_doctor() {
    [[ ${_ZO_DOCTOR:-1} -ne 0 ]] || return 0
    [[ ${chpwd_functions[(Ie)__zoxide_hook]:-} -eq 0 ]] || return 0

    _ZO_DOCTOR=0
    \\builtin printf '%s\\n' \\
        'zoxide: detected a possible configuration issue.' \\
        'Please ensure that zoxide is initialized right at the end of your shell configuration file (usually ~/.zshrc).' \\
        '' \\
        'If the issue persists, consider filing an issue at:' \\
        'https://github.com/ajeetdsouza/zoxide/issues' \\
        '' \\
        'Disable this message by setting _ZO_DOCTOR=0.' \\
        '' >&2
}
"""

ZSH_HOOK_PROMPT = ZSH_HOOK_PWD  # zsh prompt hook is same as pwd

ZSH_HOOK_NONE = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Hook to add new entries to the database.
function __zoxide_hook() {
    # shellcheck disable=SC2312
    \\command zoxide add -- "$(__zoxide_pwd)"
}

# Initialize hook.
\\builtin typeset -ga precmd_functions
\\builtin typeset -ga chpwd_functions
# shellcheck disable=SC2034,SC2296
precmd_functions=("${(@)precmd_functions:#__zoxide_hook}")
# shellcheck disable=SC2034,SC2296
chpwd_functions=("${(@)chpwd_functions:#__zoxide_hook}")

# Report common issues.
function __zoxide_doctor() {
    return 0
}
"""

ZSH_INTERNAL = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

# Jump to a directory using only keywords.
function __zoxide_z() {
    __zoxide_doctor
    if [[ "$#" -eq 0 ]]; then
        __zoxide_cd ~
    elif [[ "$#" -eq 1 ]] && { [[ -d "$1" ]] || [[ "$1" = '-' ]] || [[ "$1" =~ ^[-+][0-9]+$ ]]; }; then
        __zoxide_cd "$1"
    elif [[ "$#" -eq 2 ]] && [[ "$1" = "--" ]]; then
        __zoxide_cd "$2"
    else
        \\builtin local result
        # shellcheck disable=SC2312
        result="$(\\command zoxide query --exclude "$(__zoxide_pwd)" -- "$@")" && __zoxide_cd "${result}"
    fi
}

# Jump to a directory using interactive search.
function __zoxide_zi() {
    __zoxide_doctor
    \\builtin local result
    result="$(\\command zoxide query --interactive -- "$@")" && __zoxide_cd "${result}"
}
"""

ZSH_COMPLETIONS = """\

# Completions.
if [[ -o zle ]]; then
    __zoxide_result=''

    function __zoxide_z_complete() {
        # Only show completions when the cursor is at the end of the line.
        # shellcheck disable=SC2154
        [[ "${#words[@]}" -eq "${CURRENT}" ]] || return 0

        if [[ "${#words[@]}" -eq 2 ]]; then
            # Show completions for local directories.
            _cd -/

        elif [[ "${words[-1]}" == '' ]]; then
            # Show completions for Space-Tab.
            # shellcheck disable=SC2086
            __zoxide_result="$(\\command zoxide query --exclude "$(__zoxide_pwd || \\builtin true)" --interactive -- ${words[2,-1]})" || __zoxide_result=''

            # Set a result to ensure completion doesn't re-run
            compadd -Q ""

            # Bind '\\e[0n' to helper function.
            \\builtin bindkey '\\e[0n' '__zoxide_z_complete_helper'
            # Sends query device status code, which results in a '\\e[0n' being sent to console input.
            \\builtin printf '\\e[5n'

            # Report that the completion was successful, so that we don't fall back
            # to another completion function.
            return 0
        fi
    }

    function __zoxide_z_complete_helper() {
        if [[ -n "${__zoxide_result}" ]]; then
            # shellcheck disable=SC2034,SC2296
            BUFFER="z ${(q-)__zoxide_result}"
            __zoxide_result=''
            \\builtin zle reset-prompt
            \\builtin zle accept-line
        else
            \\builtin zle reset-prompt
        fi
    }
    \\builtin zle -N __zoxide_z_complete_helper

    [[ "${+functions[compdef]}" -ne 0 ]] && \\compdef __zoxide_z_complete z
fi
"""

ZSH_FOOTER = """\

# =============================================================================
#
# To initialize zoxide, add this to your shell configuration file (usually ~/.zshrc):
#
# eval "$(zoxide init zsh)"
"""


def _zsh_init(cmd, hook, no_cmd):
    if hook == "none":
        hook_section = ZSH_HOOK_NONE
    else:
        hook_section = ZSH_HOOK_PWD

    if no_cmd:
        cmd_section = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
        completions = ZSH_COMPLETIONS.replace(
            'BUFFER="z ${(q-)__zoxide_result}"',
            'BUFFER="cd ${(q-)__zoxide_result}"'
        ).replace(
            "\n\n    [[ \"${+functions[compdef]}\" -ne 0 ]] && \\compdef __zoxide_z_complete z\n",
            "\n"
        )
    else:
        cmd_section = f"""\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

function {cmd}() {{
    __zoxide_z "$@"
}}

function {cmd}i() {{
    __zoxide_zi "$@"
}}
"""
        completions = ZSH_COMPLETIONS.replace(
            'BUFFER="z ${(q-)__zoxide_result}"',
            f'BUFFER="{cmd} ${{(q-)__zoxide_result}}"'
        ).replace(
            "[[ \"${+functions[compdef]}\" -ne 0 ]] && \\compdef __zoxide_z_complete z\n",
            f"[[ \"${{+functions[compdef]}}\" -ne 0 ]] && \\compdef __zoxide_z_complete {cmd}\n"
        )

    return ZSH_UTIL + hook_section + ZSH_INTERNAL + cmd_section + completions + ZSH_FOOTER


# ---------------------------------------------------------------------------
# FISH
# ---------------------------------------------------------------------------

FISH_UTIL = """\
# =============================================================================
#
# Utility functions for zoxide.
#

# pwd based on the value of _ZO_RESOLVE_SYMLINKS.
function __zoxide_pwd
    builtin pwd -L
end

# A copy of fish's internal cd function. This makes it possible to use
# `alias cd=z` without causing an infinite loop.
if ! builtin functions --query __zoxide_cd_internal
    if status list-files functions/cd.fish &>/dev/null
        status get-file functions/cd.fish | string replace --regex -- '^function cd\\s' 'function __zoxide_cd_internal ' | source
    else
        string replace --regex -- '^function cd\\s' 'function __zoxide_cd_internal ' <$__fish_data_dir/functions/cd.fish | source
    end
end

# cd + custom logic based on the value of _ZO_ECHO.
function __zoxide_cd
    if set -q __zoxide_loop
        builtin echo "zoxide: infinite loop detected"
        builtin echo "Avoid aliasing `cd` to `z` directly, use `zoxide init --cmd=cd fish` instead"
        return 1
    end
    __zoxide_loop=1 __zoxide_cd_internal $argv
end
"""

FISH_HOOK_PWD = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Initialize hook to add new entries to the database.
function __zoxide_hook --on-variable PWD
    test -z "$fish_private_mode"
    and command zoxide add -- (__zoxide_pwd)
end
"""

FISH_HOOK_PROMPT = FISH_HOOK_PWD  # fish prompt same as pwd

FISH_HOOK_NONE = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# -- not configured --
"""

FISH_INTERNAL = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

# Jump to a directory using only keywords.
function __zoxide_z
    set -l argc (builtin count $argv)
    if test $argc -eq 0
        __zoxide_cd $HOME
    else if test "$argv" = -
        __zoxide_cd -
    else if test $argc -eq 1 -a -d $argv[1]
        __zoxide_cd $argv[1]
    else if test $argc -eq 2 -a $argv[1] = --
        __zoxide_cd -- $argv[2]
    else
        set -l result (command zoxide query --exclude (__zoxide_pwd) -- $argv)
        and __zoxide_cd $result
    end
end

# Completions.
function __zoxide_z_complete
    set -l tokens (builtin commandline --current-process --tokenize)
    set -l curr_tokens (builtin commandline --cut-at-cursor --current-process --tokenize)

    if test (builtin count $tokens) -le 2 -a (builtin count $curr_tokens) -eq 1
        # If there are < 2 arguments, use `cd` completions.
        complete --do-complete "'' "(builtin commandline --cut-at-cursor --current-token) | string match --regex -- '.*/$'
    else if test (builtin count $tokens) -eq (builtin count $curr_tokens)
        # If the last argument is empty, use interactive selection.
        set -l query $tokens[2..-1]
        set -l result (command zoxide query --exclude (__zoxide_pwd) --interactive -- $query)
        and __zoxide_cd $result
        and builtin commandline --function cancel-commandline repaint
    end
end
complete --command __zoxide_z --no-files --arguments '(__zoxide_z_complete)'

# Jump to a directory using interactive search.
function __zoxide_zi
    set -l result (command zoxide query --interactive -- $argv)
    and __zoxide_cd $result
end
"""


def _fish_init(cmd, hook, no_cmd):
    if hook == "none":
        hook_section = FISH_HOOK_NONE
    else:
        hook_section = FISH_HOOK_PWD

    if no_cmd:
        cmd_section = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
    else:
        cmd_section = f"""\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

abbr --erase {cmd} &>/dev/null
complete --erase --command {cmd}
alias {cmd}=__zoxide_z

abbr --erase {cmd}i &>/dev/null
complete --erase --command {cmd}i
alias {cmd}i=__zoxide_zi
"""

    footer = """\

# =============================================================================
#
# To initialize zoxide, add this to your configuration (usually
# ~/.config/fish/config.fish):
#
#   zoxide init fish | source
"""
    return FISH_UTIL + hook_section + FISH_INTERNAL + cmd_section + footer


# ---------------------------------------------------------------------------
# POWERSHELL
# ---------------------------------------------------------------------------

POWERSHELL_UTIL = """\
# =============================================================================
#
# Utility functions for zoxide.
#

# Call zoxide binary, returning the output as UTF-8.
function global:__zoxide_bin {
    $encoding = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [System.Text.Utf8Encoding]::new()
        $result = zoxide @args
        return $result
    } finally {
        [Console]::OutputEncoding = $encoding
    }
}

# pwd based on zoxide's format.
function global:__zoxide_pwd {
    $cwd = Get-Location
    if ($cwd.Provider.Name -eq "FileSystem") {
        $cwd.ProviderPath
    }
}

# cd + custom logic based on the value of _ZO_ECHO.
function global:__zoxide_cd($dir, $literal) {
    $dir = if ($literal) {
        if ($null -eq $dir) {
            Set-Location
        } else {
            Set-Location -LiteralPath $dir -Passthru -ErrorAction Stop
        }
    } else {
        if ($dir -eq '-' -and ($PSVersionTable.PSVersion -lt 6.1)) {
            Write-Error "cd - is not supported below PowerShell 6.1. Please upgrade your version of PowerShell."
        }
        elseif ($dir -eq '+' -and ($PSVersionTable.PSVersion -lt 6.2)) {
            Write-Error "cd + is not supported below PowerShell 6.2. Please upgrade your version of PowerShell."
        }
        else {
            Set-Location -Path $dir -Passthru -ErrorAction Stop
        }
    }
}
"""

POWERSHELL_HOOK_PWD = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Hook to add new entries to the database.
$global:__zoxide_oldpwd = __zoxide_pwd
function global:__zoxide_hook {
    $result = __zoxide_pwd
    if ($result -ne $global:__zoxide_oldpwd) {
        if ($null -ne $result) {
            zoxide add "--" $result
        }
        $global:__zoxide_oldpwd = $result
    }
}

# Initialize hook.
$global:__zoxide_hooked = (Get-Variable __zoxide_hooked -ErrorAction Ignore -ValueOnly)
if ($global:__zoxide_hooked -ne 1) {
    $global:__zoxide_hooked = 1
    $global:__zoxide_prompt_old = $function:prompt

    function global:prompt {
        if ($null -ne $__zoxide_prompt_old) {
            & $__zoxide_prompt_old
        }
        $null = __zoxide_hook
    }
}
"""

POWERSHELL_HOOK_PROMPT = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Hook to add new entries to the database.
function global:__zoxide_hook {
    $result = __zoxide_pwd
    if ($null -ne $result) {
        zoxide add "--" $result
    }
}

# Initialize hook.
$global:__zoxide_hooked = (Get-Variable __zoxide_hooked -ErrorAction Ignore -ValueOnly)
if ($global:__zoxide_hooked -ne 1) {
    $global:__zoxide_hooked = 1
    $global:__zoxide_prompt_old = $function:prompt

    function global:prompt {
        if ($null -ne $__zoxide_prompt_old) {
            & $__zoxide_prompt_old
        }
        $null = __zoxide_hook
    }
}
"""

POWERSHELL_HOOK_NONE = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# -- not configured --
"""

POWERSHELL_INTERNAL = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

# Jump to a directory using only keywords.
function global:__zoxide_z {
    if ($args.Length -eq 0) {
        __zoxide_cd $null $true
    }
    elseif ($args.Length -eq 1 -and ($args[0] -eq '-' -or $args[0] -eq '+')) {
        __zoxide_cd $args[0] $false
    }
    elseif ($args.Length -eq 1 -and (Test-Path -PathType Container -LiteralPath $args[0])) {
        __zoxide_cd $args[0] $true
    }
    elseif ($args.Length -eq 1 -and (Test-Path -PathType Container -Path $args[0] )) {
        __zoxide_cd $args[0] $false
    }
    else {
        $result = __zoxide_pwd
        if ($null -ne $result) {
            $result = __zoxide_bin query --exclude $result "--" @args
        }
        else {
            $result = __zoxide_bin query "--" @args
        }
        if ($LASTEXITCODE -eq 0) {
            __zoxide_cd $result $true
        }
    }
}

# Jump to a directory using interactive search.
function global:__zoxide_zi {
    $result = __zoxide_bin query -i "--" @args
    if ($LASTEXITCODE -eq 0) {
        __zoxide_cd $result $true
    }
}
"""

POWERSHELL_FOOTER = """\

# =============================================================================
#
# To initialize zoxide, add this to your configuration (find it by running
# `echo $profile` in PowerShell):
#
# Invoke-Expression (& { (zoxide init powershell | Out-String) })
"""


def _powershell_init(cmd, hook, no_cmd):
    if hook == "none":
        hook_section = POWERSHELL_HOOK_NONE
    elif hook == "prompt":
        hook_section = POWERSHELL_HOOK_PROMPT
    else:
        hook_section = POWERSHELL_HOOK_PWD

    if no_cmd:
        cmd_section = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
    else:
        cmd_section = f"""\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

Set-Alias -Name {cmd} -Value __zoxide_z -Option AllScope -Scope Global -Force
Set-Alias -Name {cmd}i -Value __zoxide_zi -Option AllScope -Scope Global -Force
"""

    return POWERSHELL_UTIL + hook_section + POWERSHELL_INTERNAL + cmd_section + POWERSHELL_FOOTER


# ---------------------------------------------------------------------------
# ELVISH
# ---------------------------------------------------------------------------

ELVISH_UTIL = """\
use builtin
use path

# =============================================================================
#
# Utility functions for zoxide.
#

# cd + custom logic based on the value of _ZO_ECHO.
fn __zoxide_cd {|path|
    builtin:cd $path
}
"""

ELVISH_HOOK_PWD = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Initialize hook to track previous directory.
var oldpwd = $builtin:pwd
set builtin:before-chdir = [$@builtin:before-chdir {|_| set oldpwd = $builtin:pwd }]

# Initialize hook to add directories to zoxide.
if (builtin:not (builtin:eq $E:__zoxide_shlvl $E:SHLVL)) {
    set E:__zoxide_shlvl = $E:SHLVL
    set builtin:after-chdir = [$@builtin:after-chdir {|_| zoxide add -- $pwd }]
}
"""

ELVISH_HOOK_PROMPT = ELVISH_HOOK_PWD

ELVISH_HOOK_NONE = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Initialize hook to track previous directory.
var oldpwd = $builtin:pwd
set builtin:before-chdir = [$@builtin:before-chdir {|_| set oldpwd = $builtin:pwd }]

# Initialize hook to add directories to zoxide.
# -- not configured --
"""

ELVISH_INTERNAL = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

# Jump to a directory using only keywords.
fn __zoxide_z {|@rest|
    if (builtin:eq [] $rest) {
        __zoxide_cd ~
    } elif (builtin:eq [-] $rest) {
        __zoxide_cd $oldpwd
    } elif (and ('builtin:==' (builtin:count $rest) 1) (path:is-dir &follow-symlink=$true $rest[0])) {
        __zoxide_cd $rest[0]
    } else {
        var path
        try {
            set path = (zoxide query --exclude $pwd -- $@rest)
        } catch {
        } else {
            __zoxide_cd $path
        }
    }
}
edit:add-var __zoxide_z~ $__zoxide_z~

# Jump to a directory using interactive search.
fn __zoxide_zi {|@rest|
    var path
    try {
        set path = (zoxide query --interactive -- $@rest)
    } catch {
    } else {
        __zoxide_cd $path
    }
}
edit:add-var __zoxide_zi~ $__zoxide_zi~
"""

ELVISH_COMPLETIONS = """\

# Load completions.
fn __zoxide_z_complete {|@rest|
    if (!= (builtin:count $rest) 2) {
        builtin:return
    }
    edit:complete-filename $rest[1] |
        builtin:each {|completion|
            var dir = $completion[stem]
            if (path:is-dir $dir) {
                builtin:put $dir
            }
        }
}
set edit:completion:arg-completer[z] = $__zoxide_z_complete~
"""

ELVISH_FOOTER = """\

# =============================================================================
#
# To initialize zoxide, add this to your configuration (usually
# ~/.elvish/rc.elv):
#
#   eval (zoxide init elvish | slurp)
#
# Note: zoxide only supports elvish v0.18.0 and above.
"""


def _elvish_init(cmd, hook, no_cmd):
    if hook == "none":
        hook_section = ELVISH_HOOK_NONE
    else:
        hook_section = ELVISH_HOOK_PWD

    if no_cmd:
        cmd_section = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
        completions = ""
    else:
        cmd_section = f"""\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

edit:add-var {cmd}~ $__zoxide_z~
edit:add-var {cmd}i~ $__zoxide_zi~
"""
        completions = ELVISH_COMPLETIONS.replace(
            "set edit:completion:arg-completer[z] = $__zoxide_z_complete~\n",
            f"set edit:completion:arg-completer[{cmd}] = $__zoxide_z_complete~\n"
        )

    return ELVISH_UTIL + hook_section + ELVISH_INTERNAL + cmd_section + completions + ELVISH_FOOTER


# ---------------------------------------------------------------------------
# NUSHELL
# ---------------------------------------------------------------------------

NUSHELL_HOOK_PWD = """\
# Code generated by zoxide. DO NOT EDIT.

# =============================================================================
#
# Hook configuration for zoxide.
#

# Initialize hook to add new entries to the database.
export-env {
  $env.config = (
    $env.config?
    | default {}
    | upsert hooks { default {} }
    | upsert hooks.env_change { default {} }
    | upsert hooks.env_change.PWD { default [] }
  )
  let __zoxide_hooked = (
    $env.config.hooks.env_change.PWD | any { try { get __zoxide_hook } catch { false } }
  )
  if not $__zoxide_hooked {
    $env.config.hooks.env_change.PWD = ($env.config.hooks.env_change.PWD | append {
      __zoxide_hook: true,
      code: {|_, dir| ^zoxide add -- $dir}
    })
  }
}
"""

NUSHELL_HOOK_NONE = """\
# Code generated by zoxide. DO NOT EDIT.

# =============================================================================
#
# Hook configuration for zoxide.
#

# -- not configured --
"""

NUSHELL_HOOK_PROMPT = NUSHELL_HOOK_NONE  # nushell prompt -> none (no prompt hook)

NUSHELL_INTERNAL = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

# Jump to a directory using only keywords.
def --env --wrapped __zoxide_z [...rest: string] {
  let path = match $rest {
    [] => {'~'},
    [ '-' ] => {'-'},
    [ $arg ] if ($arg | path expand | path type) == 'dir' => {$arg}
    _ => {
      ^zoxide query --exclude $env.PWD -- ...$rest | str trim -r -c "\\n"
    }
  }
  cd $path
}

# Jump to a directory using interactive search.
def --env --wrapped __zoxide_zi [...rest:string] {
  cd $'(^zoxide query --interactive -- ...$rest | str trim -r -c "\\n")'
}
"""

NUSHELL_FOOTER = """\

# =============================================================================
#
# Add this to your env file (find it by running `$nu.env-path` in Nushell):
#
#   zoxide init nushell | save -f ~/.zoxide.nu
#
# Now, add this to the end of your config file (find it by running
# `$nu.config-path` in Nushell):
#
#   source ~/.zoxide.nu
#
# Note: zoxide only supports Nushell v0.89.0+.
"""


def _nushell_init(cmd, hook, no_cmd):
    if hook == "none":
        hook_section = NUSHELL_HOOK_NONE
    elif hook == "prompt":
        hook_section = NUSHELL_HOOK_NONE
    else:
        hook_section = NUSHELL_HOOK_PWD

    if no_cmd:
        cmd_section = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
    else:
        cmd_section = f"""\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

alias {cmd} = __zoxide_z
alias {cmd}i = __zoxide_zi
"""

    return hook_section + NUSHELL_INTERNAL + cmd_section + NUSHELL_FOOTER


# ---------------------------------------------------------------------------
# POSIX
# ---------------------------------------------------------------------------

POSIX_UTIL = """\
# shellcheck shell=sh

# =============================================================================
#
# Utility functions for zoxide.
#

# pwd based on the value of _ZO_RESOLVE_SYMLINKS.
__zoxide_pwd() {
    \\command pwd -L
}

# cd + custom logic based on the value of _ZO_ECHO.
__zoxide_cd() {
    # shellcheck disable=SC2164
    \\command cd "$@"
}
"""

POSIX_HOOK_PWD = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

\\command printf "%s\\n%s\\n" \\
    "zoxide: PWD hooks are not supported on POSIX shells." \\
    "        Use 'zoxide init posix --hook prompt' instead."
"""

POSIX_HOOK_PROMPT = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# Hook to add new entries to the database.
__zoxide_hook() {
    \\command zoxide add -- "$(__zoxide_pwd || \\command true)"
}

# Initialize hook.
if [ "${PS1:=}" = "${PS1#*\\$(__zoxide_hook)}" ]; then
    PS1="${PS1}\\$(__zoxide_hook)"
fi

# Report common issues.
__zoxide_doctor() {
    [ "${_ZO_DOCTOR:-1}" -eq 0 ] && return 0
    case "${PS1:-}" in
    *__zoxide_hook*) return 0 ;;
    *) ;;
    esac

    _ZO_DOCTOR=0
    \\command printf '%s\\n' \\
        'zoxide: detected a possible configuration issue.' \\
        'Please ensure that zoxide is initialized right at the end of your shell configuration file.' \\
        '' \\
        'If the issue persists, consider filing an issue at:' \\
        'https://github.com/ajeetdsouza/zoxide/issues' \\
        '' \\
        'Disable this message by setting _ZO_DOCTOR=0.' \\
        '' >&2
}
"""

POSIX_HOOK_NONE = """\

# =============================================================================
#
# Hook configuration for zoxide.
#

# -- not configured --
"""

POSIX_INTERNAL_PWD = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

# Jump to a directory using only keywords.
__zoxide_z() {
    __zoxide_doctor

    if [ "$#" -eq 0 ]; then
        __zoxide_cd ~
    elif [ "$#" -eq 1 ] && [ "$1" = '-' ]; then
        if [ -n "${OLDPWD}" ]; then
            __zoxide_cd "${OLDPWD}"
        else
            # shellcheck disable=SC2016
            \\command printf 'zoxide: $OLDPWD is not set'
            return 1
        fi
    elif [ "$#" -eq 1 ] && [ -d "$1" ]; then
        __zoxide_cd "$1"
    else
        __zoxide_result="$(\\command zoxide query --exclude "$(__zoxide_pwd || \\command true)" -- "$@")" &&
            __zoxide_cd "${__zoxide_result}"
    fi
}

# Jump to a directory using interactive search.
__zoxide_zi() {
    __zoxide_doctor
    __zoxide_result="$(\\command zoxide query --interactive -- "$@")" && __zoxide_cd "${__zoxide_result}"
}
"""

POSIX_INTERNAL_PROMPT = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

# Jump to a directory using only keywords.
__zoxide_z() {
    __zoxide_doctor

    if [ "$#" -eq 0 ]; then
        __zoxide_cd ~
    elif [ "$#" -eq 1 ] && [ "$1" = '-' ]; then
        if [ -n "${OLDPWD}" ]; then
            __zoxide_cd "${OLDPWD}"
        else
            # shellcheck disable=SC2016
            \\command printf 'zoxide: $OLDPWD is not set'
            return 1
        fi
    elif [ "$#" -eq 1 ] && [ -d "$1" ]; then
        __zoxide_cd "$1"
    else
        __zoxide_result="$(\\command zoxide query --exclude "$(__zoxide_pwd || \\command true)" -- "$@")" &&
            __zoxide_cd "${__zoxide_result}"
    fi
}

# Jump to a directory using interactive search.
__zoxide_zi() {
    __zoxide_doctor
    __zoxide_result="$(\\command zoxide query --interactive -- "$@")" && __zoxide_cd "${__zoxide_result}"
}
"""


def _posix_init(cmd, hook, no_cmd):
    if hook == "none":
        hook_section = POSIX_HOOK_NONE
        # hook=none: keep __zoxide_doctor call (called but not defined, posix silently fails)
        internal = POSIX_INTERNAL_PWD
    elif hook == "prompt":
        hook_section = POSIX_HOOK_PROMPT
        internal = POSIX_INTERNAL_PROMPT
    else:
        # hook=pwd: keep __zoxide_doctor call (it's called but not defined - posix's behavior)
        hook_section = POSIX_HOOK_PWD
        internal = POSIX_INTERNAL_PWD

    if no_cmd:
        cmd_section = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
    else:
        cmd_section = f"""\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

\\command unalias {cmd} >/dev/null 2>&1 || \\true
{cmd}() {{
    __zoxide_z "$@"
}}

\\command unalias {cmd}i >/dev/null 2>&1 || \\true
{cmd}i() {{
    __zoxide_zi "$@"
}}
"""

    footer = """\

# =============================================================================
#
# To initialize zoxide, add this to your configuration:
#
# eval "$(zoxide init posix --hook prompt)"
"""
    return POSIX_UTIL + hook_section + internal + cmd_section + footer


# ---------------------------------------------------------------------------
# TCSH
# ---------------------------------------------------------------------------

TCSH_HOOK_PWD = """\
# =============================================================================
#
# Hook configuration for zoxide.
#

# Hook to add new entries to the database.
set __zoxide_pwd_old = `pwd -L`
alias __zoxide_hook 'set __zoxide_pwd_tmp = "`pwd -L`"; test "$__zoxide_pwd_tmp" != "$__zoxide_pwd_old" && zoxide add -- "$__zoxide_pwd_tmp"; set __zoxide_pwd_old = "$__zoxide_pwd_tmp"'

# Initialize hook.
alias precmd ';__zoxide_hook'
"""

TCSH_HOOK_PROMPT = TCSH_HOOK_PWD

TCSH_HOOK_NONE = """\
# =============================================================================
#
# Hook configuration for zoxide.
#
"""

TCSH_INTERNAL = """\

# =============================================================================
#
# When using zoxide with --no-cmd, alias these internal functions as desired.
#

# Jump to a directory using only keywords.
alias __zoxide_z 'set __zoxide_args = (\\!*)\\
if ("$#__zoxide_args" == 0) then\\
    cd ~\\
else\\
    if ("$#__zoxide_args" == 1 && "$__zoxide_args[1]" == "-") then\\
        cd -\\
    else if ("$#__zoxide_args" == 1 && -d "$__zoxide_args[1]") then\\
        cd "$__zoxide_args[1]"\\
    else\\
        set __zoxide_pwd = `pwd -L`\\
        set __zoxide_result = "`zoxide query --exclude '"'"'$__zoxide_pwd'"'"' -- $__zoxide_args`" && cd "$__zoxide_result"\\
    endif\\
endif'

# Jump to a directory using interactive search.
alias __zoxide_zi 'set __zoxide_args = (\\!*)\\
set __zoxide_pwd = `pwd -L`\\
set __zoxide_result = "`zoxide query --exclude '"'"'$__zoxide_pwd'"'"' --interactive -- $__zoxide_args`" && cd "$__zoxide_result"'
"""

TCSH_FOOTER = """\

# =============================================================================
#
# To initialize zoxide, add this to your shell configuration file (usually ~/.tcshrc):
#
#     zoxide init tcsh > ~/.zoxide.tcsh
#     source ~/.zoxide.tcsh
"""


def _tcsh_init(cmd, hook, no_cmd):
    if hook == "none":
        hook_section = TCSH_HOOK_NONE
    else:
        hook_section = TCSH_HOOK_PWD

    if no_cmd:
        cmd_section = """\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
    else:
        cmd_section = f"""\

# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

alias {cmd} __zoxide_z
alias {cmd}i __zoxide_zi
"""

    return hook_section + TCSH_INTERNAL + cmd_section + TCSH_FOOTER


# ---------------------------------------------------------------------------
# XONSH
# ---------------------------------------------------------------------------

XONSH_UTIL = (
'# pylint: disable=missing-module-docstring\n'
'\n'
'import builtins  # pylint: disable=unused-import\n'
'import os\n'
'import os.path\n'
'import subprocess\n'
'import sys\n'
'import typing\n'
'\n'
'import xonsh.dirstack  # type: ignore # pylint: disable=import-error\n'
'import xonsh.environ  # type: ignore # pylint: disable=import-error\n'
'\n'
'# =============================================================================\n'
'#\n'
'# Utility functions for zoxide.\n'
'#\n'
'\n'
'\n'
'def __zoxide_bin() -> str:\n'
'    """Finds and returns the location of the zoxide binary."""\n'
'    zoxide = typing.cast(str, xonsh.environ.locate_binary("zoxide"))\n'
'    if zoxide is None:\n'
'        zoxide = "zoxide"\n'
'    return zoxide\n'
'\n'
'\n'
'def __zoxide_env() -> dict[str, str]:\n'
'    """Returns the current environment."""\n'
'    return builtins.__xonsh__.env.detype()  # type: ignore  # pylint:disable=no-member\n'
'\n'
'\n'
'def __zoxide_pwd() -> str:\n'
'    """pwd based on the value of _ZO_RESOLVE_SYMLINKS."""\n'
'    pwd = __zoxide_env().get("PWD")\n'
'    if pwd is None:\n'
'        raise RuntimeError("$PWD not found")\n'
'    return pwd\n'
'\n'
'\n'
'def __zoxide_cd(path: str | bytes | None = None) -> None:\n'
'    """cd + custom logic based on the value of _ZO_ECHO."""\n'
'    if path is None:\n'
'        args = []\n'
'    elif isinstance(path, bytes):\n'
'        args = [path.decode("utf-8")]\n'
'    else:\n'
'        args = [path]\n'
'    _, exc, _ = xonsh.dirstack.cd(args)\n'
'    if exc is not None:\n'
'        raise RuntimeError(exc)\n'
'\n'
'\n'
'class ZoxideSilentException(Exception):\n'
'    """Exit without complaining."""\n'
'\n'
'\n'
'def __zoxide_errhandler(\n'
'    func: typing.Callable[[list[str]], None],\n'
') -> typing.Callable[[list[str]], int]:\n'
'    """Print exception and exit with error code 1."""\n'
'\n'
'    def wrapper(args: list[str]) -> int:\n'
'        try:\n'
'            func(args)\n'
'            return 0\n'
'        except ZoxideSilentException:\n'
'            return 1\n'
'        except Exception as exc:  # pylint: disable=broad-except\n'
'            print(f"zoxide: {exc}", file=sys.stderr)\n'
'            return 1\n'
'\n'
'    return wrapper\n'
)

XONSH_HOOK_PWD = (
'\n'
'\n'
'# =============================================================================\n'
'#\n'
'# Hook configuration for zoxide.\n'
'#\n'
'\n'
'# Initialize hook to add new entries to the database.\n'
'if "__zoxide_hook" not in globals():\n'
'\n'
'    @builtins.events.on_chdir  # type: ignore  # pylint:disable=no-member\n'
'    def __zoxide_hook(**_kwargs: typing.Any) -> None:\n'
'        """Hook to add new entries to the database."""\n'
'        pwd = __zoxide_pwd()\n'
'        zoxide = __zoxide_bin()\n'
'        subprocess.run(\n'
'            [zoxide, "add", "--", pwd],\n'
'            check=False,\n'
'            env=__zoxide_env(),\n'
'        )\n'
)

XONSH_HOOK_PROMPT = XONSH_HOOK_PWD
XONSH_HOOK_NONE = XONSH_HOOK_PWD  # xonsh always has the hook

XONSH_INTERNAL = (
'\n'
'\n'
'# =============================================================================\n'
'#\n'
'# When using zoxide with --no-cmd, alias these internal functions as desired.\n'
'#\n'
'\n'
'\n'
'@__zoxide_errhandler\n'
'def __zoxide_z(args: list[str]) -> None:\n'
'    """Jump to a directory using only keywords."""\n'
'    if args == []:\n'
'        __zoxide_cd()\n'
'    elif args == ["-"]:\n'
'        __zoxide_cd("-")\n'
'    elif len(args) == 1 and os.path.isdir(args[0]):\n'
'        __zoxide_cd(args[0])\n'
'    else:\n'
'        try:\n'
'            zoxide = __zoxide_bin()\n'
'            cmd = subprocess.run(\n'
'                [zoxide, "query", "--exclude", __zoxide_pwd(), "--"] + args,\n'
'                check=True,\n'
'                env=__zoxide_env(),\n'
'                stdout=subprocess.PIPE,\n'
'            )\n'
'        except subprocess.CalledProcessError as exc:\n'
'            raise ZoxideSilentException() from exc\n'
'\n'
'        result = cmd.stdout[:-1]\n'
'        __zoxide_cd(result)\n'
'\n'
'\n'
'@__zoxide_errhandler\n'
'def __zoxide_zi(args: list[str]) -> None:\n'
'    """Jump to a directory using interactive search."""\n'
'    try:\n'
'        zoxide = __zoxide_bin()\n'
'        cmd = subprocess.run(\n'
'            [zoxide, "query", "-i", "--"] + args,\n'
'            check=True,\n'
'            env=__zoxide_env(),\n'
'            stdout=subprocess.PIPE,\n'
'        )\n'
'    except subprocess.CalledProcessError as exc:\n'
'        raise ZoxideSilentException() from exc\n'
'\n'
'    result = cmd.stdout[:-1]\n'
'    __zoxide_cd(result)\n'
)

XONSH_FOOTER = """\

# =============================================================================
#
# To initialize zoxide, add this to your configuration (usually ~/.xonshrc):
#
# execx($(zoxide init xonsh), 'exec', __xonsh__.ctx, filename='zoxide')
"""


def _xonsh_init(cmd, hook, no_cmd):
    if no_cmd:
        cmd_section = """\


# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

# -- not configured --
"""
    else:
        cmd_section = f"""\


# =============================================================================
#
# Commands for zoxide. Disable these using --no-cmd.
#

builtins.aliases["{cmd}"] = __zoxide_z  # type: ignore  # pylint:disable=no-member
builtins.aliases["{cmd}i"] = __zoxide_zi  # type: ignore  # pylint:disable=no-member
"""

    return XONSH_UTIL + XONSH_HOOK_PWD + XONSH_INTERNAL + cmd_section + XONSH_FOOTER


# =============================================================================
# Subcommand implementations
# =============================================================================

def cmd_add(paths, score=None):
    """Handle add subcommand: validate dir, add/increment in db."""
    if not paths:
        sys.stderr.write("zoxide: no path provided\n")
        sys.exit(1)

    # Determine increment
    increment = float(score) if score is not None else 4.0

    data = load_db()

    for path in paths:
        # Validate directory exists before resolving (report original path on error)
        if not os.path.isdir(path):
            sys.stderr.write(f"zoxide: not a directory: {path}\n")
            sys.exit(1)

        # Resolve symlinks if requested
        if os.environ.get("_ZO_RESOLVE_SYMLINKS") == "1":
            try:
                path = os.path.realpath(path)
            except Exception:
                pass
        else:
            path = os.path.abspath(path)

        found = False
        for entry in data:
            if entry["path"] == path:
                entry["score"] += increment
                found = True
                break

        if not found:
            data.append({"path": path, "score": increment})

    data = age_db(data)
    save_db(data)


def cmd_query(keywords, exclude=None, interactive=False, list_all=False,
              show_score=False, all_dirs=False, base_dir=None):
    """Handle query subcommand."""
    data = load_db()

    if interactive:
        try:
            import subprocess
            import shlex
            scored = []
            for entry in data:
                if exclude and (entry["path"] == exclude or
                                entry["path"].startswith(exclude + os.sep)):
                    continue
                if not all_dirs and is_excluded(entry["path"]):
                    continue
                if base_dir and not entry["path"].startswith(base_dir):
                    continue
                scored.append(entry)
            scored.reverse()
            scored.sort(key=lambda e: e["score"], reverse=True)
            lines = [e["path"] for e in scored]
            if not lines:
                sys.stderr.write("zoxide: no match found\n")
                sys.exit(1)
            fzf_opts = os.environ.get("_ZO_FZF_OPTS", "")
            fzf_cmd = ["fzf"]
            if fzf_opts:
                fzf_cmd.extend(shlex.split(fzf_opts))
            if keywords:
                fzf_cmd.extend(["--query", " ".join(keywords)])
            proc = subprocess.run(fzf_cmd, input="\n".join(lines),
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                sys.exit(1)
            result = proc.stdout.strip()
            if result:
                print(result)
            else:
                sys.exit(1)
        except FileNotFoundError:
            sys.stderr.write("zoxide: fzf not found\n")
            sys.exit(1)
        return

    if list_all:
        scored = []
        for entry in data:
            if not all_dirs and is_excluded(entry["path"]):
                continue
            if base_dir and not entry["path"].startswith(base_dir):
                continue
            if keywords:
                rank = match_keywords(entry["path"], keywords)
                if rank < 0:
                    continue
            scored.append(entry)
        # Sort by score DESC, ties broken by recency (most recently added = last in db = first in output)
        scored.reverse()
        scored.sort(key=lambda e: e["score"], reverse=True)
        for entry in scored:
            if show_score:
                print(f"{format_score(entry['score'])} {entry['path']}")
            else:
                print(entry["path"])
        return

    if not keywords:
        sys.stderr.write("zoxide: no match found\n")
        sys.exit(1)

    candidates = []
    for idx, entry in enumerate(reversed(data)):
        if exclude and (entry["path"] == exclude or
                        entry["path"].startswith(exclude + os.sep)):
            continue
        if not all_dirs and is_excluded(entry["path"]):
            continue
        if base_dir and not entry["path"].startswith(base_dir):
            continue
        rank = match_keywords(entry["path"], keywords)
        if rank >= 0:
            candidates.append((entry["path"], entry["score"], rank, idx))

    # Sort: primary by rank (which incorporates score), secondary by recency (idx already reversed)
    candidates.sort(key=lambda c: (c[2] * c[1], c[1], c[3]), reverse=True)

    if not candidates:
        sys.stderr.write("zoxide: no match found\n")
        sys.exit(1)

    best = candidates[0]
    if show_score:
        print(f"{format_score(best[1])} {best[0]}")
    else:
        print(best[0])


def cmd_remove(paths):
    """Handle remove subcommand."""
    if not paths:
        sys.stderr.write("zoxide: no path provided\n")
        sys.exit(1)

    data = load_db()

    for path in paths:
        # Try exact match first, then abspath match
        new_data = [e for e in data if e["path"] != path and
                    os.path.abspath(e["path"]) != os.path.abspath(path)]
        if len(new_data) == len(data):
            sys.stderr.write(f"zoxide: path not found in database: {path}\n")
            sys.exit(1)
        data = new_data

    save_db(data)


def cmd_import(from_format, db_path, merge=False):
    """Handle import subcommand."""
    if not from_format:
        sys.stderr.write("zoxide: --from is required\n")
        sys.exit(1)

    if not db_path:
        sys.stderr.write("zoxide: no import file provided\n")
        sys.exit(1)

    valid_formats = {"autojump", "z"}
    if from_format not in valid_formats:
        sys.stderr.write(
            f"error: invalid value '{from_format}' for '--from <FROM>'\n"
            f"  [possible values: autojump, z]\n\n"
            f"For more information, try '--help'.\n"
        )
        sys.exit(2)

    if not os.path.exists(db_path):
        sys.stderr.write(
            f"zoxide: could not open database for importing: {db_path}\n\nCaused by:\n    No such file or directory (os error 2)\n"
        )
        sys.exit(1)

    existing_data = load_db() if merge else []
    existing = {e["path"]: i for i, e in enumerate(existing_data)}
    new_entries = []

    try:
        with open(db_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                path = None
                score = 1.0

                if from_format == "autojump":
                    # autojump: weight TAB path
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        try:
                            score = float(parts[0])
                            path = parts[1]
                        except ValueError:
                            sys.stderr.write(
                                f"zoxide: import error\n\nCaused by:\n    0: invalid rank: {parts[0]}\n    1: invalid float literal\n"
                            )
                            sys.exit(1)
                    else:
                        continue
                elif from_format == "z":
                    # z: path|weight|timestamp
                    parts = line.split("|")
                    if len(parts) >= 2:
                        path = parts[0]
                        try:
                            score = float(parts[1])
                        except ValueError:
                            continue
                    else:
                        continue

                if path and os.path.isabs(path):
                    if path in existing:
                        existing_data[existing[path]]["score"] += score
                    else:
                        new_entries.append({"path": path, "score": score})
                        existing[path] = len(existing_data) + len(new_entries) - 1

    except Exception as e:
        sys.stderr.write(f"zoxide: import error\n\nCaused by:\n    {e}\n")
        sys.exit(1)

    all_data = existing_data + new_entries
    all_data = age_db(all_data)
    save_db(all_data)


def cmd_init(shell, cmd="z", hook="pwd", no_cmd=False):
    """Handle init subcommand - output shell init script."""
    valid_shells = ["bash", "elvish", "fish", "nushell", "posix", "powershell", "tcsh", "xonsh", "zsh"]
    if not shell:
        sys.stderr.write(
            "error: the following required arguments were not provided:\n"
            "  <SHELL>\n\n"
            "Usage: executable init <SHELL>\n\n"
            "For more information, try '--help'.\n"
        )
        sys.exit(2)

    if shell not in valid_shells:
        sys.stderr.write(
            f"error: invalid value '{shell}' for '<SHELL>'\n"
            f"  [possible values: bash, elvish, fish, nushell, posix, powershell, tcsh, xonsh, zsh]\n\n"
            f"For more information, try '--help'.\n"
        )
        sys.exit(2)

    valid_hooks = {"none", "prompt", "pwd"}
    if hook not in valid_hooks:
        sys.stderr.write(
            f"error: invalid value '{hook}' for '--hook <HOOK>'\n"
            f"  [possible values: none, prompt, pwd]\n\n"
            f"For more information, try '--help'.\n"
        )
        sys.exit(2)

    if shell == "bash":
        output = _bash_init(cmd, hook, no_cmd)
    elif shell == "zsh":
        output = _zsh_init(cmd, hook, no_cmd)
    elif shell == "fish":
        output = _fish_init(cmd, hook, no_cmd)
    elif shell == "powershell":
        output = _powershell_init(cmd, hook, no_cmd)
    elif shell == "elvish":
        output = _elvish_init(cmd, hook, no_cmd)
    elif shell == "nushell":
        output = _nushell_init(cmd, hook, no_cmd)
    elif shell == "posix":
        output = _posix_init(cmd, hook, no_cmd)
    elif shell == "tcsh":
        output = _tcsh_init(cmd, hook, no_cmd)
    elif shell == "xonsh":
        output = _xonsh_init(cmd, hook, no_cmd)
    else:
        sys.stderr.write(f"zoxide: unsupported shell: {shell}\n")
        sys.exit(1)

    sys.stdout.write(output)


# =============================================================================
# CLI argument parsing and dispatch
# =============================================================================

def parse_and_run():
    args = sys.argv[1:]

    if not args:
        sys.stderr.write(MAIN_HELP)
        sys.exit(2)

    if args[0] in ("-h", "--help"):
        sys.stdout.write(MAIN_HELP)
        sys.exit(0)

    if args[0] in ("-V", "--version"):
        print(f"zoxide {VERSION}")
        sys.exit(0)

    subcommands = {"add", "query", "remove", "import", "init", "edit"}

    if args[0] not in subcommands:
        sys.stderr.write(
            f"error: unrecognized subcommand '{args[0]}'\n\n"
            f"Usage: executable <COMMAND>\n\n"
            f"For more information, try '--help'.\n"
        )
        sys.exit(2)

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "add":
        paths = []
        score = None
        i = 0
        while i < len(sub_args):
            a = sub_args[i]
            if a in ("-h", "--help"):
                sys.stdout.write(ADD_HELP)
                sys.exit(0)
            elif a in ("-V", "--version"):
                print(f"zoxide-add {VERSION}")
                sys.exit(0)
            elif a in ("-s", "--score"):
                if i + 1 < len(sub_args):
                    try:
                        score = float(sub_args[i + 1])
                    except ValueError:
                        sys.stderr.write(f"zoxide: invalid score: {sub_args[i+1]}\n")
                        sys.exit(2)
                    i += 2
                else:
                    sys.stderr.write("zoxide: --score requires an argument\n")
                    sys.exit(2)
            elif a == "--":
                paths.extend(sub_args[i + 1:])
                break
            elif a.startswith("-"):
                sys.stderr.write(
                    f"error: unexpected argument '{a}' found\n\n"
                    f"Usage: executable add [OPTIONS] <PATHS>...\n\n"
                    f"For more information, try '--help'.\n"
                )
                sys.exit(2)
            else:
                paths.append(a)
            i += 1
        cmd_add(paths, score)

    elif subcommand == "query":
        keywords = []
        exclude = None
        interactive = False
        list_all = False
        show_score = False
        all_dirs = False
        base_dir = None
        i = 0
        while i < len(sub_args):
            a = sub_args[i]
            if a in ("-h", "--help"):
                sys.stdout.write(QUERY_HELP)
                sys.exit(0)
            elif a in ("-V", "--version"):
                print(f"zoxide-query {VERSION}")
                sys.exit(0)
            elif a == "--exclude":
                if i + 1 < len(sub_args):
                    exclude = sub_args[i + 1]
                    i += 2
                else:
                    sys.stderr.write("zoxide: --exclude requires an argument\n")
                    sys.exit(2)
                continue
            elif a.startswith("--exclude="):
                exclude = a[len("--exclude="):]
            elif a == "--base-dir":
                if i + 1 < len(sub_args):
                    base_dir = sub_args[i + 1]
                    i += 2
                else:
                    sys.stderr.write("zoxide: --base-dir requires an argument\n")
                    sys.exit(2)
                continue
            elif a in ("-i", "--interactive"):
                interactive = True
            elif a in ("-l", "--list"):
                list_all = True
            elif a in ("-s", "--score"):
                show_score = True
            elif a in ("-a", "--all"):
                all_dirs = True
            elif a == "--":
                keywords.extend(sub_args[i + 1:])
                break
            elif a.startswith("-"):
                sys.stderr.write(
                    f"error: unexpected argument '{a}' found\n\n"
                    f"Usage: executable query [OPTIONS] [KEYWORDS]...\n\n"
                    f"For more information, try '--help'.\n"
                )
                sys.exit(2)
            else:
                keywords.append(a)
            i += 1
        cmd_query(keywords, exclude=exclude, interactive=interactive,
                  list_all=list_all, show_score=show_score,
                  all_dirs=all_dirs, base_dir=base_dir)

    elif subcommand == "remove":
        paths = []
        i = 0
        while i < len(sub_args):
            a = sub_args[i]
            if a in ("-h", "--help"):
                sys.stdout.write(REMOVE_HELP)
                sys.exit(0)
            elif a in ("-V", "--version"):
                print(f"zoxide-remove {VERSION}")
                sys.exit(0)
            elif a == "--":
                paths.extend(sub_args[i + 1:])
                break
            elif a.startswith("-"):
                sys.stderr.write(
                    f"error: unexpected argument '{a}' found\n\n"
                    f"Usage: executable remove [PATHS]...\n\n"
                    f"For more information, try '--help'.\n"
                )
                sys.exit(2)
            else:
                paths.append(a)
            i += 1
        cmd_remove(paths)

    elif subcommand == "import":
        from_format = None
        db_path = None
        merge = False
        positional = []
        i = 0
        while i < len(sub_args):
            a = sub_args[i]
            if a in ("-h", "--help"):
                sys.stdout.write(IMPORT_HELP)
                sys.exit(0)
            elif a in ("-V", "--version"):
                print(f"zoxide-import {VERSION}")
                sys.exit(0)
            elif a == "--from":
                if i + 1 < len(sub_args):
                    from_format = sub_args[i + 1]
                    i += 2
                else:
                    sys.stderr.write("zoxide: --from requires an argument\n")
                    sys.exit(2)
                continue
            elif a.startswith("--from="):
                from_format = a[len("--from="):]
            elif a == "--merge":
                merge = True
            elif a == "--":
                positional.extend(sub_args[i + 1:])
                break
            elif a.startswith("-"):
                sys.stderr.write(
                    f"error: unexpected argument '{a}' found\n\n"
                    f"Usage: executable import [OPTIONS] --from <FROM> <PATH>\n\n"
                    f"For more information, try '--help'.\n"
                )
                sys.exit(2)
            else:
                positional.append(a)
            i += 1

        if positional:
            db_path = positional[0]

        cmd_import(from_format, db_path, merge=merge)

    elif subcommand == "init":
        shell = None
        cmd = "z"
        hook = "pwd"
        no_cmd = False
        positional = []
        i = 0
        while i < len(sub_args):
            a = sub_args[i]
            if a in ("-h", "--help"):
                sys.stdout.write(INIT_HELP)
                sys.exit(0)
            elif a in ("-V", "--version"):
                print(f"zoxide-init {VERSION}")
                sys.exit(0)
            elif a == "--cmd":
                if i + 1 < len(sub_args):
                    cmd = sub_args[i + 1]
                    i += 2
                else:
                    sys.stderr.write("zoxide: --cmd requires an argument\n")
                    sys.exit(2)
                continue
            elif a.startswith("--cmd="):
                cmd = a[len("--cmd="):]
            elif a == "--hook":
                if i + 1 < len(sub_args):
                    hook = sub_args[i + 1]
                    i += 2
                else:
                    sys.stderr.write("zoxide: --hook requires an argument\n")
                    sys.exit(2)
                continue
            elif a.startswith("--hook="):
                hook = a[len("--hook="):]
            elif a == "--no-cmd":
                no_cmd = True
            elif a == "--":
                positional.extend(sub_args[i + 1:])
                break
            elif a.startswith("-"):
                sys.stderr.write(
                    f"error: unexpected argument '{a}' found\n\n"
                    f"Usage: executable init [OPTIONS] <SHELL>\n\n"
                    f"For more information, try '--help'.\n"
                )
                sys.exit(2)
            else:
                positional.append(a)
            i += 1

        if positional:
            shell = positional[0]

        cmd_init(shell, cmd=cmd, hook=hook, no_cmd=no_cmd)

    elif subcommand == "edit":
        i = 0
        while i < len(sub_args):
            a = sub_args[i]
            if a in ("-h", "--help"):
                sys.stdout.write(EDIT_HELP)
                sys.exit(0)
            elif a in ("-V", "--version"):
                print(f"zoxide-edit {VERSION}")
                sys.exit(0)
            i += 1
        db_path = get_db_path()
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
        try:
            import subprocess
            subprocess.run([editor, db_path])
        except Exception as e:
            sys.stderr.write(f"zoxide: failed to open editor: {e}\n")
            sys.exit(1)


if __name__ == "__main__":
    parse_and_run()
