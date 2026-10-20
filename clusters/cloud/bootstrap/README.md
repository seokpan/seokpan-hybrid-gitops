# Cloud 프로젝트와 Namespace 배포 기반

> **B 전수 대조 후속 — 2026-10-21:** [최종 종료](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/execution/B_ROSA_FINAL_CLOSEOUT_20261021.md)와 [실제 시험 결과](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/execution/HPA_ATTEMPT04_VERIFIED_RESULTS_20261021.md)를 우선한다. B ROSA·정확한 소유 범위 잔존 자원·Snapshot4개 정리는 완료다. 아래 절차·입력 대기·명령은 작성 당시 기록 또는 재사용 계약이며 현재 재실행 요청이 아니다. A 자원과 다른 담당의 종료는 판정하지 않는다. [전체 대조](https://github.com/seokpan/seokpan-hybrid-docs/blob/078b93184790231fbc3b0e03c9ce0b767ab39dab/execution/TJUNG03_FULL_REPOSITORY_AUDIT_20261021.md).

Argo AppProject의 저장소·목적지 허용과 Kubernetes Controller의 실제 배포 권한은 별개다. 기존 Cloud 계약 도구의 AppProject 선언을 재사용하고, 관측된 Router와 Controller 정보를 후속 플랫폼 설정에 연결한다. [승인 설계](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/design/03_DETAILED_DESIGN.md)와 [Cloud 플랫폼 계약](../../../platform/cloud/README.md)의 후속이다.

## AppProject 등록

`register-cloud-project.sh`는 성공한 개인 권한 결과와 Cluster API를 대조한다. seokpan-cloud-app AppProject가 없으면 서버 dry-run 후 생성하고, 동일 선언은 재사용하며 충돌하는 설정은 덮어쓰지 않는다. GitOps 저장소 한 개와 seokpan-cloud 목적지 한 개, Deployment·Service·ConfigMap·Route·PDB만 허용한다. Cluster 자원은 전부 거부한다. Secret·Namespace·RBAC·NetworkPolicy를 앱 Sync에 넣지 않는다.

Controller 실제 결과에서 프로젝트 생성과 Router·Controller 정보 수집이 성공했다. Router는 openshift-ingress의 default selector/hostNetwork=false, Controller는 openshift-gitops-application-controller StatefulSet과 openshift-gitops-argocd-application-controller ServiceAccount다. 이 단계의 완료를 Controller 실효 권한이나 개인 Argo SSO 성공으로 확대하지 않는다. 완료한 등록을 다시 실행할 필요는 없다.

## Namespace 배포 권한·Ingress 후속

`platform-next.py ROOT PROJECT_RESULT --apply`는 위 성공 결과를 소비한다. 현재 접속 대상, Router·Controller, 실행 중 Deployment가 없는 보류 상태를 확인한다. 앱 종류의 get/list/watch/create/update/patch와 상태 조회에 필요한 Controller 권한46개(기존45개와 Route custom-host create)를 실제 impersonation으로 조회한다. 부족할 때만 Cloud Namespace의 Role/RoleBinding 한 쌍을 추가한다. 새 Role은 Secret·Pod 생성/exec·RBAC 변경·delete·Cluster 권한을 부여하지 않는다. 기존의 다른 권한은 제거하지 않으며 별도 조회 결과로 남긴다.

Ingress는 관측 Router Namespace와 Pod selector를 같은 peer의 AND 조건으로 묶어 FE8080·BE8000을 허용하고, 같은 Namespace의 FE→BE8000 및 기본 ingress 차단까지 네 정책이다. Egress는 제한하지 않는다. 기존 정책의 이름/범위가 다르면 합산 효과를 검토하기 전 중단한다. Router/FE의 실제 허용·차단 통신과 Health/모니터링 경로는 앱 수락 단계에서 별도로 시험해야 한다.

모든 새 객체의 서버 dry-run을 마친 뒤 한 번씩 생성한다. 같은 객체는 재사용하고 다른 설정·소유자는 덮어쓰지 않는다. 허용 정책을 먼저, 기본 차단을 마지막에 생성한다. 일부 생성 또는 응답 오류가 생기면 결과/실행 표시를 보존하며 자동 재시도·자동 삭제를 하지 않는다. 앱·Root/Application·Sync·SQL·Migration·IAM·사람 권한·초기 인증 회수는 실행하지 않는다.

## 검증과 남은 조건

- AppProject: 기존 생성 도구 일치, Kustomize 단일 객체, Bash 문법과 Controller 등록 실제 통과.
- 후속 도구: Controller 실제 결과에서 Role/RoleBinding과 Ingress 정책4개 생성·기존 필수 권한45개 통과. 신규 custom-host create 권한은 별도 보완 대상으로 확인됐다. 최소 Role/Router/권한 조회 회귀19개와 custom-host 복구·UID/버전 경쟁 상태 회귀11개를 CI에서 직접 실행한다.
- 개인 OpenShift·Argo 로그인 화면은 성공으로 수신했다. 현재 세션의 Argo 허용/거부 정책과 실제 네트워크 통신 수락, 외부 통신 제한, 최종 Data 이관/서비스 계정·Pool·Migration·앱 업무/전환은 별도 잔여다.

## 기존 클러스터의 Route 권한 보완

실제 조회에서 Argo Controller의 `routes/custom-host` create가 거부됐다. 명시적인 host를 가진 Route의
Sync 전에 이 권한을 Cloud Namespace에만 보완한다. 앞으로 새로 생성하는 Controller Role에는 이 규칙을 포함한다.

`route-custom-host.py ROOT --apply`는 이미 생성된 `seokpan-cloud-application-controller` Role과
Binding·Controller SA·현재 Cluster API를 대조한다. 원래 규칙10개가 정확히 같은 Role에만
`route.openshift.io / routes/custom-host / create` 한 규칙을 추가한다. UID·resourceVersion·기존 규칙에
JSON Patch test를 걸고 서버 dry-run 뒤 한 번 적용한다. 오류·부분 응답·권한 반영 지연 시 자동 재시도하지 않는다.
이름/소유권/기존 규칙/Binding이 다르면 중단한다. 기존45개 권한, Ingress 설정·설치·로그인 검사를 다시 실행하지 않는다.
새 규칙이 이미 정확히 있으면 쓰기 없이 새 권한만 확인한다. 이 도구와 같은 개정의 `platform-next.py`를 같은 폴더에 둔다.

기존 Secret get·RoleBinding create의 출처는
`openshift-gitops-openshift-gitops-argocd-application-controller` ClusterRoleBinding과 동명 ClusterRole로 확인됐다.
새 Namespace Role에서 부여한 권한이 아니다. 전체 권한이 최소화됐다고 판단하지 않으며,
Operator 설정·다른 소비자 영향 확인 없이 기본 ClusterRole/Binding을 직접 삭제하거나 축소하지 않는다.

## 객체 소유권·삭제 보호와 모니터링

AppProject는 별도 bootstrap으로 등록한다. AppProject의 `Prune=false,Delete=false` 주석은
Argo가 해당 AppProject를 관리할 때의 의도를 표시하며, 현재 수동 등록 객체에 대한 삭제 방어를 보장하지 않는다.
직접 Kubernetes 삭제·다른 Controller의 삭제까지 차단하는 설정도 아니다.

모니터링 선언은 별도 경로·Application/AppProject로 분리한다. 현재 앱 AppProject에
ServiceMonitor·PrometheusRule·NetworkPolicy를 추가하지 않는다. 모니터링 전용 NP는 기본 차단을
삭제하지 않고 실제 UWM Namespace/Pod selector와 실제 metrics 포트만 허용하는 추가 정책으로 관리한다.
ServiceMonitor와 PrometheusRule은 선언 Sync와 실제 target UP/규칙 평가·알림 수락을 구분한다.
모니터링 객체와 기존 앱/플랫폼 객체를 두 Application이 중복 소유하지 않도록 해야 한다.
