# Cloud 선언 후보와 실행 보류

> **B 전수 대조 후속 — 2026-10-21:** [최종 종료](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/execution/B_ROSA_FINAL_CLOSEOUT_20261021.md)와 [실제 시험 결과](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/execution/HPA_ATTEMPT04_VERIFIED_RESULTS_20261021.md)를 우선한다. B ROSA·정확한 소유 범위 잔존 자원·Snapshot4개 정리는 완료다. 아래 절차·입력 대기·명령은 작성 당시 기록 또는 재사용 계약이며 현재 재실행 요청이 아니다. A 자원과 다른 담당의 종료는 판정하지 않는다. [전체 대조](https://github.com/seokpan/seokpan-hybrid-docs/pull/140).

ROSA Cloud App에 사용할 환경별 선언을 실제 Kustomize Overlay로 연결했다. 결과는 정적 Source 후보이며 실제 Cluster·Endpoint·Image·Secret·CA·Route·Runtime 검증은 남았다. 기본 Cloud Render는 공통 base의 FE/BE `replicas: 0`을 유지한다. `cloud-input-required`, `.invalid`, `INPUT_REQUIRED`는 실제 Namespace·Host·Image가 아니며 이 선언을 Apply/Sync하지 않는다.

본인 선언 원본은 [GitOps #10](https://github.com/seokpan/seokpan-hybrid-gitops/issues/10)의 TH-09, 상위 진행 원본은 [Docs #21](https://github.com/seokpan/seokpan-hybrid-docs/issues/21)이다. 기존 PR #9의 base/lab/Recovery 변경과 별도 Cloud 후속 범위를 연결하며, D의 #5/#6 실제 lab·수정 Image 검증 책임을 대신하지 않는다. Source 후보 작성/검사를 해당 체크 전체 완료로 올리지 않는다.

승인된 목표는 `03_DETAILED_DESIGN.md` §3-F.18.1의 FE/BE 각 3 Replica·PDB `minAvailable: 2`·Rolling `maxUnavailable: 0`/`maxSurge: 1`·AZ `ScheduleAnyway` 분산·Host Preferred 분산이다. 같은 문서 §3-F.18.2는 Source/프로세스/상태 공유 확인과 1 Replica 실측→3 Replica/Surge 자원·DB Pool 여유 확인을 실제 기동 조건으로 둔다. 따라서 **기본 실행 보류와 승인된 최종 목표를 구분**했다. 0은 실제 시험 결과나 목표를 0으로 바꾼 결정이 아니다.

`activation-target/`는 승인 목표의 별도 정적 Preview다. default Overlay가 이 경로를 소비하지 않으므로 현재 Render에 3 Replica/PDB가 자동으로 섞이지 않는다. 해당 Preview에도 미확인 Image·대상·draft 표기가 남으며 Argo Application의 Sync 경로로 지정하지 않는다. 필요한 입력과 단일 Replica 실측을 받은 뒤 리뷰된 변경으로 Cloud 기본 선언의 실행 보류를 해제하고 목표 설정을 연결한다.

Cloud 공통 입력은 `runtime/`에 두고 기본 실행 보류 Preview와 목표 Preview가 같은 Source를 소비한다. ConfigMap의 내용 Hash를 유지해 승인된 연결 설정 변경이 Backend Pod Template 참조에도 반영되도록 했다. Secret/CA 개정 교체·Runtime 재접속은 별도 공급/실행 Case로 확인한다.

## Lifecycle 입력과 다중 Backend 승격

App main `c12b3d15a4dd2c806fac4326a9eb30ed6e8a81b3`의 `Settings`는 `legacy`/`captured`를 허용한다. 기존 Cloud Source는 base의 `legacy`를 그대로 상속했으며 Cloud 전용 Override가 없었다. 이번에는 `runtime/runtime.env`에 `SEOKPAN_GAME_LIFECYCLE_MODE=INPUT_REQUIRED`를 명시해 확인되지 않은 모드를 자동 상속하거나 임의로 `captured`를 켜지 않는다. 기본 0 Replica와 3 Replica 정적 Preview의 입력 대기 상태는 유지한다. legacy가 모든 기능에서 단일 Pod 전용이라는 판정은 하지 않는다.

`tools/render_release.py`는 lab/Cloud의 FE/BE 및 initContainer가 Registry의 정확한 `@sha256` Image를 참조하도록 검사하고, Cloud Backend가 2개 이상일 때 `captured`를 명시한 검토된 ConfigMap을 요구한다. 이는 Source 입력 보조 Gate이며 `captured` 선언만으로 실제 다중 Pod 업무 안전이 확인됐다는 뜻이 아니다. [App 전환 근거](https://github.com/seokpan/seokpan-hybrid-app/blob/c12b3d15a4dd2c806fac4326a9eb30ed6e8a81b3/backend/docs/game-lifecycle-rollout.md)의 기존 writer 정지·Data 분류/보존·동일 Image/모드·2 Replica 실패 주입·Gateway/업무 수락 후 별도 활성화 변경으로 값을 확정한다. 미수락 조합을 일반 Rolling Update로 혼합하지 않는다. 실제 수락과 실패/제한은 App #4·GitOps #10의 새 Run에 기록한다.

## Backend HPA 후보 (정적 Preview)

[`activation-target/hpa.yaml`](activation-target/hpa.yaml)은 Backend HPA 후보이며 `activation-target/`에만 있다. 기본 Cloud Overlay와 Argo Sync 경로에는 포함하지 않는다. 설계 문서는 초기 HPA를 보류하고 고정 구성을 먼저 측정하도록 하므로(`03_DETAILED_DESIGN.md` §3-F), 이 선언은 활성화 결정이 아니라 부하테스트 시나리오 v3 §4의 HPA 후보값을 옮긴 Source 후보다. 시나리오 값은 검토·실측을 마친 한계값이 아니다. 시험용 임시 HPA는 B의 `tools/hpa-load`가 런타임에 만들고 지우며, 이 파일은 그와 별개의 Git 후보다. 영구 HPA 활성화는 시험 종료·원복 이후에 한다(시험 게이트가 다른 Backend HPA를 허용하지 않는다).

| 항목 | 값 | 비고 |
|---|---|---|
| 대상 | `Deployment/backend` | Backend만. Frontend는 3 Replica 고정 |
| `minReplicas` / `maxReplicas` | 3 / 6 | min 3은 시나리오 v3 후보(승인 목표 3과 같음), max 6은 시연용 후보. 시나리오의 max 10은 아래 연결 예산을 만족하지 못해 쓰지 않았다 |
| 메트릭 | CPU Utilization 60% | Backend `requests.cpu` 대비 |
| scaleUp | 안정화 0초, 60초당 +2 Pod 또는 +100% 중 큰 값 | `selectPolicy: Max` |
| scaleDown | 안정화 300초, 60초당 -1 Pod | 종료 유예 45초 동안 WebSocket 연결이 끊긴다 |

Backend Deployment에는 `replicas` 선언이 없다(HPA가 Scale을 소유). 기본 Cloud Render는 base의 `replicas: 0` 보류를 그대로 유지한다.

`tools/render_release.py`는 아래 충돌이 남아 있는 동안 Release를 막는다. 값을 임의로 바꾸지 않고 확인 후 해소한다.

| 충돌·미정 | 내용 | 해소 방법 |
|---|---|---|
| Backend `requests.cpu` 미설정 | 값이 없으면 CPU 사용률이 계산되지 않는다 | 실측 후 Cloud Overlay에서 지정 |
| DB 풀 미지정 | 미설정이면 라이브러리 기본값(엔진당 최대 15, Pod당 30)이다. min 3만으로도 `3×30+15=105`로 RDS `max_connections`(85 미만)를 넘는다. 풀 타임아웃 값도 시나리오에 아직 없다 | `SEOKPAN_DATABASE_POOL_SIZE`·`MAX_OVERFLOW`·`POOL_TIMEOUT_SECONDS`를 지정. 아래 계산 참고 |
| `captured` lifecycle 미정 | Backend가 2개 이상이면 필요하다 | App 전환 근거 수락 후 지정 |

DB 연결 계산: Pod당 최악 연결은 `2 × (pool + overflow)`(identity·game 엔진, 단일 프로세스)이고, `(maxReplicas + surge + 종료 중 Pod) × Pod당 연결 + 예약 연결 ≤ 0.9 × max_connections`여야 한다. 시나리오 v3 후보(엔진당 2+1 = Pod당 6, 예약 15, `max_connections` 85 가정)에서는 surge 1·종료 중 0이면 max 9가 상한이고 종료 중 1이면 8이다. max 6은 `(6+1+1)×6+15 = 63`으로 한도 76.5 안이다. 85는 실측값이 아니며 문서상 '85 미만'이므로 실측 후 다시 계산한다. 관리용 연결 수와 풀 값은 B/C가 정한다. 배포 이미지가 풀 환경변수를 실제로 소비하는지도 digest로 확인한다.

이 검사는 Source 검사이며 실제 지표 수집·Scale 동작·다중 Pod 업무 안전을 검증한 것이 아니다. 클러스터의 metrics API 제공 여부도 실제 Cluster에서 확인하기 전이다.

활성화 변경에서 함께 처리할 항목:

- **Replica 소유:** Application에 `/spec/replicas` `ignoreDifferences`와 `RespectIgnoreDifferences=true`를 둔다. Application은 `tools/cloud_platform_contract.py`가 생성하므로 이번 변경에는 포함하지 않았다.
- **플랫폼 소유 후속(이번 변경에 미포함):** ① `clusters/cloud/bootstrap/project.json`의 AppProject 허용 목록에 `autoscaling`/`HorizontalPodAutoscaler` 추가. `register-cloud-project.sh`가 이 파일의 SHA-256을 고정하고 기존 등록은 spec 동일성을 요구하므로 해시 개정과 이미 등록된 AppProject의 별도 반영이 필요하다. ② `tools/cloud_platform_contract.py`의 허용 종류와 observer Role. ③ `clusters/cloud/bootstrap/platform-next.py`의 컨트롤러 쓰기 권한 대조. 반영하면 `test_cloud_manifests.py`의 `PENDING_PLATFORM_WHITELIST`를 제거한다.

## 연결 입력과 Ownership

| 범위 | 현재 선언/소비 계약 | 실제 입력과 남은 Gate |
|---|---|---|
| Registry | Cloud Image는 ECR 대상 후보, Pull Secret 없음 | foundation `ecr_repository_urls`의 backend/frontend 값과 승인 Digest·플랫폼 Mapping. Classic 실제 Worker Role/프로젝트 Pull 정책 연결·캐시 없는 Pull·재생성 검증 |
| DB | `cloud` Profile, 정확한 RDS Host/Port/DB 허용 대상, Runtime URL 별도 Secret | C의 목적 GRANT/Schema·직접 TLS DNS/SAN·CA·`identity_svc`/`game_svc`와 App Lock/Driver 연결 검증 |
| Redis | 정확한 Primary Endpoint, `rediss://host:port/0`, 별도 AUTH Secret | C의 Redis Primary DNS·TLS/AUTH·CA 개정, Reader/평문/인증정보 포함 URL을 사용하지 않음 |
| 사용자 진입 | 동일 Host FE·`/api/v1`·`/ws/v1`, ClusterIP Service, Edge TLS와 HTTPS Redirect | ROSA 기본 Ingress Host·기본 신뢰 인증서·Route Admitted·CORS/Origin·HTTPS/WSS·Timeout/재접속 실측. lab의 Host/1h WS Timeout을 복사하지 않음 |
| Namespace/플랫폼 | 실제 Namespace는 입력 대기, [별도 플랫폼 계약 후보](../../../platform/cloud/README.md) 준비; 실제 Object/Label/RBAC/NP/Root/AppProject 적용 없음 | B/A/D의 Context·Namespace Owner·플랫폼/Argo 실효 권한/NetworkPolicy 인계. 초기 App 자동 Sync 보류·최초 수동 검증과 별도 Secret 공급 Gate |
| 자원/배치 | base의 SCC 관련 선언·Probes·쓰기 경로와 Rolling 유지, 목표 Preview에 AZ soft spread/Host preferred | Image 임의 UID·쓰기를 실제 확인, Requests/Limits·프로세스·identity/game 각 DB Pool·종료 중 연결과 플랫폼/UWM 부하를 함께 측정 |

Secret/CA 논리 이름과 Key는 공통 [App 계약](../../README.md)과 같다. Secret 값/Object와 공개 CA 공급은 별도 Owner가 맡는다. Migration 계정/Job·Redis StatefulSet·DB Pod·Namespace·Cluster RBAC를 Cloud App Overlay에 추가하지 않았다. AWS HA와 온프레미스 Restore Recovery는 별개 검증이다.

## 최신 Registry/CI 입력 대조

2026-10-02 조회한 [Infra PR #24](https://github.com/seokpan/seokpan-hybrid-infra/pull/24)의 HEAD `75e28d296b96b77fa6c1e3c2e642942d31457159` Source는 `seokpan-fnd-backend`/`seokpan-fnd-frontend` ECR 이름과 `ecr_repository_urls` Map을 선언한다. 이 이름 접두사는 정적 후보에 연결했지만 실제 Account/Region URL이나 생성 성공을 추정하지 않았다. 해당 PR은 Worker Pull 권한을 후속 범위로 명시하며, `validate` 보고는 실제 Apply/Node Pull 결과가 아니다.

PR 본문의 과거 untagged 7일/2개 정책 설명과 최신 Source의 단일 최근 N개 정책은 같은 사실로 섞지 않는다. 현재 HEAD Source에는 untagged/prefix별 만료 규칙이 없고 `registry_keep_image_count` 기본 50은 실물 Lifecycle Preview/Cost 확인 전이다. Cloud에서 사용 중인 Digest·Rollback 후보와 Image index 하위 Manifest가 보존되는지 별도로 확인해야 한다. CI Push User/Token을 Runtime Pull로 복사하지 않으며 [App #2](https://github.com/seokpan/seokpan-hybrid-app/issues/2)의 파이프라인 전환·Registry Mapping은 D/B 리뷰와 연결한다.

[App #2 최신 정합 기록](https://github.com/seokpan/seokpan-hybrid-app/issues/2#issuecomment-5951015819)의 A1 양 Registry Push/Harbor Scan·Smoke, C3 CI 삭제 권한 없음·N Preview 후 확정과 D의 방향 수신을 유지한다. 기존1차 대상 `promote_gitops.py`를 이 Cloud 후보에 그대로 실행하지 않으며, D의 새 CI 전환에서 대상 Repo와 `runtime/kustomization.yaml`의 고정 Digest 입력·Job/Folder·권한 경로를 같은 개정으로 정합한다. 새 Build/Scan/실제 Registry별 Digest와 Worker Pull은 아직 대기다.

## 검사와 다음 인계

```bash
kustomize build apps/overlays/cloud
kustomize build apps/overlays/cloud/activation-target
make test KUSTOMIZE=/path/to/kustomize
make release-manifest ENVIRONMENT=cloud OUTPUT=/separate/new/path/cloud.yaml KUSTOMIZE=/path/to/kustomize
```

고정 Kustomize v5.7.1의 기본/목표 Preview Build와 경계 검사는 정적 확인이다. 현재 `release-manifest`는 실제 Kustomize 출력의 미해결 입력/실행 보류를 발견해 실패하며 출력 파일을 만들지 않는다. 이 Gate는 실제 Source/Digest·Secret·Runtime 수락을 대신하지 않는다. 기존 Release 파일을 덮어쓰지 않는다.

남은 순서는 실제 ECR/DB/Redis/Ingress/Namespace·Image/Secret/CA 개정 인계→1 Replica 기동/자원·DB Pool·업무 안전 확인→Cloud 3 Replica 목표 연결·처리/배치/종료·장애 검증이다. Root/Secret/Pull/Cost/Window Gate를 이 정적 후보가 통과했다고 표현하지 않는다. Cloud Apply, Argo Sync, AWS 생성/삭제·Owner 변경은 이번 작업에서 수행하지 않았다.
