#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/start-performix-ssm-tunnel.sh [LOCAL_PORT]

Start a private local TCP tunnel to port 22 of the Second Sight Arm benchmark
host through AWS Systems Manager. Keep this process running while Arm Performix
profiles the target. It never opens inbound SSH on the instance.

Environment:
  AWS_PROFILE                 AWS CLI profile (default: kyle)
  AWS_REGION                  AWS region (default: ap-southeast-2)
  SECOND_SIGHT_INSTANCE_ID    EC2 instance (default: i-0cbb864101d450172)
EOF
}

local_port="${1:-2222}"
if [[ "$local_port" == "--help" || "$local_port" == "-h" ]]; then
  usage
  exit 0
fi
if ! [[ "$local_port" =~ ^[1-9][0-9]{0,4}$ ]] || (( local_port > 65535 )); then
  echo "LOCAL_PORT must be an integer from 1 to 65535." >&2
  exit 1
fi
if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI is required." >&2
  exit 1
fi
if ! command -v session-manager-plugin >/dev/null 2>&1; then
  echo "Install the AWS Session Manager plugin before starting the tunnel." >&2
  exit 1
fi
if lsof -nP -iTCP:"$local_port" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Local port $local_port is already in use." >&2
  exit 1
fi

aws_profile="${AWS_PROFILE:-kyle}"
aws_region="${AWS_REGION:-ap-southeast-2}"
instance_id="${SECOND_SIGHT_INSTANCE_ID:-i-0cbb864101d450172}"

exec env AWS_PROFILE="$aws_profile" aws ssm start-session \
  --region "$aws_region" \
  --target "$instance_id" \
  --document-name AWS-StartPortForwardingSession \
  --parameters "portNumber=22,localPortNumber=$local_port"
