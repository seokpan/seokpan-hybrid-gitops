# OCP 최초 배포 인계 — Source 검토에서 실제 lab 수락까지

> **현재 인계 기준: 2026-10-07.** GitOps #17은 `fa3cea313e2cb1533d9703082619b085a3de25cc`에 병합됐다. 아래 Source·공급 보고와 실제 배포/업무 수락은 서로 다른 상태다.

| 항목 | 이미 반영된 Source·수신 보고 | 남은 직접 조건 |
|---|---|---|
| lab Registry | 내부 Registry의 `seokpan-argotest/backend`·`frontend`를 FE/BE·별도 Migration Job이 소비. 승인 Index Digest 보존. D의 워커2×Image2/default SA Pull 4건 보고 수신 | 실제 실행 직전 Namespace/SA·보관·권한·사용창 확인. 별도 lab Harbor Pull Secret 공급을 다시 선행조건으로 두지 않음 |
| Data 계약 | C v2.2의 Valkey 7.2 선택·CA **ConfigMap** 정정 수락. Infra #37 Data Root 병합. `backend-redis-*` 논리 이름은 유지 | 실제 Valkey·고정 Client/Lua/RESP·업무 호환은 별도 검증. C의 Pool3+overflow2/60연결 시나리오는 미채택 |
| lab 서버 | D의 Image/TLS/AUTH/Runtime Secret 공급 보고, Service DNS `lab-redis.seokpan-argotest.svc` 소비 선언 수락 | D 작성 제안의 실제 수락·StatefulSet/Service/config PR → C Data/B Source·제한 AppProject 검토. 공급물만으로 서버 Ready가 되지 않음 |
| 실제 활성화 | FE/BE replicas 0, Migration suspend/current/300초·단일 실행·목적 자격·삭제 보호 유지 | Valkey Service/Ready 및 DB/Schema·공개 CA/목적 Secret·Route·실효 권한·공유 사용창·live Diff 수락 → 필요한 단일 Migration → Backend → Frontend → 같은 조합 Run |
| 병행 | Cloud 금고의 B 본인 복호화·해시·독립 보관, ROSA 본인 환경·Caller/Backend·지원·비용 준비 | Cloud 금고를 lab Source 검토/실행의 선행조건으로 묶지 않음. 실제 ROSA Plan에는 A/C 제한 출력·공통 prerequisite·Data SG2 필요 |

근거: [Registry 공급 #14](https://github.com/seokpan/seokpan-hybrid-gitops/issues/14#issuecomment-6016144794), [Valkey 공급 #6](https://github.com/seokpan/seokpan-hybrid-gitops/issues/6), [Data 계약 #19](https://github.com/seokpan/seokpan-hybrid-infra/issues/19#issuecomment-6014028826), [Source #17](https://github.com/seokpan/seokpan-hybrid-gitops/pull/17). Cloud ECR·Recovery Harbor는 유지한다. `lab-harbor-pull` 참조 제거는 실제 Secret 삭제가 아니다. D의 system:admin 조회는 B 권한 확인을 대신하지 않으며, 10/6 공유 사용 보고가 이후 모든 사용창의 승인을 뜻하지 않는다.

<a id="2026-10-06-현재-확인--registry-경로와-먼저-할-수-있는-준비"></a>
### Registry 경로와 제어 등록의 경계

Root 등록/Sync, App 객체의 replicas0 Sync, 실제 Pod 활성화는 서로 다른 효과다. Registry/Data 전체를 제어 등록의 선행조건으로 두지 않되 실제 Context·권한·단일 Owner·공유 사용·기존 객체/live Diff를 먼저 확인한다. 진단 YAML/ZIP은 Apply·Sync용이 아니며 기존 Release 거부를 우회하지 않는다. StatefulSet을 같은 제한 AppProject로 관리할 경우 필요한 Kind만 후속 선언 PR에서 검토한다.

<a id="추가-data-인계--전체-v2-파일-수신과-b-수락-범위"></a>
### 현재 Data 인계와 연결 예산

C v2.2에서 Cloud·lab·Recovery는 Valkey 7.2 계열을 선택했고, 공개 CA는 `backend-database-ca`/`backend-redis-ca` **ConfigMap**으로 정정됐다. Runtime/Migration/Redis 목적 Secret3개와 비민감 `backend-config`는 유지한다. 엔진 선택·CA Kind 정정은 완료된 계약이며 실제 CA bytes/Hash·DNS/SAN·TLS/AUTH·지원 Client/Lua/RESP·업무 검증과 구분한다. [v2/Redis OSS7.1 당시 검토](https://github.com/seokpan/seokpan-hybrid-gitops/blob/fa3cea313e2cb1533d9703082619b085a3de25cc/handoff/OCP_FIRST_DEPLOYMENT.md)는 이력으로 보존한다. 이전 Redis7.2.4 시험을 Valkey PASS로 승계하지 않는다.

승인 Image Source46e와 App main2003의 Alembic Source head=`20260902_0002` 확인, 실제 Image의 자산/명령, DB `current` 결과는 각각 다르다. lab Schema가 이미 head이면 불필요한 DDL을 실행하지 않고, 필요할 때만 같은 Backend Digest·DB CA·Migration 전용 자격과 승인 action/deadline으로 단일 실행한다. 기존 PVC 없는 MariaDB는 재시작/삭제하지 않는다.

Cloud 목표 Backend3·surge1, Engine2·프로세스1에서 현재 기본 Pool5+overflow10은 Pod당30이라는 계산이 가능하나 실제 연결 상한/종료 겹침의 보장이 아니다. C v2.2의 Engine당3+2이면 Pod당10, 활성4+종료1·예약10의 시나리오는60이다. 이 후보는 미채택이며 실제 max_connections·예약·종료 중 연결·부하를 B/C가 확정하고 필요한 App Source→D 새 Build/Digest→활성화로 연결한다. 이 합의는 해당 Cloud App 활성화 조건이지 ROSA 첫 Plan·lab 모든 준비를 막는 조건이 아니다.

<a id="d-추가-공급-수신--db와-lab-redis-음성-case5"></a>
### DB·Valkey 공급과 독립 Image 검사

D의 DB DNS `mariadb.seokpan-app.svc`·SAN·인증서 10/31 만료 및 Migration300초 보고를 수신했다. 최종 CA/목적 자격/Schema·노드 연결은 별도 확인한다. Valkey용 `lab-redis-server-tls`, `lab-redis-server-auth`, `backend-redis-runtime` Secret과 `backend-redis-ca` ConfigMap의 공급 보고는 서버 선언/Ready와 다르다. `lab-redis.seokpan-argotest.svc`를 소비하고 기존 demo2/Argo Redis·DB/PVC는 보존한다.

D가 물은 음성 Case5는 실제 `db_admin` Secret을 Backend Deployment에 넣지 않고 **승인 Image의 순수 계정 검사 함수에 가짜 URL을 넣는 방식**으로 수행한다. 기존 cp-03의 승인 Image 캐시에서 네트워크를 끄고 실행하므로 lab Registry 경로·실제 DB·CA·Migration 자격을 기다리지 않는다. 아래는 D에게 제공할 절차이며 B가 실행하거나 실제 Image PASS로 판정한 결과는 아니다. Image의 Alembic head도 같은 실행에서 DB 접속 없이 확인한다. Podman은 계정과 rootful/rootless 모드에 따라 Image 저장소가 달라지므로 cp-03에서 승인 Image를 Pull한 것과 같은 계정·모드로 실행한다.

```bash
backend_image='harbor.seokpan.soldesk.store/seokpan-hybrid/backend@sha256:cbb7452c28f1dfe3533358916e8d0432cd65aa10865842451ab026972b55dae6'
podman run --rm -i --pull=never --network=none --read-only \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --env PYTHONDONTWRITEBYTECODE=1 --env PYTHONPATH=/app/src \
  --entrypoint /app/.venv/bin/python "$backend_image" - <<'PY'
from alembic.config import Config
from alembic.script import ScriptDirectory
from seokpan.connection_contract import DatabaseTarget
from seokpan.persistence.mariadb.connection import (
    DatabaseConfigurationError,
    validated_database_url,
)

heads = ScriptDirectory.from_config(Config('/app/alembic.ini')).get_heads()
if heads != ['20260902_0002']:
    raise SystemExit('FAIL: unexpected Alembic head')
print('PASS: image Alembic head=20260902_0002 (offline)')

target = DatabaseTarget.from_fields('negative-test.invalid', 3306, 'stone_game')
fake_url = 'mysql+asyncmy://db_admin:NOT_A_SECRET@negative-test.invalid:3306/stone_game'
for account in ('identity_svc', 'game_svc'):
    try:
        validated_database_url(fake_url, account, target)
    except DatabaseConfigurationError as error:
        if str(error) != f'database URL must use the {account} account':
            raise SystemExit('FAIL: wrong validation refusal') from None
        print(f'PASS: {account} runtime rejects db_admin URL before DB connection')
    else:
        raise SystemExit('FAIL: runtime accepted db_admin URL')
PY
```

승인 Digest·기존 Host·실행 계정/모드·시각·exit code와 비밀값을 제거한 출력만 #6/App #1에 기록한다. 실패하면 `FAIL` 메시지 원문을 함께 남기고, `FAIL` 메시지가 없으면 그 사실과 Podman/프로세스 오류를 비밀값 없이 기록한다. 캐시에 없으면 자동 Pull하지 않는다. Case5 PASS는 Runtime 계정 검사 거부의 범위이며 실제 TLS/GRANT/Ready 시험이 아니다. Case1~4와 DB `current`/Schema·실제 업무는 해당 lab 입력 수락 후 새 Run으로 확인한다.

## 1. 검토 대상과 변경 경계

- 최초 App Source 인계 기준은 전체 Commit **`c12b3d15a4dd2c806fac4326a9eb30ed6e8a81b3`**이다. [h-app PR #5](https://github.com/seokpan/seokpan-hybrid-app/pull/5)의 Source 병합과 D의 새 Build/Scan/Digest·lab 실행 수락은 구분한다. 이후 제공된 Image의 App SHA `46e21a74dd608b41f2c12a0a57d76bddfcf25949`와 수락 범위는 [인계 카드 §2-A](OCP_SOURCE_HANDOFF_20261005.md#2-a-d의-최종-harbor-image-인계-수신--실행-승인은-별도)를 따른다. 개인 작업환경의 미반영 변경은 B가 대조하고 보존한다.
- [h-gitops PR #9](https://github.com/seokpan/seokpan-hybrid-gitops/pull/9)·[PR #11](https://github.com/seokpan/seokpan-hybrid-gitops/pull/11)은 병합됐으며 App/lab/Recovery·Cloud 선언은 현재 `main`에 있다. **2026-10-05 최초 인계 기준**은 전체 Commit **`3dc624d4dc9a774a6207708bfd68248101890401`**이며, Harbor Image 참조를 연결한 [PR #13](https://github.com/seokpan/seokpan-hybrid-gitops/pull/13) 병합 기준은 **`fc175a7002ad567e9d5206b6e4b6642e8416eea2`**이다. `apps/base`와 `apps/overlays/lab`를 대조하고 실제 사용할 최종 전체 HEAD·Render·검사를 같은 개정으로 기록한다. 이전 Image/실습 성공을 새 조합 성공으로 사용하지 않는다.
- #11은 `main`으로 전환·Source 검토 후 병합됐고 #9/#11 작업 Branch는 삭제됐다. 삭제 Branch를 실행 참조로 쓰지 않고 검토된 전체 SHA를 사용한다. Cloud 선언 병합은 ROSA 생성·App 활성화·다중 Pod 업무 수락이 아니다. 병합 Source의 이번 OCP 인계 결과와 남은 실제 입력은 [2026-10-05 인계 카드](OCP_SOURCE_HANDOFF_20261005.md)를 따른다.
- lab Overlay의 `seokpan-argotest`는 D의 존재/managed-by·10/6 사용 보고를 수신한 대상이다. 이후 실행창과 B의 실효 권한·단일 관리 Owner·기존 객체 Diff는 적용 직전에 다시 확인한다. 기존 `seokpan-app`, 공유 Operator 영역, 1차 자원은 이번 시험이 임의로 변경·삭제할 범위에 넣지 않는다.
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
| lab Node → 사용할 Registry 경로 | TCP 443 접근·DNS·CA 신뢰·Pull 인증을 구분한다. 현재 Harbor 직접 경로는 미확보. 내부 Registry 복사/Index 보존·default SA Pull4건은 D 보고 수신. 최종 실행의 SA·보존/Pruner·권한/사용창은 직전 확인 | D 실제 경로/Registry 공급, 망·공유 Owner, B 소비 대조 | Image를 사용하는 Pod 기동. 제어 등록은 해당 권한·Owner·공유 사용 조건으로 별도 준비 |
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
