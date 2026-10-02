# Frontend Runtime Desired State

이 디렉터리는 `application` Namespace의 Frontend Kubernetes Desired State 기반을 관리합니다.

## 현재 단계

현재 [Deployment](deployment.yaml)는 `replicas: 2`를 선언하고 같은 Origin의 Gateway 경로를 사용합니다. Backend·Frontend·Gateway의 기존 통합 결과와 검증 범위는 [1차 종료 시점 상태](https://github.com/seokpan/seokpan-docs/blob/main/CURRENT_STATE.md)에서 추적합니다. 아래 초기 활성화 Gate는 과거 체크포인트이며 현재 Runtime을 다시 조회한 결과가 아닙니다.

- Deployment는 `replicas: 2`이며 두 Worker에 강제 분산합니다.
- RollingUpdate는 `maxSurge: 0`, `maxUnavailable: 1`로 고정합니다.
- PDB `minAvailable: 1`은 Eviction API를 사용하는 계획된 축출에서 최소 한 Pod를 유지합니다.
- 현재 Image Digest는 [`kustomization.yaml`](kustomization.yaml)의 `images` 항목을 기준으로 합니다.
- Deployment는 `application/harbor-pull-secret`을 명시적으로 참조합니다.
- Argo CD Child Application `apps-frontend`는 Root Application에 편입되어 `apps/frontend`를 `main` 기준으로 관리합니다.
- `/tmp`만 `emptyDir`로 제공하고 Root Filesystem은 읽기 전용으로 실행합니다.
- 종료 전 5초의 Endpoint 전파 여유를 두고 전체 종료 유예는 45초로 고정합니다.

## Runtime 계약

- Deployment / Service: `frontend`
- Container / Service Port: `8080`, name `http`
- Image: `harbor.seokpan.soldesk.store/seokpan/frontend`
- Frontend는 환경별 Backend 절대 URL을 Image에 굽지 않고 같은 Origin의 `/api/v1`, `/ws/v1`을 사용합니다.

## Image 갱신 계약

CI는 `git-<main-commit-12자리>` Tag로 Harbor에 Push한 뒤 실제 Digest를 확인합니다.

[App 이미지 파이프라인](https://github.com/seokpan/seokpan-app/blob/main/Jenkinsfile.image-pipeline)이 검증 이미지를 확정하고, [Promotion 스크립트](https://github.com/seokpan/seokpan-app/blob/main/scripts/promote_gitops.py)가 변경 대상 컴포넌트의 GitOps PR을 생성합니다. 팀원 리뷰·승인·Merge 후 Argo CD가 변경된 선언을 동기화합니다. 자동 PR 생성과 배포 승인은 별도 단계입니다.

App PR #75 병합 뒤 Jenkins main Image Build #5에서 확인한 Digest는 초기 이미지 검증 이력입니다. 이후 변경을 포함한 현재 Digest는 `kustomization.yaml`에서 확인합니다.

`latest`는 사용하지 않습니다.

## Runtime 활성화 Gate

아래는 초기 Frontend 활성화 변경의 선행조건과 병합 후 확인 계획을 보존한 기록입니다. 현재 미완료 목록이나 재실행 지시로 사용하지 않습니다. 후속 통합 결과는 상단의 1차 종료 시점 상태로 연결합니다.

1. 실제 Frontend 구현 완료 — 완료
2. Frontend Container Image 존재 — 완료
3. Harbor Push 및 실제 Digest 확인 — 완료
4. SPA Fallback과 `/health/live`를 포함한 Image Process Smoke — 완료
5. 초기 Runtime Smoke Test 준비 — 완료
6. Argo CD Child Application 연결 — 완료
   - `apps-frontend`가 Root Application에 편입되어 `apps/frontend`를 `main` 기준으로 관리하며 `prune: true`, `selfHeal: true`를 사용합니다.
   - 당시 계획은 병합 후 `apps-frontend`의 Sync/Health와 실제 적용 Revision을 확인하는 것이었습니다.
7. Gateway의 현재 Client Route·Asset→Frontend, `/api/v1`·`/ws/v1`→Backend 연결 — 초기 Desired State 변경에 포함하고 병합 후 실제 연결을 확인하는 계획이었습니다.

## 후속 연결

- `seokpan-gitops#58` — Backend/Frontend Child Application Root 편입 및 Sync 검증
- `seokpan-gitops#27`, `seokpan-app#40` — Jenkins → Harbor → GitOps PR
- `seokpan-gitops#29` — Backend/Frontend Runtime Desired State 기반
