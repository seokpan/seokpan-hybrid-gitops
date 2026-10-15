#!/usr/bin/env bash
# Controller jth: register one scoped AppProject, then collect new platform inputs.
set +x
set -Eeuo pipefail
umask 077

project_root=${1:?existing protected ROSA input root required}
project_file=${2:?downloaded project.json required}
project_access=${3:?successful personal access result directory required}
project_phase=LOCAL_CONTEXT
project_created=false
project_result=''

project_stop() {
  trap - ERR
  printf 'STOP: %s; project_created=%s; no automatic retry.\n' "$project_phase" "$project_created" >&2
  if [[ -n "$project_result" ]]; then
    jq -n --arg phase "$project_phase" --argjson created "$project_created" \
      '{status:"STOP_PROJECT_REGISTRATION",phase:$phase,project_created:$created,app_created:false,sync_started:false}' \
      >"$project_result/receipt.json"
    printf 'Private project result directory: %s\n' "$project_result"
  fi
  exit 1
}
trap project_stop ERR

[[ $(id -un) == jth ]]
project_root=$(realpath -e -- "$project_root")
project_access=$(realpath -e -- "$project_access")
[[ $(dirname -- "$project_access") == "$project_root" && $(basename -- "$project_access") == human-access-* ]]
jq -e '.status=="PASS_PERSONAL_OPENSHIFT_AND_SCOPED_ARGO_CONFIGURATION" and .user=="tjung03" and .argo_project=="seokpan-cloud-app"' \
  "$project_access/receipt.json" >/dev/null
[[ $(sha256sum "$project_file" | cut -d ' ' -f1) == 52f10d8117cca5163e9bf557c7782330c56dac19d0904db13f84aa70711dee0b ]]

project_result=$(mktemp -d "$project_root/cloud-project-registration-XXXXXXXX")
project_matches=()
for project_candidate in "$project_root"/management/*/data-platform-handoff.json; do
  [[ -f "$project_candidate" ]] || continue
  if jq -e '.binding_enabled==true and (.cluster_id|type)=="string"' "$project_candidate" >/dev/null; then
    project_matches+=("$project_candidate")
  fi
done
[[ ${#project_matches[@]} == 1 ]]
project_api=$(jq -er '.api_url' "${project_matches[0]}")
project_server=$(oc whoami --show-server --request-timeout=20s)
[[ ${project_server%/} == "${project_api%/}" ]]

project_phase=EXISTING_PROJECT_SCOPE
oc get appproject seokpan-cloud-app -n openshift-gitops \
  --ignore-not-found=true --request-timeout=20s -o json \
  >"$project_result/project-before.json" 2>"$project_result/project-before.stderr"
if [[ -s "$project_result/project-before.json" ]]; then
  jq -e -s '.[0].spec==.[1].spec' "$project_file" "$project_result/project-before.json" >/dev/null
  printf 'PASS: existing exact Cloud AppProject reused.\n'
else
  project_phase=PROJECT_SERVER_DRY_RUN
  oc create --dry-run=server -f "$project_file" --request-timeout=20s -o json \
    >"$project_result/project-dry-run.json" 2>"$project_result/project-dry-run.stderr"
  project_phase=PROJECT_CREATE
  oc create -f "$project_file" --request-timeout=20s -o json \
    >"$project_result/project-create.json" 2>"$project_result/project-create.stderr"
  project_created=true
fi
oc get appproject seokpan-cloud-app -n openshift-gitops --request-timeout=20s -o json \
  >"$project_result/project-after.json" 2>"$project_result/project-after.stderr"
jq -e -s '.[0].spec==.[1].spec' "$project_file" "$project_result/project-after.json" >/dev/null

project_phase=ROUTER_INPUT_COLLECTION
oc get deployment -n openshift-ingress --request-timeout=20s -o json \
  >"$project_result/router-deployments.json" 2>"$project_result/router-deployments.stderr"
jq '[.items[] | select(.metadata.name=="router-default") | {
  namespace:.metadata.namespace,pod_labels:.spec.selector.matchLabels,
  host_network:(.spec.template.spec.hostNetwork // false)}]' \
  "$project_result/router-deployments.json" >"$project_result/router-inputs.json"

project_phase=CONTROLLER_PERMISSION_COLLECTION
oc get deployment,statefulset -n openshift-gitops --request-timeout=20s -o json \
  >"$project_result/controller-workloads.json" 2>"$project_result/controller-workloads.stderr"
jq '[.items[] | select(.metadata.name|endswith("-application-controller")) |
  {kind:.kind,name:.metadata.name,service_account:.spec.template.spec.serviceAccountName}]' \
  "$project_result/controller-workloads.json" >"$project_result/controller-inputs.json"

jq -n --argjson created "$project_created" \
  --slurpfile router "$project_result/router-inputs.json" \
  --slurpfile controller "$project_result/controller-inputs.json" \
  '{status:"PASS_CLOUD_PROJECT_REGISTERED_PLATFORM_INPUTS_COLLECTED",
    project:"seokpan-cloud-app",namespace:"seokpan-cloud",project_created:$created,
    router:$router[0],controller:$controller[0],
    controller_effective_permissions:"NOT_TESTED_BY_INVENTORY",
    app_created:false,sync_started:false,network_policy_changes:0,
    database_writes:0,sql_auth_repeated:false,personal_browser_acceptance:"PENDING"}' \
  | tee "$project_result/receipt.json"
printf 'Private project result directory: %s\n' "$project_result"
