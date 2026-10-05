# seokpan-hybrid-gitops

석판 2차 프로젝트의 ROSA OpenShift GitOps와 별도 온프레미스 Recovery 환경의 애플리케이션·플랫폼 배포 선언을 위한 저장소입니다. 승인된 설계에서는 공통 선언과 환경별 설정 및 Terraform과 GitOps의 Resource Ownership을 구분합니다. Offline Recovery에는 사전 Render·보존한 Manifest를 Infra Ansible로 적용하도록 정했습니다.

공통 App base와 lab/Recovery 설정·새 Recovery Redis 후보는 [apps](apps/README.md), 별도 Cloud 후속 후보는 [cloud](apps/overlays/cloud/README.md)에 있습니다. Source CI는 실제 Kustomize Build와 선언 경계를 검사합니다. Image·Secret/CA·저장소·대상·접속 경로 입력이 남아 FE/BE/새 Redis의 기동을 보류했습니다. Runtime/복구·Bundle 검증 완료를 뜻하지 않습니다.

저장소 책임과 배포·복구 기준은 [2차 상세설계](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/design/03_DETAILED_DESIGN.md)에서 확인합니다.


## 첫 OCP Source 인계와 리뷰

[최소 lab 제어 선언](clusters/ocp-lab/README.md)·[입력표/실행 Case](handoff/OCP_FIRST_DEPLOYMENT.md)를 사용한다. Source 리뷰와 실제 Image/lab 수락·활성화/TH 완료는 별도다. 기존 승인 Project/Application을 사용할 수 있고 새 Namespace 생성은 별도 선택 경로다. App 0 Replica/입력 대기, 수동 최초 Sync·자동 Prune 보류, 별도 suspended Migration 후보를 보존한다. 실제 Secret·Operator 설치 원본은 이 경로에서 생성하지 않는다.
