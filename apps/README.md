# App base와 환경별 입력 대기 구현

목적은 D의 [h-gitops Issue #5](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5)에 실제 Kustomize 선언을 인계하고, C의 Offline Recovery에서 소비할 App·새 Redis Source와 Secret/CA 경계를 마련하는 것이다. RTO/RPO 숫자를 정하거나 실제 복구 결과를 대신하는 자료가 아니다.

현재 결과는 **입력 대기 Source 후보**이며 실제 Kustomize Build·선언 검사는 Source CI로 확인한다. App 연결 수정 Image, 환경별 대상·Secret·CA와 실제 배포 검증이 남았다. `INPUT_REQUIRED`와 예약 `.invalid` 주소는 실제 값이 아니며, FE/BE와 새 Recovery Redis 모두 `replicas: 0`을 유지해 기동을 보류했다. 이 Render를 Apply/Sync하거나 Recovery Bundle의 검증본으로 사용하지 않는다. 변경 전 1차 자산은 수정하지 않는다. `make preview`는 진단용이고 `make release-manifest`는 미해결 입력/기동 보류가 있으면 출력 파일 생성을 거부한다.

## 출처와 실제 변경

원 lab 자료는 D가 인계한 `reference/ocp-lab-original`의 전체 SHA `259e73b0fac1af40f7bb7b43bd1982410d1df150`이다. 원문은 참고 Branch에 보존하고 main에 중복 이관하지 않는다. 원 lab Render 성공은 새 Image/연결 계약의 lab 성공이 아니다.

- `base`: FE/BE Deployment·Service·비민감 ConfigMap. Source의 8080/8000과 Health URI, `/tmp` 쓰기 경로, 종료 유예를 연결했다. 고정 UID/GID·Registry Pull Secret·lab CA·Host·hostAliases·Redis StatefulSet은 공통 선언에 넣지 않았다.
- `overlays/lab`: #5의 `seokpan-argotest`를 대상으로 하는 후보. FE/API/WSS의 동일 Host·Edge TLS Route와 `lab` 연결 Profile을 묶었다. 기존 `seokpan-app`이나 Namespace 객체·managed-by Label을 수정하지 않는다. Registry/인증 방식은 실제 Image 인계에서 확정한다.
- `overlays/recovery`: 격리 전용 VM의 **직접 DB TLS** 대상 설정과 **새 Recovery Redis TLS/AUTH**의 App 연결·별도 StatefulSet·내부 Service·비민감 설정 후보. Harbor Pull Secret 참조는 이 Overlay에만 있다. B의 Redis 선언 배선은 포함했으며 C의 실제 버전·저장소·영속성·자원·CA/AUTH 공급과 실행 검증은 남았다. 기존 1차 Redis와 Cloud Redis Runtime을 재사용·복제하지 않는다. Recovery 진입 경로는 실제 플랫폼·Host/TLS 확인 전 선언하지 않았다.

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
| `recovery-harbor-pull` Secret | Recovery FE/BE/Redis Pull | 장애 전에 로컬에서 사용할 Harbor 자격·CA·Image Mapping |
| `runtime.env` | 환경별 비민감 ConfigMap | 승인 대상·허용 Origin과 실제 Port/Schema를 일치시킨 개정 |
| Image Mapping | FE/BE와 Recovery Redis 컨테이너 | 수정 App Commit→Build/Scan→승인 Digest와 C/D의 Redis Engine/TLS·임의 UID 호환성, Registry별 실제 Pull |

Migration 목적 인증정보는 일반 App Deployment에 넣지 않으며 자동 Job도 포함하지 않는다. Schema/대상/Image/승인 Ref를 확인한 별도 단일 실행이 필요하다. Runtime 계정 분리, Data Restore/Cutover는 C의 작업 경계를 유지한다.

### 새 Recovery Redis Source와 C/A/D의 실제 입력

`redis.yaml`의 논리 이름은 `recovery-redis`이며 격리 Namespace 안의 Headless `ClusterIP` Service만 선언한다. Backend의 `rediss://recovery-redis.<격리 Namespace>.svc:6379/0`과 예상 Host를 함께 바꿔 같은 대상을 검증한다. 체크인 Namespace `recovery-input-required`는 승인된 실제 Namespace가 아니다. 다른 환경·1차 Redis 주소를 연결하거나 `FLUSHALL`로 초기화하는 절차는 넣지 않았다.

`redis.conf`는 평문 Port를 `0`으로 끄고 TLS `6379`, 서버 인증서·Key·CA 파일, TLS 1.2/1.3을 선언한다. App은 Client Certificate를 공급하지 않으므로 `tls-auth-clients no`로 맞추고 별도 AUTH를 사용한다. 이는 무인증 허용이 아니다. C가 공급한 보호 AUTH 설정의 실제 `requirepass`가 비어 있지 않고 Backend의 `backend-redis-runtime` Token과 같은 승인 개정인지 실행 전에 검증해야 한다. 비민감 ConfigMap에 Password/ACL 값은 넣지 않으며 Redis 실행 인자는 설정 파일 경로뿐이다. Source 도구는 실제 Secret 내용을 읽거나 인증 성공을 확인하지 않는다.

| 외부 입력 | Source 소비 인터페이스 | C/A/D가 확정·검증할 조건 |
|---|---|---|
| `recovery-redis-server-tls` Secret | `tls.crt`, `tls.key`, `ca.crt` 읽기 전용 Mount | 새 Service DNS/SAN·수명·Key 보호와 Backend CA의 일치 |
| `recovery-redis-server-auth` Secret | `redis-auth.conf` 읽기 전용 Include | 비어 있지 않은 `requirepass`, Backend Token과 승인 개정 일치, 무인증/평문 인증 부재 |
| `recovery-redis-runtime-input-required` 외부 ConfigMap | `redis-runtime.conf` 읽기 전용 Include | 실제 Redis Engine 버전에 맞는 `dir /data`와 쓰기 경로·영속성·메모리 정책. AUTH 값은 이 ConfigMap에 넣지 않음 |
| `recovery-redis-storage-input-required` 외부 Volume 참조 | `/data` 쓰기 Mount | 새 격리 Runtime용 실제 Volume·빈 초기 상태·임의 UID 쓰기 권한·용량 |
| Local Harbor Redis Digest | `redis-server /etc/seokpan/redis/redis.conf` | 승인 Engine/TLS Binary·임의 UID·읽기 전용 RootFS와 필요한 쓰기 경로·실측 자원·상태 확인 방법 |

현재 PVC 이름은 **입력 대기 Volume 인터페이스**이며 PVC·StorageClass·영속성 정책 채택이 아니다. Source에 Namespace/Secret/PVC 객체·`volumeClaimTemplates`를 만들지 않는다. C/A가 승인한 다른 새 Volume 방식으로 교체할 수 있고 Renderer는 PVC만 강제하지 않는다. 이름만으로 실제 데이터가 비어 있거나 1차 자산과 격리됐음을 증명하지 않는다. AOF·`maxmemory`·Resource Requests/Limits·Redis 버전·최종 Volume 정책은 선택하지 않았다.

Runtime/보호 AUTH Include를 먼저 읽고 공개 TLS 설정을 뒤에 두어 그 Include가 평문 Port/TLS 설정을 덮어쓰지 못하게 한다. Renderer는 Redis와 같이 Directive 이름의 대소문자를 구분하지 않으며 공개 파일에 허용한 Transport/Process 설정의 추가 중복·AUTH·외부 복제 지시를 거부한다. C는 외부 Include 내용에도 인증·복제·쓰기 정책의 모순이 없는지 검토한다. Secret 파일 Mount는 읽기 전용이며 고정 UID/GID·`fsGroup`을 지정하지 않았다. 실제 SCC·임의 UID에서 Key/설정 읽기 권한과 `/data` 쓰기 권한이 맞는지는 C/A/D의 실행 검증이다. Secret를 읽을 수 있다는 선언이 실제 파일 권한 검증은 아니다.

### 설정·Secret·CA 개정의 소비자 반영

공통 base의 `runtime.env`와 Overlay의 `runtime.env`를 논리 이름 `backend-config`의 ConfigMap Generator로 합친다. 실제 Render 이름은 내용 Hash가 붙은 `backend-config-<hash>`이고 Kustomize가 Backend의 `envFrom` 참조도 같은 이름으로 바꾼다. 대상/Origin/Profile 등 비민감 설정을 바꾸면 Backend PodTemplate도 달라져 승인한 Sync/Apply의 Rolling Update에 연결된다. 공통 base 단독 Build도 입력 대기 자료이며 직접 배포 대상이 아니다. 기존 생성 ConfigMap의 정리는 검토한 Prune/삭제 절차를 따르며 이 변경에서 자동 Prune를 켜지 않는다.

외부 공급 Secret `backend-db-runtime`·`backend-redis-runtime`과 CA ConfigMap `backend-database-ca`·`backend-redis-ca`는 고정 논리 참조를 유지한다. 값/Object 교체만으로 기존 Pod의 환경변수나 이미 조립한 TLS Context/Pool이 갱신됐다고 판단하지 않는다. App 이관 묶음의 `backend/docs/hybrid-connections.md` 환경 경계와 같이 새 Config/Secret/CA 개정·허용 대상 조합을 기록하고, 승인한 Backend Pod 재기동과 재접속·양성/음성 연결·업무 검증을 수행한다. 재기동 의도는 공개 가능한 개정 ID의 PodTemplate 변경 등 승인된 배포 변경으로 연결하며 Secret 값/평문 Hash를 Git에 넣지 않는다. 공급 코드·Object와 실제 재기동/회수 성공은 해당 Owner의 후속 실행이며 이 PR에서 수행하지 않는다.

Redis 비민감 설정도 `recovery-redis-config-<hash>`로 생성되고 StatefulSet의 ConfigMap Volume 참조가 같은 이름으로 변환된다. 외부 Redis AUTH/TLS/Runtime 설정은 고정 논리 참조이므로 실제 공급 개정만 바뀌어도 기존 Redis가 새 설정을 읽었다고 가정하지 않는다. C의 검토·승인 재기동과 Backend Token/CA 개정 및 재접속 검증을 같은 조합으로 연결한다. 자동 Prune나 자동 재기동 Controller는 추가하지 않았다.

## Build와 검사

검사 도구는 upstream `kubernetes-sigs/kustomize`의 고정 Release **v5.7.1**이다. 이 도구를 최종 실행 환경과 Bundle에 보존할지는 A/C/D의 실제 도구 인계에서 확인한다. 이번 검사에는 Linux amd64 Release의 공개 SHA256 `ea375e7372f9aa029129d4b2d16c66b7750b7f1213c4f66f910d981c895818d8`을 대조했다.

```bash
kustomize version
kustomize build apps/base
kustomize build apps/overlays/lab
kustomize build apps/overlays/recovery
KUSTOMIZE=/path/to/kustomize python3 -m unittest discover -s tools -p 'test_app_manifests.py' -v
make preview ENVIRONMENT=lab KUSTOMIZE=/path/to/kustomize
RECOVERY_NAMESPACE="$REVIEWED_RECOVERY_NAMESPACE" RECOVERY_REGISTRY="$REVIEWED_RECOVERY_REGISTRY" \
  make release-manifest ENVIRONMENT=recovery OUTPUT=/separate/path/recovery.yaml KUSTOMIZE=/path/to/kustomize
```

테스트는 PyYAML로 **실제 Kustomize 출력**을 읽으며 별도 Renderer가 아니다. Build/객체 충돌, 새 Redis를 포함한 기동 보류, Secret/CA·TLS/AUTH 참조, SCC 관련 선언, Pull 경계, Probe/Port와 동일 Host Route를 검사한다. 의미 검사·출력 보존을 고립해 검증하는 제어 Fixture 검사도 구분해 포함한다. Fixture 성공은 실제 Overlay Build 결과가 아니다. 실제 SCC Admission·임의 UID 파일 권한·Image Pull·DB/Redis 연결·업무·Offline 복구 시간은 실행하지 않았다.

설정 변경 회귀검사는 두 Overlay의 격리 사본에서 DB 대상 설정 하나를 바꾸고 실제 Kustomize로 전후 Build한다. 생성 ConfigMap 이름과 Backend PodTemplate의 참조가 함께 바뀌고 Frontend·외부 CA 참조가 유지되는지 확인한다. 이는 선언의 Rollout 유발 연결 검사이며 실제 Pod 재기동 성공은 별도다.

`tools/render_release.py`는 **Python과 PyYAML**로 실제 Kustomize v5.7.1의 출력에서 미해결 입력을 확인한다. Source CI의 Python 3.12/PyYAML 6.0.2와 Kustomize·실행 의존성을 오프라인에서 사용할지는 A/C/D가 장애 전 실제 도구 인계에서 검증·보존한다. `INPUT_REQUIRED`, 예약 `.invalid` 주소, `input-required` 표기, `replicas: 0` 또는 빈 출력이 있으면 실패하고 결과 파일을 만들지 않는다.

Recovery는 별도로 공급한 승인 Namespace와 Local Harbor Host(`RECOVERY_NAMESPACE`/`RECOVERY_REGISTRY` 또는 `--recovery-namespace`/`--recovery-registry`)를 요구한다. 위 예의 `REVIEWED_RECOVERY_NAMESPACE`/`REVIEWED_RECOVERY_REGISTRY`도 해당 Owner의 실제 승인 값을 먼저 받아 지정하는 입력이며 샘플 값으로 승인되지 않는다. 렌더된 App/새 Redis의 Namespace·단일 Replica·내부 Service/Backend 대상 일치, TLS-only 설정·보호 AUTH Include 순서·외부 AUTH/CA 파일 참조와 읽기 전용 Mount, Local Harbor Digest 형식, 다른 Owner의 Namespace/Secret/PVC를 생성하지 않는 경계를 검사한다. Backend는 필수 ConfigMap 단일 참조로만 비민감 설정을 공급하며 추가 `envFrom`·중복 `env` 이름·생성 ConfigMap 키의 직접 환경변수 Override도 거부한다. 공급한 이름·Digest 형식의 일치는 실제 Namespace 격리·Harbor/Image 승인·Secret 내용/AUTH 일치·TLS 연결·빈 저장소를 증명하지 않는다.

입력 검사를 통과해도 기존 파일·Symlink는 덮어쓰지 않으며 새 출력 경로가 필요하다. 출력 파일은 기존 경로와 충돌하지 않을 때만 원자적으로 생성하므로 이전 검증 Artifact가 보존된다. 과거 파일을 이번 성공으로 취급하지 않는다. 통과는 이 Source 입력 검사의 통과이며 Context·Runtime/업무·Bundle 수락까지 증명하지 않는다. Apply/Sync와 외부 신규 조회는 하지 않는다.

## 활성화 전에 남은 작업

1. B 수정 Source와 D Build/Scan 결과의 승인 FE/BE Digest, C/D의 호환 Redis Engine/Local Image Digest를 받는다. 실제 Registry와 환경별 Pull 방식을 Overlay에 고정한다.
2. C/D에게 lab의 TLS/AUTH Redis 대상·Secret/CA와 DB TLS·Schema를 받는다. C/A에게 격리 Recovery Namespace/VM·DB·새 Redis·플랫폼·저장소/자원과 진입 경로를 받는다. `runtime.env`·Route·CA/Secret 개정이 같은 조합인지 대조한다.
3. 실측 기반 Requests/Limits와 실제 Image의 임의 UID/쓰기 경로를 검증한다. 입력과 Source/Digest/Config/Schema 조합을 확인한 뒤 별도 변경으로 기동 보류를 해제한다. lab 초기 각 1, Recovery 초기 각 1로 시험하되 이번 0은 승인 Replica 변경이 아니라 미준비 Source의 실행 보류다. 단일 Replica에 PDB를 붙여 Drain을 막지 않는다.
4. D #5의 수동 Sync·Health와 #6의 수정 Image/양성·음성 연결·업무 검증을 받는다. Namespace/Prune/Finalizer/삭제 정책은 이번 변경에서 수정하지 않았다.
5. Recovery 접속·새 Redis 상태 처리·완료 기록/신규 게임 업무를 확인한 Render·Image·Config/CA·Secret 논리 참조·도구를 장애 전에 로컬에 보존한다. 전체 Bundle 작성·C의 수락과 D의 기존 실제 Run은 아직 남았다. 탐지부터 업무 재개, Backup Data 시각 근거와 최신성을 측정한다. [h-docs PR #30](https://github.com/seokpan/seokpan-hybrid-docs/pull/30)의 main 반영으로 현재 설계 요구사항은 **RTO 10분·영속 DB RPO 30분·운영 중 Portable Backup 15분**이다. 선택 근거·기능/접속 범위·미달 처리와 실행 Gate는 [03 §3-I.14.5](https://github.com/seokpan/seokpan-hybrid-docs/blob/ab116463fd1f1a75d54e734c3c1c99cd098f639d/design/03_DETAILED_DESIGN.md#recovery-design-decision-20261005)를 따른다. 예약 주기만으로 RPO를 보장하지 않으며 실제 성공 Data 간격·로컬 완성 지연·시점 불확실성 및 실제 사용 사본의 나이를 검증한다. 이전 30분·90분·1시간은 승인 이력이며 기존 Run을 소급 변경하지 않는다. 로컬 합성 부분 Run PASS를 실제 전체 RTO/RPO·최종 T18 달성으로 확대하지 않는다.

Cloud 선언 후보는 [cloud](overlays/cloud/README.md)에 별도 후속 변경으로 연결한다. 기본 Render는 기동 보류 0이며 승인된 FE/BE 각 3 Replica·PDB minAvailable 2·AZ soft spread는 분리된 목표 Preview다. 실제 Source 상태 공유·1 Replica 실측·Pool/자원·입력/권한·Runtime 검증 뒤 리뷰한 변경으로 활성화한다. Cloud Source Build를 ROSA 생성·배포 완료로 표시하지 않는다.
