#!/bin/zsh
# A third-party Desktop launcher. Configuration belongs to claude-config.
set -u

usage() {
    print 'Usage: launch.command --machine FILE [--claude-config EXECUTABLE] [--dry-run]'
    print 'Check the bound third-party App Profile, apply it, then open its Claude app.'
}
machine_file=''
config_command=''
preview=0
while (( $# )); do
    case "$1" in
        --machine|--claude-config)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            if [[ "$1" == --machine ]]; then machine_file=$2; else config_command=$2; fi
            shift 2 ;;
        --dry-run) preview=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) print -u2 -- "Unsupported option: $1"; usage >&2; exit 2 ;;
    esac
done
[[ -n "$machine_file" && -f "$machine_file" ]] || {
    print -u2 '请用 --machine 指定已有的 Machine 配置文件。'; exit 2
}
machine_file=${machine_file:a}
if [[ -z "$config_command" ]]; then
    config_command=$(command -v claude-config || true)
    [[ -n "$config_command" ]] || config_command="$HOME/.local/bin/claude-config"
fi
[[ -f "$config_command" && -x "$config_command" ]] || {
    print -u2 '未找到 claude-config；请先安装，或用 --claude-config 指定其路径。'; exit 2
}
config_command=${config_command:a}
helper="${0:A:h}/app/handle-report.js"
[[ -f "$helper" ]] || { print -u2 '启动器缺少报告处理文件，请重新构建。'; exit 2; }
work=$(mktemp -d "${TMPDIR:-/tmp}/claude-bootstrap.XXXXXX") || exit 1
completed=0
cleanup() {
    if (( completed )); then rm -rf -- "$work"; else print -u2 -- "本次原始输出：$work"; fi
}
trap cleanup EXIT
"$config_command" plan --app claude-desktop --machine "$machine_file" --format json >"$work/plan.json" 2>"$work/plan.stderr"
plan_exit=$?
plan_id=$(/usr/bin/osascript -l JavaScript "$helper" check "$work/plan.json" "$plan_exit" "$machine_file") || exit $?
if (( preview )); then
    /usr/bin/osascript -l JavaScript "$helper" preview "$work/plan.json" 0 "$machine_file" || exit $?
else
    "$config_command" apply --app claude-desktop --machine "$machine_file" --expect-plan-id "$plan_id" --format json >"$work/apply.json" 2>"$work/apply.stderr"
    apply_exit=$?
    /usr/bin/osascript -l JavaScript "$helper" launch "$work/plan.json" 0 "$machine_file" "$work/apply.json" "$apply_exit" || exit $?
fi
completed=1
