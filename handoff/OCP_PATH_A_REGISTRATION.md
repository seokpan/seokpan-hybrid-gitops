# OCP lab 경로 A — 등록 Source와 단계별 Sync의 분리

현재 기준은 [GitOps #5 단계별 활성화·작성/리뷰 갱신](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5#issuecomment-6032629690)이다. [기존 B 동의](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5#issuecomment-6030172661)와 [D의 11:53 KST 조건부 공유 사용창 보고](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5#issuecomment-6029883776)는 그 시점의 기록으로 보존한다. 실제 등록 시 유효한 공유 사용창을 확인한다. 이 문서는 실제 등록·Sync·기동 결과가 아니다.

## 선택한 경로와 책임

기존 `openshift-gitops` Controller에 `AppProject/seokpan-ocp-lab-app`과 `Application/seokpan-ocp-lab-app` 각 1개만 등록한다. 두 객체의 namespace는 `openshift-gitops`, Application project는 `seokpan-ocp-lab-app`, destination은 `seokpan-argotest`, Workload path는 `apps/overlays/lab`다. `clusters/ocp-lab/root/`라는 디렉터리 이름은 별도 Root Application을 추가한다는 뜻이 아니다. `bootstrap/`, `reuse/`, `new-namespace/`를 함께 등록하거나 새 Controller/Operator/Namespace를 설치하지 않는다.

Project는 해당 Repo·목적지와 Deployment/StatefulSet/Service/ConfigMap/Route만 허용하고 cluster-scope를 차단한다. Kind 허용은 객체 이름 단위 제한이 아니다. Secret은 외부 공급, Migration Job은 별도 실행이고 Namespace/PVC 권한을 추가하지 않는다. 기존 `default` Project·공유 객체는 보존한다.

D가 lab 실행 입력인 Stage-1 활성화 PR과 Argo 등록 PR을 작성하고 B가 App/GitOps Source·배포 경계를 리뷰할 수 있다. 역할 재배정이 아니다. 이 #20의 검사 도구는 B 작성이며 A/D가 리뷰한다. 실제 Bootstrap은 D 또는 공유 Owner와 확인된 지정 실행자가 Git 변경→Review→지정 apply 순서로 수행한다. Root가 없는 이 경로에서 Project/Application 자체가 Argo에 의해 자동 Sync되는 구조는 아니다.

## 단계별 활성화와 Gate

| 단계 | Source | 실행 전 조건 |
|---|---|---|
| Stage 1 | lab Overlay에서 Valkey StatefulSet `lab-redis` replicas=1, release-state=`source-reviewed-runtime-unverified`. FE/BE는 replicas0 + input-required 유지 | 별도 Valkey Stage-1 Preflight Gate의 Source 구현·검증, exact SHA/Render·공유 사용창·live Diff 확인 후 Valkey 리소스만 선택 수동 Sync |
| Stage 2 | DB/Secret/CA/Route 수락 뒤 lab Overlay patch로 FE/BE release-state와 replicas 활성화 | 변경된 Workload SHA를 등록 Source에 반영하고 기존 전체 `release-manifest` 정상 통과 뒤 FE/BE 최초 수동 Sync |

base `backend.yaml`/`frontend.yaml`의 hold는 lab 때문에 제거하지 않는다. 기존 Source Test의 모든 Workload=0/input-required 및 lab-redis=0 조건을 단순 삭제/우회하지 않고 staged activation에 맞는 양성/음성 검사로 수정한다. base/Recovery hold와 Migration 별도 실행 경계는 유지한다.

**기존 전체 release-manifest를 약화하지 않는다.** Stage 1에서 FE/BE 미완성으로 전체 Gate가 실패한다는 사실을 무검사 기동 허가로 쓰지 않는다. 별도 Stage-1 Gate는 Valkey 승인 Digest, Render된 StatefulSet/Service/ConfigMap, TLS/AUTH Secret 참조, TLS-only/Readiness AUTH, arbitrary UID/securityContext, Resource/Persistence 조건을 검사하고 FE/BE/DB 입력에 의존하지 않아야 한다. #20의 Controller 등록 비교 도구는 이 Gate가 아니다. Stage-1 Gate의 구현/검증은 D 활성화 PR에서 다루며 이 안내만으로 완료로 표시하지 않는다.

## SHA·등록·Sync 순서

1. D Stage-1 활성화 PR / B 리뷰 → Merge하여 **SHA A** 확정.
2. D Controller 등록 PR / B 리뷰. 두 metadata.namespace와 project/destination을 위 경로로 맞추고 **targetRevision=SHA A**. 등록 Manifest 자신의 SHA 자기참조 또는 이동하는 main 사용 금지.
3. 검토된 등록 Source의 Render·아래 선언 비교·실제 Controller/CRD/RBAC·기존 객체 충돌·공유 Owner 사용창 확인 → 지정 실행자 최초 Bootstrap.
4. SHA A에서 Stage-1 Gate와 live Diff 확인 → 승인된 Valkey 리소스 선택 수동 Sync.
5. 실제 DB 입력 수락 → FE/BE 활성화 PR → **SHA B** 확정.
6. Controller 등록 Source의 targetRevision을 SHA B로 갱신·리뷰·지정 apply → SHA B의 전체 release-manifest 정상 통과 → FE/BE 최초 수동 Sync.

등록 Source SHA와 소비 Workload SHA를 각각 기록한다. 자동 Sync·SelfHeal·자동 Prune·finalizer는 최초 검증에 사용하지 않는다. Stage 2 전에 부재 보고된 `backend-db-runtime`·`backend-database-ca` 및 `backend-redis-runtime`·`backend-redis-ca`, DB Host/Name/Schema/목적 권한, Route Host/ALLOWED_ORIGINS를 실제 lab 개정과 대조한다. Secret 값은 Git 밖에 둔다.

#5는 등록·Sync/Health·Source SHA, #14는 공유 Owner/사용창/Registry/환경 입력, #6은 실제 Pull/Ready/TLS/AUTH/대표 업무 Run으로 구분한다. Source Merge·Argo Synced·Valkey Ready는 전체 lab Runtime PASS가 아니다.

## 등록 선언 비교 명령

실행 장소는 **GitOps clone 최상위의 Source 검사 환경**이다. Kustomize5.7.1·Python/PyYAML을 사용하며 클러스터에 접속하지 않는다.

```bash
# 등록값 PR에 반영된 검토 Source checkout에서만 사용한다.
# WORKLOAD_SHA는 먼저 병합·수락한 Workload의 전체40자리 SHA다.
: "${WORKLOAD_SHA:?Workload 전체 SHA를 먼저 지정하세요}"
registration_dir="$(mktemp -d)"
kustomize build clusters/ocp-lab/root > "$registration_dir/controller.yaml" &&
python3 tools/check_ocp_lab_registration.py \
  --manifest "$registration_dir/controller.yaml" \
  --workload-sha "$WORKLOAD_SHA"
```

현재 보류 Source의 namespace/SHA를 그대로 넣으면 BLOCKED다. 도구는 Source YAML의 정확 Repo/Kind/목적지/SHA·수동/삭제 보호 및 metadata를 비교한다. SHA 존재·리뷰·병합, Stage-1/전체 Workload Gate, 실제 Owner/RBAC/사용창·Secret 공급은 증명하지 않는다. 진단 Render를 Apply하지 않는다.

metadata는 현재 검토된 `name`·`namespace`·`annotations`와 비어 있는 선택적 `labels`만 허용한다. annotation은 `argocd.argoproj.io/sync-options=Prune=false,Delete=false`, `seokpan.io/release-state=source-reviewed-runtime-unverified`의 두 항목/값에 고정한다. Application의 `spec.syncPolicy`는 자동 Sync 없이 `syncOptions`의 `FailOnSharedResource=true`·`Prune=false`·`Delete=false` 세 항목만 허용한다. 이는 #24로 병합된 등록 Source와의 비교이며 실제 승인·등록·Sync·Runtime 검증을 대신하지 않는다. 과거 `input-required-no-runtime-validation`이나 Runtime PASS 표기는 등록 준비값으로 통과시키지 않는다. `skip-reconcile`·sync-wave/hook·추적/정책 label 등 추가 metadata는 모두 차단한다. live 객체의 자동 metadata를 정제 없이 넣어 통과시키는 도구가 아니다. 이후 등록 Source에서 metadata를 바꿀 때도 allowlist·시험을 같은 PR에서 명시적으로 리뷰한다. Workload의 Stage-1 release-state와 Controller metadata는 서로 다른 객체/경계다.

실제 등록값 PR에서 보류 Source 기대 검사를 새 상태와 정합화하되 placeholder 음성 Case는 합성 입력으로 보존한다. 기존 전체 인계는 [첫 배포 인계](OCP_FIRST_DEPLOYMENT.md)·[Controller Source 안내](../clusters/ocp-lab/README.md)를 함께 사용한다. 단계별 Source/Gate·Owner의 최신 기준은 이 문서를 우선하고 옛 후보·실행 이력을 지우지 않는다.
