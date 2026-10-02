# App base와 lab / Recovery 입력 대기 구현

목적은 D의 [GitOps #5](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5)에 실제 Kustomize 선언을 인계하고, C의 Offline Recovery에서 소비할 App 설정·Secret/CA 경계를 마련하는 것이다. RTO/RPO 숫자를 정하거나 실제 복구 결과를 대신하는 자료가 아니다.

현재 결과는 **실제 Kustomize Build를 통과한 Source 후보**다. App 연결 수정 Image, 환경별 대상·Secret·CA와 실제 배포 검증이 남았다. `INPUT_REQUIRED`와 예약 `.invalid` 주소는 실제 값이 아니며, FE/BE `replicas: 0`을 유지해 기동을 보류했다. 이 Render를 Apply/Sync하거나 Recovery Bundle의 검증본으로 사용하지 않는다. 변경 전 1차 자산은 수정하지 않는다. `make preview`는 진단용이고 `make release-manifest`는 미해결 입력/기동 보류가 있으면 출력 파일 생성을 거부한다.

## 출처와 실제 변경

원 lab 자료는 D가 인계한 `reference/ocp-lab-original`의 전체 SHA `259e73b0fac1af40f7bb7b43bd1982410d1df150`이다. 원문은 참고 Branch에 보존하고 main에 중복 이관하지 않는다. 원 lab Render 성공은 새 Image/연결 계약의 lab 성공이 아니다.

- `base`: FE/BE Deployment·Service·비민감 ConfigMap. Source의 8080/8000과 Health URI, `/tmp` 쓰기 경로, 종료 유예를 연결했다. 고정 UID/GID·Registry Pull Secret·lab CA·Host·hostAliases·Redis StatefulSet은 공통 선언에 넣지 않았다.
- `overlays/lab`: #5의 `seokpan-argotest`를 대상으로 하는 후보. FE/API/WSS의 동일 Host·Edge TLS Route와 `lab` 연결 Profile을 묶었다. 기존 `seokpan-app`이나 Namespace 객체·managed-by Label을 수정하지 않는다. Registry/인증 방식은 실제 Image 인계에서 확정한다.
- `overlays/recovery`: 격리 전용 VM의 **직접 DB TLS**와 **새 Recovery Redis TLS/AUTH** 대상 설정을 소비하는 App 후보. Harbor Pull Secret 참조는 이 Overlay에만 있다. 새 Redis 배포·복원·CA/AUTH 공급은 C 입력/작업이 남았으며 기존 1차 Redis를 재사용하지 않는다. Recovery 진입 경로는 실제 플랫폼·Host/TLS 확인 전 선언하지 않았다.

Redis URL은 `rediss://<host>:<port>/0`이며 인증정보를 넣지 않는다. 별도 `SEOKPAN_REDIS_AUTH_TOKEN` Secret과 CA/Hostname 검증을 사용한다. 과거 lab의 `redis://`·hostAliases·10/31 만료 CA·기존 이미지 Digest를 새로운 연결 계약에 복사하지 않았다. 현재 세부 변수는 App 이관 묶음의 연결 Source 개정과 대조한다.

45초 종료 유예·Probe 간격/제한·lab WS `timeout-tunnel: 1h`는 원 Source/lab에서 출발한 **미측정 초기 후보**이며 Runtime 적합성 판정이 아니다. Requests/Limits도 아직 실측 입력이 없어 넣지 않았다. 최종 활성화 전에 D의 이미지/임의 UID·Health·종료/재접속·자원 측정과 같은 개정으로 조정한다.

## 공급 계약

두 Overlay는 아래 논리 이름을 각 대상 Namespace에서 소비한다. 값/Object 공급은 별도 Owner 책임이며 이 저장소에는 Secret 값을 기록하지 않는다.

| 입력 | 소비 대상 | 남은 확인 |
|---|---|---|
| `backend-db-runtime` Secret | `SEOKPAN_IDENTITY_DATABASE_URL`, `SEOKPAN_GAME_DATABASE_URL` Key | 환경별 실제 Host/Port/DB와 `identity_svc`/`game_svc`, 직접 TLS·GRANT·Schema |
| `backend-redis-runtime` Secret | `SEOKPAN_REDIS_AUTH_TOKEN` Key | 별도 AUTH 개정과 정확한 대상·새 Recovery Runtime |
| `backend-database-ca` ConfigMap | `ca.crt`, `/etc/seokpan/database-ca/ca.crt` | 해당 DB DNS/SAN·CA·수명·승인 공급본 |
| `backend-redis-ca` ConfigMap | `ca.crt`, `/etc/seokpan/redis-ca/ca.crt` | 해당 Redis TLS DNS/SAN·CA·수명·승인 공급본 |
| `recovery-harbor-pull` Secret | Recovery FE/BE Pull | 장애 전에 로컬에서 사용할 Harbor 자격·CA·Image Mapping |
| `runtime.env` | 환경별 비민감 ConfigMap | 승인 대상·허용 Origin과 실제 Port/Schema를 일치시킨 개정 |
| Image Mapping | FE/BE 컨테이너 | 수정 App Commit→Build/Scan→승인 Digest, Registry별 실제 Pull |

Migration 목적 인증정보는 일반 App Deployment에 넣지 않으며 자동 Job도 포함하지 않는다. Schema/대상/Image/승인 Ref를 확인한 별도 단일 실행이 필요하다. Runtime 계정 분리, Data Restore/Cutover는 C의 작업 경계를 유지한다.

### 설정·Secret·CA 개정의 소비자 반영

공통 base의 `runtime.env`와 Overlay의 `runtime.env`를 논리 이름 `backend-config`의 ConfigMap Generator로 합친다. 실제 Render 이름은 내용 Hash가 붙은 `backend-config-<hash>`이고 Kustomize가 Backend의 `envFrom` 참조도 같은 이름으로 바꾼다. 대상/Origin/Profile 등 비민감 설정을 바꾸면 Backend PodTemplate도 달라져 승인한 Sync/Apply의 Rolling Update에 연결된다. 공통 base 단독 Build도 입력 대기 자료이며 직접 배포 대상이 아니다. 기존 생성 ConfigMap의 정리는 검토한 Prune/삭제 절차를 따르며 이 변경에서 자동 Prune를 켜지 않는다.

외부 공급 Secret `backend-db-runtime`·`backend-redis-runtime`과 CA ConfigMap `backend-database-ca`·`backend-redis-ca`는 고정 논리 참조를 유지한다. 값/Object 교체만으로 기존 Pod의 환경변수나 이미 조립한 TLS Context/Pool이 갱신됐다고 판단하지 않는다. App 이관 묶음의 `backend/docs/hybrid-connections.md` 환경 경계와 같이 새 Config/Secret/CA 개정·허용 대상 조합을 기록하고, 승인한 Backend Pod 재기동과 재접속·양성/음성 연결·업무 검증을 수행한다. 재기동 의도는 공개 가능한 개정 ID의 PodTemplate 변경 등 승인된 배포 변경으로 연결하며 Secret 값/평문 Hash를 Git에 넣지 않는다. 공급 코드·Object와 실제 재기동/회수 성공은 해당 Owner의 후속 실행이며 이 PR에서 수행하지 않는다.

## Build와 검사

검사 도구는 upstream `kubernetes-sigs/kustomize`의 고정 Release **v5.7.1**이다. 이 도구를 최종 실행 환경과 Bundle에 보존할지는 A/C/D의 실제 도구 인계에서 확인한다. 이번 검사에는 Linux amd64 Release의 공개 SHA256 `ea375e7372f9aa029129d4b2d16c66b7750b7f1213c4f66f910d981c895818d8`을 대조했다.

```bash
kustomize version
kustomize build apps/base
kustomize build apps/overlays/lab
kustomize build apps/overlays/recovery
KUSTOMIZE=/path/to/kustomize python3 -m unittest discover -s tools -p 'test_app_manifests.py' -v
make preview ENVIRONMENT=lab KUSTOMIZE=/path/to/kustomize
make release-manifest ENVIRONMENT=recovery OUTPUT=/separate/path/recovery.yaml KUSTOMIZE=/path/to/kustomize
```

테스트는 PyYAML로 **실제 Kustomize 출력**을 읽으며 별도 Renderer가 아니다. Build/객체 충돌, 기동 보류, Secret/CA·TLS/AUTH 참조, SCC 관련 선언, Pull 경계, Probe/Port와 동일 Host Route를 검사한다. 실제 SCC Admission·임의 UID 파일 권한·Image Pull·DB/Redis 연결·업무·Offline 복구 시간은 실행하지 않았다.

설정 변경 회귀검사는 두 Overlay의 격리 사본에서 DB 대상 설정 하나를 바꾸고 실제 Kustomize로 전후 Build한다. 생성 ConfigMap 이름과 Backend PodTemplate의 참조가 함께 바뀌고 Frontend·외부 CA 참조가 유지되는지 확인한다. 이는 선언의 Rollout 유발 연결 검사이며 실제 Pod 재기동 성공은 별도다.

`tools/render_release.py`는 Python 표준 라이브러리만으로 실제 Kustomize v5.7.1의 출력에서 미해결 입력을 확인한다. `INPUT_REQUIRED`, 예약 `.invalid` 주소, `input-required` 표기, `replicas: 0` 또는 빈 출력이 있으면 실패하고 결과 파일을 만들지 않는다. 입력 검사를 통과해도 기존 파일·Symlink는 덮어쓰지 않으며 새 출력 경로가 필요하다. 출력 파일은 기존 경로와 충돌하지 않을 때만 원자적으로 생성하므로 이전 검증 Artifact가 보존된다. 과거 파일을 이번 성공으로 취급하지 않는다. 통과는 이 Source 입력 검사의 통과이며 Secret 존재·TLS 연결·Digest 승인·Context·Runtime/업무·Bundle 수락까지 증명하지 않는다. Apply/Sync와 외부 신규 조회는 하지 않는다.

## 활성화 전에 남은 작업

1. B 수정 Source와 D Build/Scan 결과의 승인 FE/BE Digest를 받는다. 실제 Registry와 환경별 Pull 방식을 Overlay에 고정한다.
2. C/D에게 lab의 TLS/AUTH Redis 대상·Secret/CA와 DB TLS·Schema를 받는다. C/A에게 격리 Recovery Namespace/VM·DB·새 Redis·플랫폼·저장소/자원과 진입 경로를 받는다. `runtime.env`·Route·CA/Secret 개정이 같은 조합인지 대조한다.
3. 실측 기반 Requests/Limits와 실제 Image의 임의 UID/쓰기 경로를 검증한다. 입력과 Source/Digest/Config/Schema 조합을 확인한 뒤 별도 변경으로 기동 보류를 해제한다. lab 초기 각 1, Recovery 초기 각 1로 시험하되 이번 0은 승인 Replica 변경이 아니라 미준비 Source의 실행 보류다. 단일 Replica에 PDB를 붙여 Drain을 막지 않는다.
4. D #5의 수동 Sync·Health와 #6의 수정 Image/양성·음성 연결·업무 검증을 받는다. Namespace/Prune/Finalizer/삭제 정책은 이번 변경에서 수정하지 않았다.
5. Recovery 접속·새 Redis 상태 처리·완료 기록/신규 게임 업무를 확인한 Render·Image·Config/CA·Secret 논리 참조·도구를 장애 전에 로컬에 보존한다. C의 Bundle 수락과 D의 기존 실제 Run에 연결해 탐지부터 업무 재개, Backup Data 시각 근거와 최신성을 측정한다. RTO 30분/RPO 90분/1시간 Backup은 기존 공식 목표를 유지하며 강화 수치는 실측·업무 영향·팀 부담 판단 전 확정하지 않는다.

Cloud Overlay의 ECR·FE/BE 3 Replica·PDB minAvailable 2·AZ soft spread/자원 검증은 후속 범위다. Cloud 없는 이번 Build 결과를 ROSA 배포 완료로 표시하지 않는다.
