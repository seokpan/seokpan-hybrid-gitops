# Cloud 플랫폼 계약과 관리 조회 권한 후보

실제 Namespace·Argo Controller·Ingress Router 인계가 없는 상태에서도 검토할 수 있는 Source 도구다. `contract.fixture.json`은 합성 시험 전용이며 실제 Cluster 입력이나 승인 자료가 아니다. 기본 App Overlay 및 어떤 Root Kustomization에도 연결하지 않았다. Namespace를 실제 생성하거나 Application을 등록하지 않는다.

```bash
python3 tools/cloud_platform_contract.py platform/cloud/contract.fixture.json
# 보호 경로에서 검토한 비민감 계약으로 별도 새 후보 파일을 만들 때:
python3 tools/cloud_platform_contract.py /private/reviewed-contract.json --output /private/new-cloud-platform-candidate.yaml
```

오프라인 계약 검사는 필수 필드·Namespace 분리·전체 40자리 Source 개정·Router의 정확한 Namespace/Pod selector를 요구한다. 통과는 필드의 형식과 선언 경계이며 실제 Source 존재·Owner 승인·Router 레이블의 진위·실효 권한·통신을 증명하지 않는다. 입력 오류에 입력 값을 출력하지 않고 기존 출력 파일을 덮어쓰지 않는다. 합성 파일을 수정해 실제 값처럼 제출하지 않는다.

후보 객체는 플랫폼 Owner가 관리할 Namespace·조회 Role·Ingress NetworkPolicy와 Argo 관리 Namespace의 수동 AppProject/Application이다. AppProject는 해당 Repo·단일 App Namespace와 Deployment/Service/ConfigMap/Route/PDB만 허용한다. Namespace/Secret/RBAC/NetworkPolicy는 App Sync 범위에서 제외한다. PDB는 승인된 Cloud 목표 Source를 별도 활성화할 때 쓰는 종류 허용이며 현재 Overlay에 PDB를 추가하지 않는다. 자동 Sync·Self Heal·Prune·Cascade finalizer·CreateNamespace를 추가하지 않는다. 플랫폼 후보와 App 후보를 한 Application에 넣지 않는다.

조회 Role은 App Namespace의 상태 조회만 제공한다. Secret·ConfigMap·Pod 생성/exec/portforward·권한 수정 권한은 없다. Pod 로그 조회는 명시적 선택이며 로그에 포함될 수 있는 민감정보 보호를 별도 검토한다. GitHub Team은 OpenShift Group과 자동으로 같다고 취급하지 않는다. 로그인 후 관측한 OpenShift User/Group과 담당별 권한을 확인하기 전 RoleBinding을 생성하지 않는다. 이 Role은 Argo Writer·dedicated-admin·Bootstrap 관리자 권한을 대신하지 않는다.

Ingress 후보는 전용 Namespace의 기본 차단, 관측 Router Namespace와 Pod를 **같은 peer의 AND 조건**으로 제한한 FE 8080/BE 8000 접근, 같은 Namespace의 FE→BE 8000만 선언한다. 기존 NetworkPolicy의 허용은 합산되므로 이 후보만으로 차단 효과를 확정하지 않는다. hostNetwork Router의 실제 Source 처리와 Health/모니터링 경로도 실행 환경에서 확인한다. Egress는 이 도구가 제한하지 않는다. DNS·DB·Redis·필수 외부 호출의 관측 없이 임의 deny-egress를 배포하지 않으며 Egress 제한은 별도 검토·시험 후 추가한다. Ingress-only 후보를 전체 NetworkPolicy 완료로 올리지 않는다.

실행 순서는 A의 실제 Cluster 인계 → B/플랫폼 Owner의 Namespace·Controller·Router 확인 → 관리 IdP 및 실제 Subject 대조 → 후보 리뷰 → 별도 플랫폼 수동 적용 → RBAC 양성/음성·허용/차단 통신 검증 → 실제 Cloud App Release 입력 수락 → 별도 수동 등록/Sync다. 현재 Cloud App의 입력 대기/0 Replica 보류는 그대로다.

남은 검증: 비팀원/권한 제거 후 로그인과 기존 Token, Secret 및 exec/portforward 거부, 다른 Namespace 거부, Router/FE 경로 성공, 무관 Pod/Namespace 접근 실패, DNS/DB/Redis 정상 연결과 정책 충돌 여부, Prune/Delete 차단. Source 계약 PASS는 이 실행 결과의 대체가 아니다.

근거: [승인 설계](https://github.com/seokpan/seokpan-hybrid-docs/blob/1ac5e59dd55be728bc0ee280e2faa165ace860a8/design/03_DETAILED_DESIGN.md), [Kubernetes RBAC 최소권한](https://kubernetes.io/docs/concepts/security/rbac-good-practices/), [NetworkPolicy 합산과 peer](https://kubernetes.io/docs/concepts/services-networking/network-policies/), [Argo 프로젝트 경계](https://argo-cd.readthedocs.io/en/stable/user-guide/projects/).
