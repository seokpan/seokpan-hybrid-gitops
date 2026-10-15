# Cloud AppProject 등록

정상 개인 로그인·Cloud 프로젝트 조회/Sync 권한을 연결한 뒤, Argo가 허용할 저장소·목적지·리소스 범위를 등록한다. 기존 `tools/cloud_platform_contract.py`가 생성하는 AppProject와 동일한 선언이다. 도구의 다른 후보 객체나 합성 Router 입력은 포함하지 않는다.

등록 객체는 openshift-gitops의 seokpan-cloud-app AppProject 하나다. 소스는 이 GitOps 저장소 한 개, 목적지는 클러스터 내부 seokpan-cloud Namespace 한 개로 제한한다. Deployment·Service·ConfigMap·Route·PodDisruptionBudget만 허용하고 Cluster 자원은 전부 거부한다. Secret·Namespace·RBAC·NetworkPolicy를 App Sync에 포함하지 않는다. Argo SSO/RBAC를 이 프로젝트 선언이 대신하지 않는다.

Application/Root 생성이나 Sync를 시작하지 않으므로 DB 이관 완료를 기다리지 않고 등록할 수 있다. 실제 Cloud App 등록은 보호 배포 입력과 Source 소유권, 최종 이관/서비스 계정·Pool·Migration·업무 전환 조건을 수락한 뒤 진행한다. 이 폴더를 기존 Root에 자동 연결하지 않았다.

`register-cloud-project.sh`는 Controller jth의 기존 관리 환경과 성공한 개인 권한 receipt를 사용한다. 동일 프로젝트가 있으면 범위를 대조해 재사용하고 다르면 덮어쓰지 않는다. 없으면 서버 dry-run 후 한 번 생성한다. 이후 실제 Router selector/hostNetwork 및 Argo Controller ServiceAccount 이름을 조회해 다음 플랫폼 검토용 보호 파일로 남긴다. 이 정보 수집은 ServiceAccount의 실제 생성 권한 시험을 포함하지 않는다. 조회가 실패하면 생성된 프로젝트를 임의로 삭제/재생성하지 않는다. 결과 폴더에 단계와 생성 여부가 남는다.

초기 관리자 접속을 유지하며 AppProject가 등록된 사실을 실제 개인 SSO 권한 수락이나 앱 배포 완료로 기록하지 않는다. Controller 실제 등록/정보 수집 결과는 아직 없다. 선언은 기존 생성 도구와 일치하고, Kustomize 구문·단일 객체 범위 및 실행 파일 문법을 로컬에서 확인한다.

관련: [Cloud 플랫폼 계약](../../../platform/cloud/README.md), [B 전체 체크리스트](https://github.com/seokpan/seokpan-hybrid-docs/issues/21).
