# Cloud 프로젝트와 Namespace 배포 기반

Argo AppProject의 저장소·목적지 허용과 Kubernetes Controller의 실제 배포 권한은 별개다. 기존 Cloud 계약 도구의 AppProject 선언을 재사용하고, 관측된 Router와 Controller 정보를 후속 플랫폼 설정에 연결한다. [승인 설계](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/design/03_DETAILED_DESIGN.md)와 [Cloud 플랫폼 계약](../../../platform/cloud/README.md)의 후속이다.

## AppProject 등록

`register-cloud-project.sh`는 성공한 개인 권한 결과와 Cluster API를 대조한다. seokpan-cloud-app AppProject가 없으면 서버 dry-run 후 생성하고, 동일 선언은 재사용하며 충돌하는 설정은 덮어쓰지 않는다. GitOps 저장소 한 개와 seokpan-cloud 목적지 한 개, Deployment·Service·ConfigMap·Route·PDB만 허용한다. Cluster 자원은 전부 거부한다. Secret·Namespace·RBAC·NetworkPolicy를 앱 Sync에 넣지 않는다.

Controller 실제 결과에서 프로젝트 생성과 Router·Controller 정보 수집이 성공했다. Router는 openshift-ingress의 default selector/hostNetwork=false, Controller는 openshift-gitops-application-controller StatefulSet과 openshift-gitops-argocd-application-controller ServiceAccount다. 이 단계의 완료를 Controller 실효 권한이나 개인 Argo SSO 성공으로 확대하지 않는다. 완료한 등록을 다시 실행할 필요는 없다.

## Namespace 배포 권한·Ingress 후속

`platform-next.py ROOT PROJECT_RESULT --apply`는 위 성공 결과를 소비한다. 현재 접속 대상, Router·Controller, 실행 중 Deployment가 없는 보류 상태를 확인한다. 앱 종류의 get/list/watch/create/update/patch와 상태 조회에 필요한 Controller 권한45개를 실제 impersonation으로 조회한다. 부족할 때만 Cloud Namespace의 Role/RoleBinding 한 쌍을 추가한다. 새 Role은 Secret·Pod 생성/exec·RBAC 변경·delete·Cluster 권한을 부여하지 않는다. 기존의 다른 권한은 제거하지 않으며 별도 조회 결과로 남긴다.

Ingress는 관측 Router Namespace와 Pod selector를 같은 peer의 AND 조건으로 묶어 FE8080·BE8000을 허용하고, 같은 Namespace의 FE→BE8000 및 기본 ingress 차단까지 네 정책이다. Egress는 제한하지 않는다. 기존 정책의 이름/범위가 다르면 합산 효과를 검토하기 전 중단한다. Router/FE의 실제 허용·차단 통신과 Health/모니터링 경로는 앱 수락 단계에서 별도로 시험해야 한다.

모든 새 객체의 서버 dry-run을 마친 뒤 한 번씩 생성한다. 같은 객체는 재사용하고 다른 설정·소유자는 덮어쓰지 않는다. 허용 정책을 먼저, 기본 차단을 마지막에 생성한다. 일부 생성 또는 응답 오류가 생기면 결과/실행 표시를 보존하며 자동 재시도·자동 삭제를 하지 않는다. 앱·Root/Application·Sync·SQL·Migration·IAM·사람 권한·초기 인증 회수는 실행하지 않는다.

## 검증과 남은 조건

- AppProject: 기존 생성 도구 일치, Kustomize 단일 객체, Bash 문법과 Controller 등록 실제 통과.
- 후속 도구: 최소 Role·Router AND 조건·허용 포트·Ingress-only·기존 범위 충돌·API 빈 배열 표현·권한 조회 오류 구분17개 오프라인 검사 통과. 실제 후속 적용은 아직 미실행이다.
- 개인 Argo SSO, 실효 권한의 허용/거부와 실제 정책 통신 수락, 외부 통신 제한, 최종 Data 이관/서비스 계정·Pool·Migration·앱 업무/전환은 별도 잔여다.
