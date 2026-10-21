#!/usr/bin/env bash
# Diagnostic-only, dependency-free cgroup memory snapshots for CI worker steps.
# Never output environment variables, database URLs, or process command lines.
ci_resource_snapshot() {
    local stage="${1:-unknown}" usage="unavailable" limit="unavailable"
    local peak="unavailable" oom="unavailable" oom_kill="unavailable"
    local name count

    if [ -r /sys/fs/cgroup/memory.current ]; then
        IFS= read -r usage < /sys/fs/cgroup/memory.current || :
        IFS= read -r limit < /sys/fs/cgroup/memory.max || :
        if [ -r /sys/fs/cgroup/memory.peak ]; then
            IFS= read -r peak < /sys/fs/cgroup/memory.peak || :
        fi
        if [ -r /sys/fs/cgroup/memory.events ]; then
            while read -r name count; do
                case "$name" in
                    oom) oom="$count" ;;
                    oom_kill) oom_kill="$count" ;;
                esac
            done < /sys/fs/cgroup/memory.events
        fi
    elif [ -r /sys/fs/cgroup/memory/memory.usage_in_bytes ]; then
        IFS= read -r usage < /sys/fs/cgroup/memory/memory.usage_in_bytes || :
        IFS= read -r limit < /sys/fs/cgroup/memory/memory.limit_in_bytes || :
        if [ -r /sys/fs/cgroup/memory/memory.max_usage_in_bytes ]; then
            IFS= read -r peak < /sys/fs/cgroup/memory/memory.max_usage_in_bytes || :
        fi
        if [ -r /sys/fs/cgroup/memory/memory.failcnt ]; then
            IFS= read -r oom < /sys/fs/cgroup/memory/memory.failcnt || :
        fi
    fi
    printf 'CI_RESOURCE stage=%s usage_bytes=%s limit_bytes=%s peak_bytes=%s oom_events=%s oom_kill_events=%s\n' \
        "$stage" "$usage" "$limit" "$peak" "$oom" "$oom_kill"
}


# Called only from a top-level ERR trap, not as a wrapper around setup functions.
# Preserves Bash's native errexit behavior for failures within those functions.
ci_log_failure() {
    local status="$1" lane="$2" stage="$3"
    ci_resource_snapshot "worker:error:$lane:$stage:exit=$status"
    if [ "$status" -ge 128 ]; then
        printf 'CI stage %s/%s exited %s (signal termination possible). Check cgroup OOM counters and worker/task deadlines; SIGKILL alone does not prove OOM.\n' \
            "$lane" "$stage" "$status" >&2
    fi
}
