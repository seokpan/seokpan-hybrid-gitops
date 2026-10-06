# OCP Source 인계 카드 — 병합 후 다음 실행 (2026-10-05, Image 입력 2026-10-06 갱신)

**목적:** 병합된 App와 GitOps 선언을 D의 실제 OCP 배포와 C의 Data 검토에 연결한다. 이 카드는 Source 제출·입력 수신·실제 실행을 따로 표시한다. 상세 절차는 [OCP 최초 배포 안내](OCP_FIRST_DEPLOYMENT.md), B 원본은 [GitOps #10](https://github.com/seokpan/seokpan-hybrid-gitops/issues/10), 개인 상위는 [Docs #21](https://github.com/seokpan/seokpan-hybrid-docs/issues/21)이다.

## 현재 후속 — 2026-10-06 Registry 경로 미확보

[D의 GitOps #14 보고](https://github.com/seokpan/seokpan-hybrid-gitops/issues/14#issuecomment-6011344271)를 수신했다. lab과 Harbor 사이의 망 연결이 없어 bastion 요청의 SYN이 Harbor에 도착하지 않았고, 임시 라우트는 원복했다고 보고했다. **현재 Harbor로 Pod를 기동할 경로는 확보되지 않았다.** Node 직접 접근은 미검사다. Context/Controller·대상 Namespace Active/managed-by 일치·기존 Application 없음은 D의 조회 범위로 구분하며, B의 권한·공유 Owner·사용창·4조 공지/사용 수락은 남았다. Application이 없다고 기존 FE/BE 등 배포 객체도 없다고 판단하지 않는다.

먼저 할 수 있는 것은 **권한·단일 Owner·공유 사용을 수락한 제한 Project/Application 등록과, 필요한 경우 Root의 수동 Sync**다. Root가 Child Application을 등록해도 App 자동 Sync는 없다. 현재 lab 8객체 전체의 0 Replica Sync 또는 진단 ZIP Apply는 허용한 실행 방법이 아니다. Service·Route·ConfigMap도 실제로 바뀌며, 기존 동명 Deployment를 0으로 줄이면 중단될 수 있다. 실제 8객체 목록·Owner·selector·Route Host·Diff를 먼저 확인한다. 현재 Release 검사의 0 Replica·미입력 거부는 유지한다.

망 Owner의 연결 지원 확인과 **이미 있는 공통 Registry 후보 조사**를 병행한다. 후보의 복사 호스트/lab Node 접근·사용 Owner·TLS·인증과 승인 Image의 내용/플랫폼·대상 Index Digest를 확인한다. 대상이 정해지기 전 lab Image·Cloud ECR·Recovery Harbor 선언은 바꾸지 않는다. ROSA 준비도 별도 진행한다. 판단·담당·기존 절차와의 관계는 [최초 배포 안내의 현재 확인](OCP_FIRST_DEPLOYMENT.md#2026-10-06-현재-확인--registry-경로와-먼저-할-수-있는-준비)에 있다. 공급은 #14, B 수신/선언 대조는 #10, 실제 등록/Sync는 #5, 접속/업무는 #6에 기록한다. 아직 Apply/Sync·새 실행 Run·Runtime PASS는 없다.

### 추가 Data 수신 상태 — 전체 v2 파일 수신

C의 `data-contract-v2-20261006.md` **§0–7 전체/§6 B 요청5개**를 받았다(SHA256 `8679c46b80b1fe93b2083aea584a47e65cf4882d0c976a7cd9218159fe8f4616`, 원본 불변). Endpoint 직접 사용·TLS·Redis 별도Token·CA 공급 순서·환경별 자격 분리·Schema 확인/1회 실행·300초 조건을 수락한다. 원 #19 공개 코멘트에도 전체 계약 게시를 확인했으며 계약 미제공 대기는 해소됐다. 실제 Endpoint/CA/자격 공급·Image/DB Revision·Redis 지원 범위/호환 전략·실제7.1 시험과 연결 예산은 별도다.

Source Alembic head는 인계46e와 현재2003에서 `20260902_0002`로 확인했다. 실제 Image 자산/DB `current`를 실행한 결과는 아니다. §2.9 논리 참조6개는 확인했고 공개 CA의 Source ConfigMap과 계약 CA Secret 명칭/Kind를 C/B가 맞춘다. Endpoint/CNAME·세션 시간대 미지정은 수락, Runtime SQL Host VPC/20는 Worker 송신 주소/SG/SQL 매칭의 실제 확인을 조건으로 수락한다. Migration은 suspended `current`/300초 유지, D의 lab Schema 판단과 같은 Image·목적 자격을 받은 뒤 단일 실행한다. lab DB는 재시작·삭제하지 않는다.

Backend 연결 예산은 아직 미수락이다. Cloud 후보3·surge1, Runtime Engine2·기본 Pool5+10·Process1 가정에서 정상2=60/교체3=90, Cloud 정상3=90/교체4=120의 후보 상한이다. overflow5로 줄여도 교체4×20+예약10=90이며, surge0/unavailable0 조합도 허용되지 않는다. C 실제 max_connections·예약과 B의 정상/교체/종료 연결 수·Pool·HA를 맞춘 뒤 활성화한다. 현재 Source replicas0은 유지하며 Source 후보를 실제 Pod 상태로 쓰지 않는다. [최초 배포 안내의 B 수락 표](OCP_FIRST_DEPLOYMENT.md#추가-data-인계--전체-v2-파일-수신과-b-수락-범위), 원 응답 Infra#19/App#1, 시험 GitOps#6, 선언#10을 따른다.

**Redis 지원 범위 추가 확인:** [AWS 공식 Engine 설명](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/engine-versions.html)은 ElastiCache Redis OSS7.1을 OSS7.0 호환으로 설명한다. 반면 정확한 [redis-py v8.1.0 지원표](https://github.com/redis/redis-py/blob/v8.1.0/README.md)는 6.0 이상 Client의 지원 범위를 Redis7.2 이상으로 명시한다. 따라서 C의7.1 선택을 접수했지만 B의 App 호환 수락은 지원 범위/사용 전략 합의와 실제 대상 시험 후다. 실제 동작 불가능을 단정하거나 Driver/Engine/Protocol을 임의 변경하지 않는다. 기존 Redis7.2.4 시험과 현재 전체 Lua/명령·TLS/AUTH·RESP 동작을 구분한다. 이 차이는 Cloud App 조합 수락의 조건이며 제한 제어 등록/ROSA 첫 Plan을 막는 새 일괄 조건이 아니다.

### D lab 입력 추가 수신

[D의 #19 응답](https://github.com/seokpan/seokpan-hybrid-infra/issues/19#issuecomment-6012181426)에서 DB DNS `mariadb.seokpan-app.svc`·인증서 SAN·10/31 만료와 deadline300초 수락을 받았다. 실제 CA bytes/Hash·목적 자격·Schema·노드 연결은 남았다. TLS+AUTH lab Redis는 없고 기존 demo2/PVC·Argo 내부 Redis는 유지한다. D의 새 lab Redis 구성/공급, B 선언/임의 UID/쓰기/TLSAUTH Probe, C CA/인증 계약 검토를 연결하며 Service DNS·발급자·일정은 실제 인계 대기다.

음성 Case5는 실제 Migration Secret을 Backend에 넣지 않고 기존 승인 Image의 순수 검사 함수에 가짜 db_admin URL을 주어 거부를 확인한다. 기존 cp-03 캐시·network none으로 실제 Image Alembic head도 함께 확인할 수 있다. [정확한 제안 명령](OCP_FIRST_DEPLOYMENT.md#d-추가-공급-수신--db와-lab-redis-음성-case5)은 아직 실행하지 않았으며 Image/Case5 실제 결과를 수신한 뒤 수락한다. lab Registry가 막혀도 이 두 확인의 준비는 별도로 진행한다.

## 1. 최초 인계 기준과 이번 Image 개정 상태

| 구분 | 기준·이번 상태 | 다음 담당 |
|---|---|---|
| 최초 인계 Source | **2026-10-05 최초 인계 기준:** App `c12b3d15a4dd2c806fac4326a9eb30ed6e8a81b3`; GitOps `3dc624d4dc9a774a6207708bfd68248101890401` / Tree `24a6c69fd22b8065bc537b5c77aef10336c9026b`. 이 병합 기준의 GitOps 49개 Blob·권한을 원격 manifest와 대조, #11 검토 Tree와 동일. 인계 PR artifact의 실제 checkout SHA/Tree는 artifact manifest에서 별도 확인 | B가 Source 묶음을 제출. D/C 수신·보완은 각 원 이슈에 기록 |
| 최초 인계 Native Source/Render 검사 | **최초 인계 기준** 병합 HEAD의 [Run 37323213534](https://github.com/seokpan/seokpan-hybrid-gitops/actions/runs/37323213534), Job 111807272347: Kustomize v5.7.1·Python 3.12·PyYAML 6.0.2, App18+OCP6+Release6+Cloud9 = **39 PASS**, skip0. 테스트가 실제 Kustomize Build 후 객체·참조·보류 조건 검사 | 실제 Cluster Admission·Image Pull·Data 연결·업무는 D/B/C 별도 |
| Render 인계 파일·Hash | 기존 [GitOps #12](https://github.com/seokpan/seokpan-hybrid-gitops/pull/12)에서 39개 검사 뒤 **8개 OCP 진단 Render·SHA256·객체 목록·실제 checkout SHA/Tree**의 artifact 보존을 추가했다. **이번 Image 입력 PR은 그 Workflow를 사용하며 Workflow 자체를 변경하지 않는다.** 새 HEAD Native CI·artifact의 실제 결과는 #10/PR에 연결하고 최초 인계 결과와 구분한다 | B가 새 HEAD artifact를 검증·제출, D/C 수신·보완 별도 |
| 실제 lab 상태 | #14의 D 보고에서 공유 Controller `openshift-gitops`, `seokpan-argotest` Active·managed-by 일치, Project default만·Application 없음, Pull Secret 미존재를 수신. D Caller는 system:admin이며 B 권한·Owner·사용 수락은 미확인. 검토자의 독립 OCP API 조회 결과는 아님 | D와 공유 Owner가 권한·Owner·사용 수락과 기존 배포 객체/충돌을 적용 직전 확인 |
| 새 조합 실제 실행 | 아래 D의 최종 Harbor Image/Scan/Digest 인계를 수신해 Lab/Recovery App과 보류 Migration의 Image 참조를 고정했다. 실제 lab Owner/권한·Secret/CA/Data/Schema·Node 플랫폼 공급 계약은 미수락. Workload Pull은 공급 수락 뒤 해당 활성화/최초 실행에서 검증할 결과이며 **NOT RUN**. OCP Apply/Sync·Registry 조회·Migration/DDL·AWS 호출 **NOT RUN** | 나머지 최소 입력 수락 → 별도 활성화 개정 → 최초 수동 Sync·새 Run |

#9/#11 Branch는 삭제됐으므로 위 SHA와 파일 링크를 사용한다. 2026-10-05 최초 인계 PR은 문서와 검사 결과 보존만 바꿨다. 이후 2026-10-06 Image 입력 개정은 아래 승인 App Digest와 lab의 논리 Pull Secret 참조만 반영하며 기동·Migration 실행·플랫폼 입력은 계속 보류한다. artifact는 실제 checkout SHA/Tree를 기록하므로 문서 기준 SHA와 구분하고, 실행할 때는 사용할 전체 SHA와 선언을 다시 대조한다. 개인 clone의 미push/미커밋 변경 확인은 본인 환경에서 해야 한다.

## 2. 코드가 OCP에 반영되는 실제 경로

`App 코드 → D Build → 승인 Image Digest → B lab 선언 입력 → D가 정확 SHA/Path로 Application 등록·수동 Sync → OCP가 Image Pull·Pod 기동 → B/C/D 검증`.

- **Image**는 실행할 프로그램과 파일을 묶은 것이다. App PR 병합은 Image 생성이나 OCP 교체가 아니다.
- **Manifest**는 어떤 Image·설정·개수로 실행할지 적은 YAML이다. `apps/base` 공통 선언에 `apps/overlays/lab`의 OCP 대상·Route·설정을 합친다.
- **Render**는 Kustomize가 위 입력을 최종 YAML로 계산하는 작업이다. Render만 하면 클러스터는 바뀌지 않는다.
- **Application**은 Argo CD에 Repo·SHA·Path·대상을 알려주는 객체다. 현재 Source는 수동 최초 Sync이며 자동 Sync가 없다. 따라서 GitHub 병합만으로 이 OCP 새 조합이 배포됐다고 볼 수 없다.
- **Sync**를 승인·실행하면 Argo CD가 해당 선언을 OCP API에 적용한다. Root Sync는 Child Application 등록이고 App Sync와 별개다. App가 Pod를 만들도록 승인한 뒤 실제 Node가 Image를 내려받아 기동한다. 0 Replica의 Sync는 Pull·Ready·업무 성공을 확인하지 않는다.

ROSA는 AWS에서 제공하는 별도 OpenShift 클러스터다. 현재 `cloud` 선언과 Infra의 ROSA 코드는 준비됐지만 이 코드 병합만으로 ROSA가 생성되거나 기존 OCP가 ROSA로 바뀌지 않는다.

## 2-A. D의 최종 Harbor Image 인계 수신 — 실행 승인은 별도

원본은 [D의 App #10 인계](https://github.com/seokpan/seokpan-hybrid-app/pull/10#issuecomment-6009053898)와 사용자가 전달한 최신 Scan 정정이며, [B의 실제 수신 답변](https://github.com/seokpan/seokpan-hybrid-app/pull/10#issuecomment-6009213599)에 수락 범위와 남은 입력을 연결했다. App Source `46e21a74dd608b41f2c12a0a57d76bddfcf25949`, Tag `git-46e21a74dd60`, Pipeline `hybrid/image-pipeline/main #3`, 보고 Platform `linux/amd64`의 조합이다. 아래 Digest는 **D가 보고한 최종 index Digest**이며 B가 Registry raw metadata/manifest를 별도 조회하거나 Workload Pull을 실행한 결과는 아니다.

| 소비 | 수신한 고정 Image 참조 | 반영 위치 |
|---|---|---|
| Backend + 보류 Migration | `harbor.seokpan.soldesk.store/seokpan-hybrid/backend@sha256:cbb7452c28f1dfe3533358916e8d0432cd65aa10865842451ab026972b55dae6` | lab/recovery `kustomization.yaml`의 `images.digest`, OCP Migration Job의 같은 Backend Image |
| Frontend | `harbor.seokpan.soldesk.store/seokpan-hybrid/frontend@sha256:e9fb167a9afd753f5ca4ef1644efd9d0a310b82cc42d4331ebaa65bbf4bfa4d9` | lab/recovery `kustomization.yaml`의 `images.digest` |

- **수신한 Scan 판단:** D의 최종 보고는 `CRITICAL 0 / fixable HIGH 0` Gate 수락이며, 초기 libexpat/pcre2 HIGH 경고는 기존 Dockerfile의 갱신과 최신 재검사 정정으로 대조한다. MEDIUM nghttp2/UNKNOWN libpng 등이 남을 수 있으므로 모든 취약점 0이나 B의 독립 Scan 성공으로 표현하지 않는다. 보고된 cp-03의 podman Pull도 OCP FE/BE/Job의 실제 Pull·SCC·UID·Ready 성공은 아니다.
- **private Harbor 논리 계약:** lab FE/BE와 보류 Migration에 `imagePullSecrets: [{name: lab-harbor-pull}]` 참조를 제안한다. 공급 형식은 `kubernetes.io/dockerconfigjson` type과 `.dockerconfigjson` key이며 소비 Pod와 같은 `seokpan-argotest` Namespace에서 필요한 Harbor project의 `Pull Repository` 권한으로 제한한 pull 전용 계정을 사용한다. D가 보호 공급 개정·Owner·권한을 검토·수락한다. 기존 동명 Secret의 Owner·소비자·type도 확인하며, 생성 후 변경할 수 없는 type이 다르면 수락한 교체/참조 전환 방법을 정한다. Secret 객체·값은 이 Source에 없고, 존재/공급 완료를 확인하지 않았다. 공유 default ServiceAccount의 암묵적 설정을 가정하지 않는다.
- **Registry TLS 신뢰 경계:** Pull Secret의 인증과 node/cluster의 Registry TLS 신뢰는 별도이며 App의 DB/Redis CA Mount가 이를 공급하지 않는다. 현재 lab의 신뢰 설정으로 Harbor TLS가 검증되면 추가 변경은 필요하지 않다. 추가 Trust 변경이 필요한 경우에만 공유 lab Owner와 변경 범위·영향·검증 방법을 합의한다. 이번 PR은 Trust 설치를 수행하지 않는다.
- **Recovery 범위:** FE/BE는 같은 보존 후보 Digest로 고정하고 기존 `recovery-harbor-pull` 참조를 유지한다. Recovery Redis Image·TLS/AUTH·Storage와 격리 Namespace는 계속 입력 대기다. 최종 격리 복구 환경에서 Harbor/독립 사본·Key를 읽을 수 있는지도 별도 확인한다. ROSA ECR 업로드·Digest·Worker Pull은 이번 인계에 포함되지 않아 Cloud ECR placeholder를 유지한다.
- **활성화 전에 남은 입력:** 실제 lab Context/Caller·Namespace/Controller Owner, Pull Secret/Registry Trust 공급 계약, DB/Redis DNS/TLS/AUTH/CA/Schema·외부 Secret 공급, Route/Origin과 필요한 Migration의 C 수락 Action/deadline이다. 최소 공급 계약 수락 → 별도 Replica 활성화 개정 검토 → 최초 수동 Sync 순서로 진행하고, **실제 App Image Pull·SCC/UID·Ready는 그 실행에서 검증한다.** 필요한 별도 Migration Job의 Pull도 승인한 Job 최초 실행에서 확인한다. App `replicas: 0`, Job `suspend: true`·`current`·backoff0와 미해결 표시는 유지하며 Image 입력 수신만으로 Sync·Migration·Recovery T18을 시작하지 않는다.

## 3. 지금 빠진 최소 입력과 바로 풀리는 실행

| 필요한 입력·수신 기록 | 공급·수락 담당 | 막는 실행 | 병행 가능한 B 작업 |
|---|---|---|---|
| App SHA → Harbor FE/BE 최종 Digest/Platform·Build/Scan 보고 수신. private Pull Secret/CA 공급 계약은 미수락; Workload Pull 시험은 이후 실제 실행 | D: [App #2](https://github.com/seokpan/seokpan-hybrid-app/issues/2) / App #10 인계. B: 위 Source 반영·lab-harbor-pull 논리 참조 제안 | 공급 계약 수락 전 활성화 대기. 수락 후 최초 Sync에서 Image Pull·SCC/업무 Case 확인. Image 값 작성 대기는 해소 | D Pull/Trust 공급 검토·나머지 lab/Data 입력 대조. ECR은 별도 |
| Context·Caller/RBAC·Controller/Project/Application·Namespace Owner·실제 managed-by·Repo 인증·4조 공지/공유 사용 수락 | D/공유 Owner: [GitOps #5](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5) | 실제 Application 등록·변경·Sync | 기존 승인 `reuse` 경로와 제한 Project 비교. 새 Namespace 자동 생성 금지 |
| Node에서 사용할 Registry로의 망 경로·DNS·CA·Pull 인증. 현재 Harbor 접근 미확보, Node 직접 검사는 미실행 | D/망·공유 Owner: [GitOps #14](https://github.com/seokpan/seokpan-hybrid-gitops/issues/14), B 수신/대조: #10 | Image를 사용하는 Pod 기동. 제한된 제어 등록은 권한·Owner·사용 수락 후 별도 준비 | 망 연결 지원 및 이미 있는 공통 Registry 후보·복사 호스트/Node 접근·Owner·동일 Image 내용/플랫폼·대상 Digest 확인 |
| lab DB DNS/Port/DB·CA/SAN·TLS·Runtime 계정·Schema, Redis rediss/TLS+별도 AUTH·CA, 외부 Secret/CA 공급 개정 | C 계약 + D lab 공급 + B 소비: [App #1](https://github.com/seokpan/seokpan-hybrid-app/issues/1), [GitOps #6](https://github.com/seokpan/seokpan-hybrid-gitops/issues/6) | 실제 연결·Ready·대표 업무 | 논리 Secret 참조·양성/음성 Case 대조 |
| Migration 필요 여부, 실제 Image 내 `seokpan-migration-gate`/자산, 같은 Backend Digest·ConfigMap/DB CA·별도 목적 자격·C 수락 action/deadline·유일한 Run | C 판단/수락, B 계약, 지정 실행자: App #1/GitOps #6 | 필요한 Schema 준비·해당 최초 App Sync | `current`와 실제 DDL 구분, suspended Job/단일 실행 준비 |
| 실제 Route Host·Origin·외부 DNS/TLS·승인 최초 Replica1·자원/종료 개정 | B 선언 + D lab 경로/실측: GitOps #10/#5/#6 | FE/API/WSS·외부 업무 | Route/Port/Probe·최초 활성화/삭제 보호 대조 |

비밀값·Credential URL·Private Key는 Git/Issue/Render에 넣지 않는다. 공급자는 공개 가능한 개정 ID·보호 공급 참조·수신/보완 상태만 남기고 실제 값은 보호 경로에서 대조한다.

**OCP 최소 조합에는 전체 A foundation·ECR·ROSA Cluster·복구 Host·완성 T18을 일괄 선행으로 붙이지 않는다.** ROSA의 실제 Plan 입력은 [Infra #25](https://github.com/seokpan/seokpan-hybrid-infra/issues/25)에서 병행한다.

## 4. Render를 보존하는 명령과 경로 선택

Source 검사에서 아래 경로를 모두 Build하는 것은 여러 선택 경로를 비교하는 작업이다. 실제로 모두 Apply/Sync하는 순서가 아니다.

| 경로 | Native 검사에서 확인한 용도·경계 |
|---|---|
| `apps/base`, `apps/overlays/lab` | FE/BE·Service·ConfigMap, lab의 같은 Host FE/API/WSS Route. Namespace/Secret/Job/Application/AppProject를 App 경로가 소유하지 않음 |
| `clusters/ocp-lab/reuse` | 기존 승인 Project/Application을 쓸 경우. 실제 Owner·권한·제한 범위 확인 전 입력 대기 |
| `clusters/ocp-lab/bootstrap`, `clusters/ocp-lab/root` | 별도 Root를 쓰기로 수락했을 때만. 초기 수동 Sync·고정 Repo/SHA/Path·삭제 보호 |
| `clusters/ocp-lab/new-namespace`, `platform/ocp-lab/new-namespace` | 새 Namespace가 필요하고 Owner·managed-by·공유 사용이 승인된 경우만 |
| `operations/ocp-lab/migration` | App/Root 상시 Sync 밖의 `suspend: true`, 기본 `current`, backoff0 Job. 현재300초는 DDL 승인시간이나 측정값이 아님 |

이미 준비한 GitOps clone에서 개인 변경을 먼저 보존하고, 별도 detached worktree로 같은 SHA를 확인한다. 아래 `3dc624...`는 **2026-10-05 최초 인계 재현용 기준**이다. 이번 Image 입력 개정을 확인할 때는 새 PR/병합·Native artifact의 검토된 전체 GitOps SHA로 바꾸고 Source/Image/Render를 함께 대조한다. 아래는 Source만 읽고 로컬 파일을 쓰는 명령이다. `/absolute/new/...` 경로는 실제 별도 경로로 바꾼다. 출력에는 미해결 입력이 남으므로 **Apply/Sync 금지**다.

```bash
set -euo pipefail
git status --short
git fetch origin main
git worktree add --detach /absolute/new/ocp-source-worktree 3dc624d4dc9a774a6207708bfd68248101890401
cd /absolute/new/ocp-source-worktree
git rev-parse HEAD
kustomize version
python3 -c 'import yaml; print(yaml.__version__)'
ocp_render_dir="$(mktemp -d /absolute/new/ocp-render-20261005.XXXXXX)"
for ocp_source_path in apps/base apps/overlays/lab clusters/ocp-lab/reuse clusters/ocp-lab/bootstrap clusters/ocp-lab/root clusters/ocp-lab/new-namespace platform/ocp-lab/new-namespace operations/ocp-lab/migration; do
  ocp_render_name="$(printf '%s' "$ocp_source_path" | tr '/' '_')"
  kustomize build "$ocp_source_path" > "$ocp_render_dir/$ocp_render_name.yaml"
done
(cd "$ocp_render_dir" && sha256sum ./*.yaml > SHA256SUMS)
git status --short
```

Kustomize는 기존 검사와 같은 v5.7.1을 쓴다. GitOps #12에서 추가되어 이번 #13 Image PR에서도 재사용하는 Native Workflow는 위 **8경로**를 Build한다. artifact의 `source-manifest.json`에 실행 SHA/Tree·도구 개정·Path별 실제 객체 개수·종류/이름/Namespace·YAML SHA256이 있고 `SHA256SUMS`로 내려받은 8개 파일을 대조할 수 있다. `README.md`는 **NOT DEPLOYABLE·Runtime NOT RUN** 범위를 명시한다. 기존 Native 검사 자체의 App base/lab/Recovery 3경로 + OCP6경로 =9경로와, 이번 OCP 인계 artifact의 base/lab 2경로 + OCP6경로 =8경로는 다른 범위다.

artifact 보존은 **7일**이며 Source/인계 검토용이다. GitHub artifact 다운로드에 로그인이 필요할 수 있으므로 D/C가 받을 보존 위치와 읽은 개정을 별도로 기록한다. 보호된 Secret/CA 값·Runtime Run/Index·DB Backup/Recovery Release 보존 정책과 별개다. 만료 뒤에는 수락한 정확 SHA에서 재생성할 수 있다. 실제 PR CI 결과·artifact 다운로드 대조·D/C의 읽은 개정과 수신 여부를 #10에 기록한다. 2026-10-05 최초 인계 당시에는 Native Kustomize 부재와 다운로드 timeout 때문에 로컬 Render를 실행하지 않았다. 이번 Image 입력 개정은 공식 Kustomize v5.7.1 Archive SHA256을 기존 Workflow 값과 대조하고 Python3.12/PyYAML6.0.2에서 기존 **39개 검사 PASS·실제 9개 진단 Render(위 OCP8 + Recovery1)**와 Hash를 확인했다. Lab/Recovery Release와 Migration 입력 검사는 남은 입력/기동 보류 때문에 exit2를 유지하고 실행 출력 파일을 만들지 않는다. 로컬 기준은 고정 main `6ea2d9a90ab7c58803767220abf956d3c1b54a5f` + 검토된 변경 Blob이며 최종 PR HEAD/Native CI artifact는 별도로 연결한다.

현재 Source의 실제 예는 아래와 같다.

```yaml
# apps/overlays/lab/kustomization.yaml
namespace: seokpan-argotest
images:
  - name: seokpan-backend
    newName: harbor.seokpan.soldesk.store/seokpan-hybrid/backend
    digest: sha256:cbb7452c28f1dfe3533358916e8d0432cd65aa10865842451ab026972b55dae6
```

`apps/base/backend.yaml`·`frontend.yaml`는 `replicas: 0`이다. 이번 Harbor Image 수신 뒤에도 나머지 lab/Data/Pull/Owner 입력이 대기 중이라는 뜻이며, 이 상태의 Synced를 실행 성공으로 세지 않는다. 활성화는 승인 Digest/설정·같은 Image의 Migration·필요 Schema를 대조한 별도 개정으로 만들고 `make release-manifest` 입력 검사를 통과한 뒤 최초 수동 Sync한다.

## 5. 실제 시험 Case — 기대와 실제를 따로 쓰기

| Case | 기대·확인할 조건 | 이번 실제 결과 |
|---|---|---|
| 대상/Owner/수동 Sync/삭제 보호 | Context·SHA/Path·Namespace·Project 범위·단일 Owner. App 자동 Sync/Prune 보류, finalizer 없는 수동 정리·보호 대상 분리 | **NOT RUN**, D/Owner 현장 수락 대기 |
| Image Pull·임의 UID·쓰기 | 승인 Digest 실제 Pull, 고정 UID/권한 확대 없이 기동·CA읽기·`/tmp`쓰기·ReadOnlyRootFS | **NOT RUN**, Harbor Source 참조는 반영. D Secret/Trust·Owner 공급 수락 후 해당 최초 Sync에서 실제 Pull·기동 시험 |
| Startup/Live/Ready | Backend `/health/startup`·`/health/live`·`/health/ready`, Service/Probe/Data 조건. FE200과 BE Ready 구분 | **NOT RUN** |
| DB/Redis 연결 | TLS/CA/SAN·목적 계정과 Redis 별도 AUTH의 정상/거부·CA/Pod교체, hostAliases 우회 없이 목적 DNS 사용 | **NOT RUN**, C/D 입력 대기 |
| Schema/Migration | 같은 BE Digest·Config/DB CA·별도 Migration 자격. 필요한 경우만 수락 Action/deadline·단일 실행·Schema 결과 | **NOT RUN**, 이미 head인 current를 DDL 성공으로 쓰지 않음 |
| FE/API/WSS·대표 업무·종료 | 로그인/회원가입·Room/Ready/투표/착수/결과·재접속, 오류·응답 유실·중단/종료의 기대/실제 대조 | **NOT RUN** |
| Cloud 인계 | 위 same Source/Image/설정 결과·실패·Cloud 차이·재시험 범위를 B/C/D 수락 | **NOT RUN**, OCP PASS를 Cloud3Pod/ROSA/T18로 승계하지 않음 |

[GitOps #7의 완료](https://github.com/seokpan/seokpan-hybrid-gitops/issues/7#issuecomment-5945477442)는 **2026-10-02 demo2의 기존 Image**에서 1차 GRANT·Ready·게임/Rating·Migration current=head를 확인한 범위다. DB에 PVC가 없던 조건, DDL 미실행, RDS TLS/권한 별도 판단을 유지한다. #7을 다시 열거나 새 Source/Image PASS로 복사하지 않는다.

실제 새 조합 시험 때만 새 Run을 만들고 Source/Image/Config/Context·수행자·Case·실패/수정/재시험·Cloud 차이를 원 GitOps #5/#6, D Index, B 수신에 연결한다. 이번 Source/CI만으로 Runtime Run/Index·RTO/RPO 성공을 생성하지 않는다.

## 6. D/C에게 받을 회신 — 값 대신 수신 상태

**D → GitOps #5/#6·App #2:** 위 Source와 Render 범위를 수신했는지, 사용할 Controller/Context·Project/Application/Namespace와 Owner·권한·공유 사용/4조 사전 공지 상태, AppSHA→Build/Test/Scan→Registry별Digest/Platform/Pull 개정, 추가로 필요한 B 보완을 기록한다. 실제 실행 전이면 그 상태를 명시한다.

**C → App #1·GitOps #6:** 목적 DB/Redis·TLS/CA/SAN·AUTH·Schema·Runtime/Migration 계정 계약과 보호 공급 개정, Migration 필요 여부·허용 Action/deadline·실행 담당, 추가 B/D 보완을 기록한다. Password/Token/GRANT 원문은 공개하지 않는다.

**B → GitOps #10·Docs #21:** Source/Case 제출과 Render파일 제출 여부, D/C의 수신/보완·최소 입력 수락, 별도 활성화 개정/실제 Run을 서로 다른 칸에 기록한다. OCP 사전검증 수락 → 결과/Cloud 차이 인계 → 공유 사용 종료 후 승인 실습 대상 정리를 구분한다. **OCP 삭제는 ROSA 준비/Plan/생성의 선행조건이 아니다.**
