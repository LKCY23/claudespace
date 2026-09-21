#!/bin/zsh
set -eu

script_dir=${0:A:h}
python=${CLAUDE_BOOTSTRAP_PYTHON:-}

if [[ -z "$python" ]]; then
    python=$(command -v python3 || true)
    if [[ -z "$python" || "$python" == /usr/bin/python3 ]]; then
        for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
            /opt/anaconda3/bin/python3 "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3"; do
            if [[ -x "$candidate" ]]; then
                python=$candidate
                break
            fi
        done
    fi
fi

if [[ -z "$python" ]]; then
    printf '%s\n' 'Python 3.9+ is required. Set CLAUDE_BOOTSTRAP_PYTHON to its absolute executable path.' >&2
    exit 1
fi

exec "$python" "$script_dir/apply.py" --launch "$@"
