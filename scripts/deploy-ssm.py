"""Deploy an already published image to a bootstrapped K3s installation."""

import json
import os
import re
import subprocess
import time

image = os.environ["IMAGE"]
instance = os.environ["INSTANCE_ID"]
if not re.fullmatch(r"ghcr\.io/[a-z0-9_./-]+@sha256:[a-f0-9]{64}", image):
    raise SystemExit("Expected immutable GHCR image digest")
if not re.fullmatch(r"i-[a-f0-9]+", instance):
    raise SystemExit("Invalid EC2 instance ID")
commands = [
    "set -eu",
    "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml",
    "previous=$(kubectl -n school get deployment school-api -o jsonpath='{.spec.template.spec.containers[0].image}')",
    f"kubectl -n school set image deployment/school-api app={image}",
    "if ! kubectl -n school rollout status deployment/school-api --timeout=180s; then "
    'kubectl -n school set image deployment/school-api app="$previous"; '
    "kubectl -n school rollout status deployment/school-api --timeout=180s; exit 1; fi",
]
result = subprocess.check_output(
    [
        "aws",
        "ssm",
        "send-command",
        "--instance-ids",
        instance,
        "--document-name",
        "AWS-RunShellScript",
        "--parameters",
        json.dumps({"commands": commands}),
        "--output",
        "json",
    ],
    text=True,
)
command_id = json.loads(result)["Command"]["CommandId"]
for _ in range(90):
    time.sleep(5)
    result = subprocess.run(
        [
            "aws",
            "ssm",
            "get-command-invocation",
            "--command-id",
            command_id,
            "--instance-id",
            instance,
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        continue
    invocation = json.loads(result.stdout)
    if invocation["Status"] in ["Pending", "InProgress", "Delayed"]:
        continue
    print(invocation.get("StandardOutputContent", ""))
    print(invocation.get("StandardErrorContent", ""))
    if invocation["Status"] != "Success":
        raise SystemExit("Deployment failed: " + invocation["Status"])
    break
else:
    raise SystemExit("Timed out waiting for SSM deployment")
