# OCP lab 경로 A — 등록 Source와 실제 Sync의 분리

기준은 [GitOps #5의 B 동의](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5#issuecomment-6030172661)와 [D의 11:53 KST 조건부 공유 사용창 보고](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5#issuecomment-6029883776)다. 사용창을 실제 등록 시점에 확인한다. 이 문서는 실제 등록·Sync·기동 결과가 아니다.

## 선택한 경로

기존 `openshift-gitops` Controller를 사용한다. `clusters/ocp-lab/root/`라는 디렉터리 이름과 달리 여기서 선택하는 Render에는 **AppProject 1개와 Application 1개만** 있고 별도의 Root Application은 없다. 두 객체 이름은 `seokpan-ocp-lab-app`, namespace는 `openshift-gitops`다. Application은 제한 Project를 참조하고 `seokpan-argotest`의 `apps/overlays/lab`만 소비한다. `bootstrap/`, `reuse/`, `new-namespace/`를 함께 등록하지 않는다. 새 Controller/Operator/Namespace를 설치하지 않는다.

Project는 해당 GitOps Repo·목적 Namespace 및 Deployment/StatefulSet/Service/ConfigMap/Route만 허용하고 cluster-scope를 차단한다. 이 Kind 허용은 객체 이름 하나만 허용하는 name-based 정책이 아니다. Secret은 외부 공급, Migration Job은 별도 실행이고 Namespace/PVC 권한을 추가하지 않는다. 기존 `default` Project·공유 객체는 보존한다.

Source 작성·관리 B, 리뷰 D, 실제 Bootstrap 적용은 D 또는 공유 Owner와 확인된 지정 실행자다. Git 변경→Review→지정 실행자 apply로 관리하며 Root가 없는 이 경로에서 Project/Application 자체가 Argo에 의해 자동 Sync되는 것으로 해석하지 않는다.

## 순서와 직접 조건

1. **Workload 입력 PR:** 실제 Image Digest·Route/Origin(D·Owner), DB/Schema/목적 자격·CA(C), Valkey 개정·권한·자원을 대조한다. Secret 값은 Git 밖에 둔다. 검토·병합한 전체 SHA를 고정한다.
2. **Controller 등록값 PR:** B가 두 `metadata.namespace`, Application Project/destination과 `targetRevision`을 정합화하고 D가 리뷰한다. `targetRevision`은 1번의 **이미 존재하는 Workload 전체 SHA**다. 등록 PR 자신의 SHA나 이동하는 main을 넣지 않는다.
3. **등록 전:** 해당 등록 Source의 두 객체 Render·아래 비교 검사와 실제 Controller/CRD/RBAC·객체 충돌·공유 사용창을 확인한다. 검토된 Git 원본을 지정 실행자가 한 번 apply해 Bootstrap한다. 등록 Source SHA와 소비 Workload SHA를 각각 기록한다.
4. **최초 Workload Sync 전:** 정확한 Workload SHA에서 `release-manifest`·Image/Route/DB/Valkey 입력·live Diff를 확인하고 최초 수동 Sync한다. 자동 Sync·SelfHeal·자동 Prune·finalizer는 사용하지 않는다.
5. #5에 등록/Sync, #6의 실제 Run에 Pod Pull·Ready·TLS/AUTH·업무 결과를 분리한다. 등록 성공은 Workload 또는 ROSA Acceptance가 아니다.

현재 선언의 placeholder·replicas0·Migration suspend는 유지한다. Valkey Source 준비는 DB Schema·Cloud 금고/Pool 완료와 독립적으로 가능하지만 **현재 release-manifest는 lab Overlay 전체**를 검사한다. 이 독립성을 미해결 Route/DB 입력을 무시한 전체 Sync 또는 진단 Render Apply의 허가로 사용하지 않는다. 부분 기동은 해당 검토된 Source/실행 범위를 먼저 갖춰야 한다.

## 등록 선언 비교 명령

실행 장소는 **GitOps clone 최상위의 Source 검사 환경**이다. 이것은 `oc`나 AWS 명령이 아니며 클러스터에 접속하지 않는다. Kustomize5.7.1·Python/PyYAML은 기존 Source 검사 도구를 사용한다.

```bash
# 등록값 PR에 반영된 검토 Source checkout에서만 사용한다.
# WORKLOAD_SHA는 앞서 병합·수락한 Workload 전체40자리 SHA를 직접 지정한다.
: "${WORKLOAD_SHA:?Workload 전체 SHA를 먼저 지정하세요}"
registration_dir="$(mktemp -d)"
kustomize build clusters/ocp-lab/root > "$registration_dir/controller.yaml" &&
python3 tools/check_ocp_lab_registration.py \
  --manifest "$registration_dir/controller.yaml" \
  --workload-sha "$WORKLOAD_SHA"
```

현재 미해결 Source를 넣으면 **BLOCKED가 정상**이다. 도구는 YAML의 Repo/Kind/목적지·정확 SHA·수동/삭제 보호만 비교한다. SHA가 실제 존재하거나 리뷰·병합됐는지, Workload 입력이 완성됐는지, 실제 Owner/RBAC/사용창이 유효한지는 증명하지 않는다. `operation.sync`로 등록과 동시에 실행하거나 Helm/Kustomize override로 고정 Workload를 바꾸는 입력도 허용하지 않는다. Kustomize 명령이 로컬 진단 파일을 만들며 검사기는 그 파일을 읽을 뿐이다. 검사기가 입력 Manifest나 클러스터 객체를 생성/수정하지 않는다.

실제 등록값 PR에서는 현재의 보류 Source 기대 검사도 새 입력 상태와 함께 정합화한다. placeholder 거부라는 음성 Case는 합성 입력으로 계속 보존하며, 검사를 없애거나 실환경 수락 없이 성공으로 바꾸지 않는다.

정리·삭제, Secret/Migration 및 전체 기존 인계는 [첫 배포 인계](OCP_FIRST_DEPLOYMENT.md)와 [Controller Source 안내](../clusters/ocp-lab/README.md)를 함께 사용한다. 경로 A의 이후 결정과 충돌하는 예전 경로 선택 대기/새 Root 설명은 이 문서의 선택 범위로 대체하며 역사 후보를 삭제하지 않는다.
