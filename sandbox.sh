#!/usr/bin/env bash
# sandbox.sh: manage the agent sandbox container.
#
# Usage: ./sandbox.sh build | start | stop | reset
#   build  Build the sandbox image from the Dockerfile in this directory.
#   start  Create and start the container with isolation and resource limits.
#   stop   Remove the container. The /workspace volume is kept.
#   reset  Remove the container and the /workspace volume, then start a new container.

# This is equivalent to
#   set -e
#   set -u
#   set -o pipefail
set -euo pipefail

IMAGE=sandbox-image
CONTAINER=agent-sbx
VOLUME=sbx-workspace

case "${1:-}" in
  build)
    docker build -t "$IMAGE" .
    ;;
  start)
    docker run -d --name "$CONTAINER" \
      --init \
      --user 1000:1000 \            # syntax: "run as {user ID}:{group ID}", specified in Dockerfile
      --read-only \
      --tmpfs /tmp:size=64m \       # This mounts a 64 MB memory-backed filesystem at /tmp. It is writable, and its contents are lost when the container stops.
      -v "$VOLUME":/workspace \     # syntax: v {local_volume_NAME}:{container_root_dir}. This mounts the named volume sbx-workspace at /workspace. Docker creates the volume if it does not exist. It is writable, and its contents persist after the container is removed.
      --network none \
      --cap-drop ALL \
      --security-opt no-new-privileges \
      --pids-limit 256 \
      --memory 1g --cpus 1 \
      "$IMAGE"
    ;;
  stop)
    docker rm -f "$CONTAINER"
    ;;
  reset)
    docker rm -f "$CONTAINER" || true
    docker volume rm "$VOLUME" || true
    "$0" start
    ;;
  *)
    echo "Usage: $0 build | start | stop | reset" >&2
    exit 1
    ;;
esac