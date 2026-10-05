# OCP 최초 배포 인계 — Source 검토에서 실제 lab 수락까지

이 문서는 정태훈(B)이 최초 OCP 배포에 필요한 선언·입력·검사 범위를 준비하고, 최유준(D)과 김상희(C)가 실제 Image·lab·Data 입력과 실행 결과를 연결하도록 안내한다. 현재 Source는 **입력 대기 후보**다. 이 문서의 작성이나 PR의 리뷰·병합은 OCP Runtime PASS 또는 ROSA 수락을 뜻하지 않는다.

| 구분 | 원본과 기록 위치 |
|---|---|
| B 개인 상위·TH 체크 | [h-docs Issue #21](https://github.com/seokpan/seokpan-hybrid-docs/issues/21) — TH01·08·09·11 및 후속 영향 |
| B 선언·Render·인계 | [h-gitops Issue #10](https://github.com/seokpan/seokpan-hybrid-gitops/issues/10) |
| D 실제 Argo/lab 배포 | [h-gitops Issue #5](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5) |
| D 새 Image의 실제 접속·업무 검증 | [h-gitops Issue #6](https://github.com/seokpan/seokpan-hybrid-gitops/issues/6) |
| App 접속 계약·Build | [h-app Issue #1](https://github.com/seokpan/seokpan-hybrid-app/issues/1), [h-app Issue #2](https://github.com/seokpan/seokpan-hybrid-app/issues/2), [h-app Issue #4](https://github.com/seokpan/seokpan-hybrid-app/issues/4) |
| Data/TLS·Schema | [h-infra Issue #17](https://github.com/seokpan/seokpan-hybrid-infra/issues/17), [h-infra Issue #19](https://github.com/seokpan/seokpan-hybrid-infra/issues/19) |
| 팀 입력·인계·공식 결과 연결 | [h-docs Issue #8](https://github.com/seokpan/seokpan-hybrid-docs/issues/8), [05 구현·검증 기록](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/execution/05_IMPLEMENTATION_AND_VALIDATION.md), [Evidence 안내](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/evidence/README.md) |

## 1. 검토 대상과 변경 경계

- App의 병합 Source는 전체 Commit **`c12b3d15a4dd2c806fac4326a9eb30ed6e8a81b3`**이다. [h-app PR #5](https://github.com/seokpan/seokpan-hybrid-app/pull/5)의 Source 병합과 D의 새 Build/Scan/Digest·lab 실행 수락은 구분한다. 개인 작업환경의 미반영 변경은 B가 대조하고 보존한다.
- [h-gitops PR #9](https://github.com/seokpan/seokpan-hybrid-gitops/pull/9)의 App 경로는 `apps/base`와 `apps/overlays/lab`이다. 이 문서의 최초 대조 기준은 기존 HEAD `39f416f3201fc566a6421055422e3dba89310965`이며, 후속 변경의 **최종 전체 HEAD·Render와 검사 결과를 다시 기록**한다. 이전 HEAD의 검사 성공을 새 HEAD 성공으로 사용하지 않는다.
- [h-gitops PR #11](https://github.com/seokpan/seokpan-hybrid-gitops/pull/11)은 #9 Branch를 Base로 하는 Cloud 후보다. OCP 최초 인계의 선행은 아니다. #9 병합 뒤 #11의 Base를 main으로 바꾸고 Diff·Source 검사를 다시 확인한다. 그 확인 전 #9 Branch 정리는 보류한다.
- 현재 lab Overlay의 `seokpan-argotest`는 **후보 대상 이름**이다. 실제 사용 승인·존재·관리 Owner·권한의 확인을 대신하지 않는다. 기존 `seokpan-app`, 공유 Operator 영역, 1차 자원은 이번 시험이 임의로 변경·삭제할 범위에 넣지 않는다.
- App base/lab는 FE/BE Deployment·Service·비민감 ConfigMap·Route를 다룬다. App Overlay에 Namespace·Secret·Migration Job·Application·AppProject 객체를 섞어 상시 관리하지 않는다. GitOps 플랫폼 선언과 App 선언, 별도 Secret 공급·단일 Migration 실행을 구분한다.
- 최소 lab 제어 후보의 경로·선택 방식은 [clusters/ocp-lab](../clusters/ocp-lab/README.md)에 있다. 기존 승인 경로 대조용 `reuse`, 새 Root의 `bootstrap`/`root`, 승인한 새 Namespace가 필요한 때만 사용하는 `new-namespace`는 서로 다른 선택이다. 별도 `operations/ocp-lab/migration` Job은 suspended 입력 대기 후보이고 Root/App의 상시 Sync 경로에 포함하지 않는다.

### 공유 Controller의 기존 기록과 적용 전 확인

[h-gitops Issue #5](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5) 본문과 [PR #9 D 리뷰](https://github.com/seokpan/seokpan-hybrid-gitops/pull/9#pullrequestreview-5413591924)는 Application을 **공유 `openshift-gitops` Namespace**에 등록하고, 대상 **`seokpan-argotest`의 managed-by 라벨을 유지**하며, **4조에 사전 공지**하도록 기록한다. 이는 D가 전달한 환경 조건이며 이번 Source 작업에서 클러스터를 새로 조회하거나 공유 사용 수락·공지 발송을 완료했다는 뜻이 아니다.

D/공유 Owner가 적용 직전에 실제 Controller/Instance·권한·Context와 기존 Project/Application의 Owner를 재확인한다. 기존 managed-by 라벨의 정확한 값과 Controller 일치를 확인하고 보존한다. 새 Namespace를 승인하는 경로는 필요한 managed-by 값·생성/관리 Owner·지원 동작을 먼저 수락한다. 값이 확인되지 않은 라벨을 새로 넣거나 기존 라벨을 변경하지 않는다. 4조 사전 공지의 수행자·대상 범위·시점·공유 사용 수락은 #5에 남긴다. 이 문서 작업에서는 공지를 발송하지 않았고 `gitops-controller-input-required`를 실제 Namespace 값으로 활성화하지 않는다.

## 2. 지금 B가 만드는 묶음과 담당별 병행 작업

| 담당 | 지금 준비할 결과 | 실제 실행 때 확인할 결과 |
|---|---|---|
| B 정태훈 | Source/개인 변경 대조, App와 플랫폼 선언의 Owner 범위, 진단 Render·입력 누락표, 아래 시험 Case, 인계 원본 링크 | 승인 입력 개정 반영, 수동 최초 Sync와 App 동작 결과 대조, Cloud로 넘길 조합·차이·재시험 범위 |
| D 최유준 | 병합 App Source의 Build/Test/Scan·Registry별 Image Mapping, 실제 lab Context/권한·Argo/Operator·Pull·실행 창 확인 | 새 Image의 Pull·SCC·파일/쓰기 경로·Health·업무·종료, Argo 동작·Event·로그·Run·Index 연결 |
| C 김상희 | 승인 DB/Redis 대상·TLS/AUTH·CA/SAN·목적별 권한·Schema 및 Migration 필요 여부의 연결 계약 | 해당 Data 조건·연결 양성/음성 결과, 필요한 Migration의 대상·승인·결과 수락 |
| 공유 환경 Owner | 기존 Project/Application·Namespace·Operator 사용 범위와 중복 관리 여부, 정리 범위 확인 | 이번 시험 범위 수락·공유 사용 종료와 보호 대상 확인 |

Source·진단 Render·Case·Owner 인계는 A의 모든 기반 작업을 기다리지 않는다. 실제 OCP 배포는 해당 시험의 최소 Image/lab/Data/Secret 입력을 기다린다. ROSA 기반 출력·실제 Plan·ECR Pull·전체 Offline 복구 Bundle은 각각 별도 작업이며 OCP 최초 Sync의 일괄 선행조건이 아니다.

## 3. 최소 입력표

이 표에는 논리 참조와 확인 범위만 둔다. Password·Token·Private Key·Credential 포함 URL, 실제 Secret 값이나 승인되지 않은 실제 ID를 Git/댓글/Render에 넣지 않는다. 공급자는 공개 가능한 개정 ID·보호 저장 경로·승인/수신 상태를 전달하고, D/B/C는 실행 전 보호 경로에서 대상과 값을 대조한다.

| 최소 입력 | 소비·확인 범위 | 공급·확인 담당 | 없을 때 막는 작업 |
|---|---|---|---|
| App 전체 Commit → FE/BE Image Mapping | Build/Test/Scan 결과, 전체 Digest·플랫폼, 실제 lab Registry·Pull 방식/CA. 활성화는 `images.digest`와 출력의 `@sha256` 고정, Job은 같은 Backend Digest. 과거 Image 캐시만으로 새 Pull 성공을 판정하지 않음 | D Build/Pull, B Source 대조 | 새 Image 활성화·실제 App 검증 |
| 실제 lab Context·Namespace·Caller/RBAC | #5의 공유 `openshift-gitops`·대상 `seokpan-argotest` 기록을 실제 Controller/Instance·Context/권한·Owner·API/CRD·Argo/Operator 버전과 재대조, Repo 읽기 인증 경로 | D와 공유 Owner, B 선언 대조 | 실제 플랫폼 변경·Application 등록·Sync |
| 공유 사용·Namespace 관리 | 기존 managed-by 라벨 값/Controller 일치·보존, 새 Namespace라면 승인 managed-by/Owner. 4조 사전 공지 수행·시점·범위와 공유 사용 수락 | D와 공유 Owner | 공유 Controller 등록/변경·해당 Namespace 최초 Sync |
| Project/Application·Repo/Revision/Path | 정확한 GitOps 전체 SHA와 `apps/overlays/lab`, 허용 Repo·Namespace·Resource 종류, 초기 Sync/삭제 경계. 기존 `default` 등의 실효 범위를 제한 `seokpan-ocp-lab-app` 후보와 비교 | B 선언, D/Owner 환경 확인 | 해당 Application 등록/변경·최초 Sync |
| DB 대상·CA·Schema·Runtime 계정 | `backend-db-runtime`의 `SEOKPAN_IDENTITY_DATABASE_URL`/`SEOKPAN_GAME_DATABASE_URL`; `backend-database-ca`의 `ca.crt`; 승인 Host/Port/DB·SAN·수명·목적별 GRANT·Schema 개정 | C 계약·수락, D lab 공급 협업, B 소비 대조 | DB 양성/음성 연결·Ready·DB 업무 |
| Redis TLS/AUTH 대상·CA | `backend-redis-runtime`의 `SEOKPAN_REDIS_AUTH_TOKEN`; `backend-redis-ca`의 `ca.crt`; `rediss` 대상·Port/DB·SAN·수명·AUTH 개정 | C 계약·수락, D lab 공급 협업, B 소비 대조 | Redis 양성/음성 연결·Ready·Runtime 업무 |
| 비민감 설정·Route | `runtime.env`의 Profile/허용 Origin/예상 대상과 같은 Host의 FE/API/WSS Route, 실제 DNS/TLS 경로 | B 선언, D lab 경로 확인 | 외부 접속·FE/API/WSS·업무 검증 |
| Secret/CA 공급과 교체 | 별도 Owner의 공급 완료·개정, App 참조 일치, 보호 보관·회수 범위. Operator 생성 객체는 덮어쓰지 않음 | 지정 공급자 C/D, B 소비 연결 | 최초 App 활성화·해당 개정 재접속 |
| Migration 필요 여부와 승인 | 대상·현재 Schema·동일 Backend Digest/Action; `backend-db-migration`의 `SEOKPAN_MIGRATION_DATABASE_URL`과 DB CA 보호 공급 참조, ConfigMap Hash·C 수락 deadline·유일한 Run·필요한 경우 단일 실행과 결과 | C 판단/수락, B App 계약, 지정 실행자 | 필요한 Schema 준비·해당 App Sync |

DB/Redis 연결 설정과 CA/Secret 논리 이름은 [apps/README.md](../apps/README.md)에 있다. 고정 이름 Secret/CA를 교체했다고 기존 Pod의 환경변수·TLS Context가 새 개정으로 바뀐 것으로 보지 않는다. 승인한 Backend 교체와 새 연결·업무 검증까지 같은 개정으로 기록한다. Migration 목적 인증정보를 일반 App Deployment에 공급하지 않는다.

## 4. Project/Application 경로 선택

**경로 A — 기존 승인 Project/Application 사용:** D와 공유 Owner가 기존 대상의 허용 Repo/Revision/Path·Namespace·Resource 범위·관리 주체·초기 수동 Sync/삭제 보호를 확인하면 그 Application을 지정 lab 전체 SHA에 고정한다. 확인되지 않은 기존 객체를 덮어쓰거나 플랫폼 Owner를 가져오지 않는다. 승인 기존 경로가 충분하면 신규 Root·전체 Cloud 정책·UWM·완성 복구 Bundle을 먼저 요구하지 않는다.

기존 Project가 `default`처럼 넓은 Repo·Destination·Resource 권한을 허용한다면, [제한 AppProject 후보](../clusters/ocp-lab/root/app-project.yaml)의 고정 Repo·`seokpan-argotest`·Deployment/Service/ConfigMap/Route와 cluster-scope 차단을 비교한다. 제한 Project를 기존 Controller에서 재사용하는 경우도 새 전체 Root가 반드시 필요한 것은 아니다. D/Owner와 해당 Project의 등록·변경 원본/단일 Owner 및 실제 RBAC를 수락한 뒤 `reuse` Application의 Project 참조를 같은 승인 개정으로 맞춘다. Source 후보의 제한은 실제 Controller 권한이 자동으로 좁아졌다는 증거가 아니다.

**경로 B — 새 단독 lab 플랫폼 경로 준비:** 기존 경로를 사용할 수 없으면 B가 별도 GitOps 플랫폼 원본으로 제한된 Project/Application과 필요한 Namespace 관리 경계를 준비한다. 실제 Operator/Argo Namespace·API/CRD·공유 설치의 사용 방식·권한은 D/Owner의 확인 입력으로 고정한다. 같은 객체를 기존 Argo·새 Root·Bootstrap이 중복 관리하지 않게 한다. 새 Operator 설치가 필요할 때만 Infra의 최소 Bootstrap 예외를 별도 검토하고, 이후 Project/Application/배포 원본은 GitOps로 관리한다.

어느 경로든 Root/Platform/App의 최초 자동 Sync를 보류하고 수동 확인한다. App의 최초 수동 Sync 이후 자동 Sync·SelfHeal을 켜는 변경은 승인한 별도 개정으로 진행한다. 자동 Prune는 초기 보류한다. Root/Child Application finalizer와 수동·연쇄 삭제, Namespace 삭제는 별도 보호 검토 대상이며 Prune 비활성화만으로 삭제 보호 완료를 선언하지 않는다. 공유 환경에서 파괴적인 삭제 대조 시험을 실행하지 않는다.

## 5. 1단계 — Source 품질 검사와 리뷰

아래 명령은 저장소 Root에서 실행한다. 검사 환경에 **Kustomize v5.7.1, Python/PyYAML**을 준비하고 실행 도구 개정·최종 GitOps HEAD를 기록한다. 기존 명령은 클러스터 Apply/Sync나 Registry/AWS 호출을 하지 않는다.

```bash
kustomize version
kustomize build apps/base
kustomize build apps/overlays/lab
make preview ENVIRONMENT=lab KUSTOMIZE=/path/to/kustomize
make test KUSTOMIZE=/path/to/kustomize
```

`/path/to/kustomize`는 준비한 실행 파일 경로로 바꾼다. 현재 진단 Render에는 `INPUT_REQUIRED`·예약 `.invalid` 주소·`replicas: 0`이 남는다. 이것은 입력 대기 선언을 대조하는 자료이며 Apply/Sync할 Release가 아니다. 실제 Build/Test의 실행·기대 결과·실제 결과·실패/제한을 인계 원본에 기록한다.

입력 대기 Source 리뷰에서는 App/플랫폼 Owner, 공통·환경별 배선, Secret/CA 경계, 초기 수동 Sync·기동 보류·삭제 보호, 아래 Case의 확인 가능성을 검토한다. **이 검사를 통과한 최종 HEAD의 Source 리뷰·병합**은 실행 보류 상태의 선언을 확정하는 판단이다. **실제 lab 활성화**는 다음 단계에서 공급 입력과 승인 조합을 충족한 별도 판단이다. 입력 대기 Source를 병합하면서 실제 Image/DNS/Secret 성공이나 Runtime PASS를 체크하지 않는다.

새 lab 제어 후보도 같은 최종 HEAD에서 진단 Build한다. 아래 경로를 모두 Build하는 것은 Source 검사를 위한 것이며 서로 다른 경로를 한꺼번에 등록·Sync하라는 실행 순서가 아니다.

```bash
kustomize build clusters/ocp-lab/reuse
kustomize build clusters/ocp-lab/bootstrap
kustomize build clusters/ocp-lab/root
kustomize build clusters/ocp-lab/new-namespace
kustomize build platform/ocp-lab/new-namespace
kustomize build operations/ocp-lab/migration
```

## 6. 2단계 — 실제 lab 활성화와 시험

1. D/Owner가 실제 Context·Caller·Namespace·Argo/Operator 버전·Project/Application 경로를 확인한다. B는 Root/Platform/App 단일 Owner·초기 수동 Sync·Prune/finalizer/Namespace 보호를 대조한다.
2. B/C/D가 최소 입력표의 공급 개정·수신·누락을 확인한다. Image Digest·Route/Origin·DB/Redis 대상·CA/SAN·Schema·Secret 참조가 같은 승인 조합인지 확인한다. App 기동은 계속 보류한다.
3. C와 현재 Schema/대상을 확인한다. **Migration이 필요한 경우만** 승인한 별도 단일 실행으로 처리하고 결과·Schema를 수락한다. 이미 준비된 Schema에 불필요한 DDL을 실행하지 않는다. Migration을 App의 상시 자동 Sync/SelfHeal 대상으로 만들지 않는다. [Job 입력 검사와 DB 전용 설정 근거](../clusters/ocp-lab/README.md#migration은-app-sync-hook이-아니다)를 따라 App/Job Backend Digest·ConfigMap Hash·DB 대상/CA·별도 Migration 자격·C 수락 deadline을 대조한다. 후보의 300초를 실제 쓰기 작업의 승인 상한이나 측정 성공으로 취급하지 않는다.
4. 승인 입력을 별도 활성화 개정에 반영한다. lab 최초 FE/BE 각 1의 후보·실측 자원·Image/Pull·설정·기동 보류 해제·삭제 경계를 리뷰한다. 최종 GitOps 전체 SHA와 App/Digest/설정/Secret/Schema 조합을 고정한 뒤 아래 입력 검사를 수행한다.

   ```bash
   make release-manifest ENVIRONMENT=lab OUTPUT=/separate/new/path/lab.yaml KUSTOMIZE=/path/to/kustomize
   ```

   출력 디렉터리를 미리 준비하고 이전 파일과 겹치지 않는 새 경로를 쓴다. 입력 누락·0 Replica·미해결 표시가 있으면 도구는 출력 생성을 거부한다. 입력 검사 성공은 실제 Context·권한·Pull·Secret 값·Runtime/업무 수락을 증명하지 않는다.

5. D가 승인한 정확한 Revision/Path와 대상에 최초 **수동 Sync**를 수행하고 B/C와 아래 Case를 검증한다. 과거 공개 예제나 old Source/Image 결과를 새 조합으로 대체하지 않는다. 변경 후에는 영향받은 Case를 새 Run으로 재시험한다.
6. D/B/C는 실제 결과와 Cloud 차이를 수락하고 후속 전달한다. 별도 Source 변경이 있다면 같은 HEAD/Render/Image/설정 조합인지 다시 대조한다. OCP PASS를 ROSA RDS/ElastiCache/ECR/Worker/AZ 또는 최종 복구 T18 PASS로 확대하지 않는다.

| Case | 기대·확인 내용 | 기록할 실제 근거 |
|---|---|---|
| 대상·최초 Sync·삭제 보호 | 정확한 Context/Namespace·GitOps SHA/Path·Owner. 초기 App 자동 Sync 보류, 수동 최초 Sync, 자동 Prune 보류·finalizer/연쇄/Namespace 보호 별도 확인 | Argo 대상/설정·Diff·Resource 범위·Sync/Health. 보호 검토 결과와 미실행 삭제 Case |
| 새 Image·SCC·임의 UID·쓰기 | 승인 Digest를 실제 Pull. 필요한 임의 UID에서 기동·CA/설정 읽기·`/tmp` 쓰기·ReadOnly RootFS, 고정 UID나 권한 확대를 전제로 하지 않음 | Image ID/Digest·Admission/Event·UID·파일 접근·실제 쓰기·실패. Requests/Limits·종료 유예는 실측 개정 연결 |
| Startup/Live/Ready | Backend Pod/Service의 `/health/startup`, `/health/live`, `/health/ready`를 실제 DB/Redis 조건과 연결. Frontend `/health/live` 200과 Backend Ready를 구분 | Pod/Kubelet Probe·Service 대상과 응답·Data 준비 조건/변화. 공개 Host의 FE 200만으로 Backend 준비 판정 금지 |
| DB·Redis TLS/AUTH 양성 | 승인 대상/목적 계정·Schema·CA/SAN·AUTH 개정에서 정상 접속. Redis는 TLS+별도 AUTH | 비밀값을 제거한 연결/권한/대상 결과·실제 Data 조건·C 수락 |
| 접속 음성·CA/Hostname | 틀린 대상·CA·Hostname·AUTH·목적 권한 조건에서 실패하며 비밀값을 노출하지 않음. TLS 검증·AUTH를 완화해서 통과시키지 않음 | 격리된 시험 조건·기대 거부/실제 거부·Ready/로그·오류 원인. 공유 DB/실사용 Credential 변경 금지 |
| Schema·필요한 Migration | 승인 대상/현재 Schema·같은 App/Job Backend Digest와 설정/DB CA를 확인. C가 수락한 Action/deadline에서 필요한 변경만 단일 실행·결과 수락. timeout/실패 후 상태를 먼저 확인하고 불필요한 실행·App 재Sync DDL 반복을 하지 않음 | 필요/불필요 판단, Source 입력 검사·승인 Ref·Digest·deadline·실행 횟수·실패/종료/Schema 상태와 C 수락 |
| FE/API/WSS·인증 | 같은 승인 Host에서 HTTPS FE·`/api/v1`·`/ws/v1`, 허용 Origin·실제 사용자 인증/권한, WSS 연결·재접속 확인 | 브라우저/Client 조건·Route/업무 응답·연결/실패·재인증. Route `timeout-tunnel: 1h`를 장시간 성공 측정으로 취급하지 않음 |
| 대표 업무·오류·상태 | 현재 지원하는 로그인/Guest·로비/방·Ready/게임·투표/착수·종료/결과를 실제 계약대로 확인. 오류·권한 거부·접속 단절에서 미확인 쓰기를 중복 재실행하지 않음 | 지원 기능/제한·기대/실제 결과·DB/Redis 정합·완료/불명확 결과·후속 결함 링크 |
| 교체·종료·Drain 경계 | 승인한 lab 대상의 Pod 교체/종료·재접속/업무 상태 확인. 불명확한 게임을 정상 완료로 기록하지 않음. 공유 Node Drain은 Owner와 범위·영향 확인 후 별도 실행 | 종료 시간선·이벤트·WSS/사용자 안내·현재 업무/DB 결과. 미실행 Node Drain은 NOT RUN, lab 단일 Replica를 Cloud 무중단 증거로 사용하지 않음 |
| Argo 동작·Cloud 차이 | Deployment의 Pod 재생성과 Argo SelfHeal을 구분. 자동 Sync/SelfHeal은 최초 수락 후 별도 승인 개정으로 시험. OCP와 ROSA의 Data/Pull/권한/규모 차이를 후속 Case에 연결 | 실제 변경·Controller 동작·같은 조합의 Run, PASS/FAIL/PARTIAL/NOT RUN 및 ROSA 재시험 범위 |
| 실습 정리·잔존 확인 | 현재 Application에는 삭제 finalizer가 없으므로 Application만 삭제해도 배포 객체는 남는다. 아래 수동 정리를 기본으로 선택하고 해당 lab App에만 별도 승인한 finalizer 경로를 대조한다 | 정리 전/후 객체 목록·단일 Owner·허용 삭제 범위·잔존·보존 결과·실제 수행자/공유 Owner 수락. 공유 Namespace/Secret/Data/Operator 삭제는 제외 |

### 실습 정리 방법 선택

1. D의 시험 결과·Source/Image/설정·원 Run을 보존하고 B 인계 및 공유 Owner의 사용 종료·대상 범위를 수락한다. 삭제 전 `seokpan-argotest`의 **이 App이 관리한 Deployment/Service/Route/생성 ConfigMap 목록**과 Owner·사용자를 기록한다. Namespace 전체를 삭제 목록으로 삼지 않는다. 별도 Migration Job은 App 관리 객체가 아니므로 승인한 Run/Owner의 정리 범위로 따로 판단한다.
2. **기본 수동 정리:** App의 Sync/SelfHeal 및 재등록 경로를 승인 범위에서 보류하고 Application 삭제/등록 해제를 처리한다. finalizer가 없으므로 App 객체가 없어졌다는 사실을 리소스 정리 성공으로 쓰지 않는다. 확인한 이 App 객체만 별도 수동 정리하고 잔존/다른 사용 여부를 재확인한다. 공유 Secret/CA·DB/Redis·Namespace·Controller와 기존 1차/복구 자산을 일괄 삭제하지 않는다.
3. **별도 승인한 cascade 대안:** D/Owner가 실제 Argo 버전 동작·현재 보호 annotation·관리 객체 목록을 검토한 경우에만 **해당 lab App Application 하나**의 finalizer/삭제 보호 개정을 별도로 승인한다. Root/Platform/공유 Namespace까지 cascade 범위를 넓히지 않는다. 격리된 범위에서 기대/실제 삭제·보호 대상 잔존을 새 Run으로 확인한다. 현재 Source는 이 finalizer를 추가하지 않았으며 자동 cascade 승인이 아니다.

이전 #5의 cascade 전제는 현재 finalizer 없는 후보에 그대로 적용하지 않는다. 어느 방법인지, 아직 미수락/미실행인지, 실제 정리한 정확한 범위와 남은 객체를 #5와 원 Run에 기록한다.

## 7. 제출·수신과 다음 행동

B는 GitOps #10에 Source/최종 전체 SHA·진단 Render·입력 누락·Case·영향/제한을 연결한다. D의 #5/#6과 C의 Data 이슈에는 해당 인계 원본 링크·요청 범위를 연결한다. **제출과 수신/기술 수락은 따로 기록**하며, 다른 담당의 실행 결과·수락을 B가 대신 완료로 표시하지 않는다. 실제 시험은 [Evidence 안내](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/evidence/README.md)에 맞춘 새 Run에 남기고 원 Issue → h-docs #21 해당 TH → 05/Tracker/Index 순서로 연결한다.

```text
범위 / 실제 수행자·검토자 / 시각(KST):
App SHA / GitOps SHA·Path / Image Digest·플랫폼:
환경·대상(공개 가능한 참조) / 설정·Secret·CA·Schema 개정:
검사·Case / 기대 결과 / 실제 결과 / PASS·FAIL·PARTIAL·NOT RUN:
원 Run·PR·로그 링크 / 실패·제한 / Cloud 차이·재시험 범위:
인계 제출 범위·시각 / 수신·수락·보완 요청:
Blocker·공급 이슈 / 직접 막는 실행 / 계속할 준비 / 다음 확인 시점:
```

| 상태 | 다음 행동 |
|---|---|
| Source·진단 Render·Case 준비 완료 | 최종 HEAD Source 리뷰 요청, D/C/Owner에 최소 입력·인계 범위 연결. 아직 Runtime 수락 전 |
| Image/lab/Data 입력 일부 대기 | 해당 공급 이슈·개정·직접 막는 Case를 기록. B의 선언/Case 보완·Cloud/Recovery·ROSA 준비는 병행 |
| 실제 OCP 조합 수락 | Source/Image/설정/Schema와 실패/남은 차이를 보존하고 ROSA 후속·필요 재시험으로 전달 |
| 실습 정리 검토 | D의 검증/원시 결과 보존, B의 Release/Overlay 인계, 공유 Owner의 사용 종료·정리 범위 확인 후 승인한 lab 대상만 정리 |

OCP 사전검증 업무 완료, lab 대상 정리, 공유 OCP 클러스터 종료는 별도 판정이다. ROSA 준비·Plan은 OCP와 겹칠 수 있으며 OCP 삭제는 ROSA 시작 조건이 아니다. 기존 1차 Kubernetes/DB/Redis·Image·백업·로컬 복구 자산과 공유 Data/Operator 영역을 이번 lab 정리 대상으로 묶지 않는다. 아직 실제 정리일·ROSA 생성/삭제일·Runtime PASS나 새로운 비용 승인으로 기록할 근거는 없다.

기준: [03 §3-F.6~7·17 및 §3-I.13](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/design/03_DETAILED_DESIGN.md), [04 §3~4](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/design/04_IMPLEMENTATION_READINESS.md). 승인 설계의 값·역할·최종 시험 범위는 유지한다.
