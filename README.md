# seokpan-hybrid-gitops

석판 2차 프로젝트의 ROSA OpenShift GitOps와 별도 온프레미스 Recovery 환경의 애플리케이션·플랫폼 배포 선언을 위한 저장소입니다. 승인된 설계에서는 공통 선언과 환경별 설정 및 Terraform과 GitOps의 Resource Ownership을 구분합니다. Offline Recovery에는 사전 Render·보존한 Manifest를 Infra Ansible로 적용하도록 정했습니다.

공통 App base와 lab/Recovery 설정·새 Recovery Redis 후보는 [apps](apps/README.md)에 있습니다. Source CI는 실제 Kustomize Build와 선언 경계를 검사합니다. Image·Secret/CA·저장소·대상·접속 경로 입력이 남아 FE/BE/새 Redis의 기동을 보류했습니다. Runtime/복구·Bundle 검증 완료를 뜻하지 않습니다.

저장소 책임과 배포·복구 기준은 [2차 상세설계](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/design/03_DETAILED_DESIGN.md)에서 확인합니다.
