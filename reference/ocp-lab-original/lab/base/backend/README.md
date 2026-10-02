# Backend Runtime Desired State

이 디렉터리는 `application` Namespace의 Backend Kubernetes Desired State 기반을 관리합니다.

## 현재 단계

현재 [Deployment](deployment.yaml)는 `replicas: 2`를 선언합니다. A-10의 Provider·Frontend·Gateway 통합 기록은 [1차 종료 시점 상태](https://github.com/seokpan/seokpan-docs/blob/main/CURRENT_STATE.md)에서 확인합니다. 이 README는 현재 선언과 운영 계약을 안내하며, 추가 실행 검증의 완료 여부를 별도로 판정하지 않습니다.

- 두 Pod는 `kubernetes.io/hostname` 기준 `DoNotSchedule` Topology Spread를 사용해 두 Worker에 분산합니다.
- RollingUpdate는 `maxSurge: 0`, `maxUnavailable: 1`로 고정해 두 Worker가 모두 사용 중인 상태에서도 강제 분산 규칙과 교착되지 않고 한 Pod씩 교체합니다.
- PodDisruptionBudget `minAvailable: 1`은 Eviction API를 사용하는 계획된 축출에서 최소 한 Pod를 유지합니다.
- 현재 Image Digest는 [`kustomization.yaml`](kustomization.yaml)의 `images` 항목을 기준으로 합니다. 과거 검증 이미지의 Digest를 현재 값으로 복제하지 않습니다.
- Deployment는 `application/harbor-pull-secret`을 명시적으로 참조합니다.
- Argo CD Child Application `apps-backend`는 Root Application에 편입되어 `apps/backend`를 `main` 기준으로 관리합니다.
- 실제 DB URL 및 Credential은 Git에 포함하지 않습니다.

초기 활성화에서는 App #22 승인에 따른 Alembic `20260902_0002` 적용과 데이터 보존을 검증하고, Backend 1 Replica에서 승인 Image·공개 CA Mount, 실제 MariaDB 두 역할과 Redis Provider readiness, 세 Health Endpoint, Argo CD Healthy를 확인했습니다. 아래 초기 활성화 기록은 그 단계의 근거이며 현재 Replica 수나 모든 후속 검증의 완료를 대신하지 않습니다.

## Runtime 계약

- Deployment / Service: `backend`
- Container / Service Port: `8000`, name `http`
- Image: `harbor.seokpan.soldesk.store/seokpan/backend`
- Redis: `redis://redis.platform.svc.cluster.local:6379/0`
- Startup: `/health/startup`
- Liveness: `/health/live`
- Readiness: `/health/ready`
- `SEOKPAN_INSTANCE_ID`: Pod `metadata.name` Downward API

Production의 `/health/ready`는 시작 시 MariaDB 두 역할의 `SELECT 1`, Redis `PING`과 필수 Runner 조립이 성공한 뒤에만 200을 반환합니다. 각 Pod의 readiness와 별도로 두 Pod 사이 공유 상태·이벤트 전달은 실제 교차 요청으로 검증합니다.

## DB / Migration 경계

MaxScale TLS Listener와 App Client 계약은 `seokpan-infra#102`, `seokpan-app#50` 기준으로 확정되어 있습니다.

Backend가 사용하는 공식 DB 주소는 `db.seokpan.soldesk.store:3306`이며, Runtime DB URL은 `backend-db-runtime` Secret의 `SEOKPAN_IDENTITY_DATABASE_URL`, `SEOKPAN_GAME_DATABASE_URL` Key를 통해 전달합니다.

공개 Root CA 전달 계약:

```text
ConfigMap: seokpan-internal-ca
Key:       ca.crt
Mount:     /etc/seokpan/pki/ca.crt
Env:       SEOKPAN_DATABASE_CA_FILE=/etc/seokpan/pki/ca.crt
```

`database-ca-configmap.yaml`에는 Ansible Controller의 공식 Root CA `/etc/pki/seokpan-ca/ca.crt`에서 인계받은 공개 인증서만 포함합니다.

2026-09-09 인계된 인증서는 기존 공개키·SKI를 유지하고, critical Key Usage에 Certificate Sign·CRL Sign을 포함합니다.
새 인증서의 X.509 SHA-256 Fingerprint는 다음과 같습니다.

```text
28:EE:82:23:2C:08:E7:48:A6:65:D7:98:65:AA:BB:5A:58:53:BE:32:BE:28:29:DB:37:F1:EE:02:6C:87:2F:60
```

이전 지문 `A3:3B:2F:BB:16:2B:41:5C:C7:91:7E:9B:F6:4A:6C:00:8E:CD:47:16:97:C4:F0:6D:0B:CF:DC:BA:E2:34:5B:96`은 교체 전 이력입니다.
현재 파일 대조에는 위 신규 지문을 사용합니다. Root CA 유효기간은 2026-09-09 08:03:30 UTC부터 2036-09-06 08:03:30 UTC까지이며, 서비스 인증서의 365일 발급 기준과 구분합니다.

인계·검증 근거는 [Infra PR #163](https://github.com/seokpan/seokpan-infra/pull/163)과
[GitOps #39](https://github.com/seokpan/seokpan-gitops/issues/39)에서 연결합니다.
2026-09-09 Ansible Controller의 OpenSSL 3.5.7에서 MaxScale 설정 파일과 동일한 공개 인증서 사본을
신규 CA로 `-x509_strict -purpose sslserver -verify_hostname db.seokpan.soldesk.store` 검증하여 통과했습니다(exit 0).
명령·두 인증서 지문·원본/사본 파일 해시·실행 결과는 [검증 완료 댓글](https://github.com/seokpan/seokpan-gitops/issues/39#issuecomment-5602090338)에 기록돼 있습니다.
공개 CA 파일의 지문·확장·자체 서명 검증과 MaxScale 서버 인증서 검증, 실제 DB 연결은 서로 다른 결과입니다.
Harbor API 시험 성공을 Backend DB 연결 성공으로 대신하지 않습니다.

ConfigMap 파일 변경만으로 실행 중인 Pod의 `subPath` 파일이 갱신되지는 않습니다.
실제 적용 전에 Backend와 Migration 실행 상태를 확인하고, 가동 중인 Backend는 승인된 재기동 후 파일 지문·TLS·서비스 상태를 확인합니다.
실행 중인 Migration은 임의로 중단하거나 재실행하지 않고 작업 종료와 CA 전환 시점을 조율합니다.
새 Migration Job도 실행 전에 신규 CA를 확인하며, CA 검증을 위해 Migration을 실행하지 않습니다.
Backend가 실제로 비활성 상태라면 CA 교체를 위해 Replica를 늘리거나 불필요한 재시작을 하지 않습니다.
자세한 실행·완료 기준은 [GitOps #39](https://github.com/seokpan/seokpan-gitops/issues/39)에서 관리하며 이 파일 변경만으로 해당 Issue를 종료하지 않습니다.

CA Private Key와 서비스 Private Key는 이 Repository에 포함하지 않습니다.

`SEOKPAN_MIGRATION_DATABASE_URL`과 `db_admin` Credential은 일반 Backend Deployment에 주입하지 않습니다.

DB Credential은 Runtime과 Migration의 권한 경계를 Kubernetes Secret에서도 분리합니다.

Runtime DB Secret:

    Secret: backend-db-runtime
    Namespace: application
    Consumer: Backend Deployment

    Keys:
    - SEOKPAN_IDENTITY_DATABASE_URL
    - SEOKPAN_GAME_DATABASE_URL

Migration DB Secret:

    Secret: backend-db-migration
    Namespace: application
    Consumer: 승인된 One-shot Migration Workload만

    Key:
    - SEOKPAN_MIGRATION_DATABASE_URL

세 DB URL은 모두 공식 Endpoint `db.seokpan.soldesk.store:3306`과 Database `stone_game`을 사용하며,
각각 `identity_svc`, `game_svc`, `db_admin`의 기존 계정 경계를 유지합니다.

실제 Password와 전체 DB URL은 Git에 저장하지 않습니다. GitOps는 Secret 이름·Key와 소비 Workload의
참조 계약만 관리합니다.

실제 Kubernetes Secret 값의 공급은 Ansible + Vault 방식을 사용하며,
공급 자동화는 `seokpan-infra#150`에서 관리합니다.

승인형 One-shot Migration Job 실행 구조와 자산은 `seokpan-gitops#44`에서 관리합니다.
실행 자산은 `apps/backend/migration/`에 보관하며 일반 `apps/backend/kustomization.yaml`에는 포함하지 않아 Argo CD Auto-Sync 대상과 분리합니다.
실제 Migration 실행은 `seokpan-infra#150`의 Migration Secret 공급, 승인된 Backend Image Digest, DB 사전 Gate 완료 이후에만 수행합니다.

## Image 갱신 계약

CI는 `git-<main-commit-12자리>` Tag로 Harbor에 Push한 뒤 실제 Digest를 확인합니다.

[App 이미지 파이프라인](https://github.com/seokpan/seokpan-app/blob/main/Jenkinsfile.image-pipeline)이 검증 이미지를 확정하고, [Promotion 스크립트](https://github.com/seokpan/seokpan-app/blob/main/scripts/promote_gitops.py)가 변경 대상 컴포넌트의 GitOps PR을 생성합니다. 팀원 리뷰·승인·Merge 후 Argo CD가 변경된 선언을 동기화합니다. 현재 Digest는 `kustomization.yaml`에서 확인하며 자동 PR 생성과 배포 승인을 구분합니다.

`latest`는 사용하지 않습니다.

## Runtime 활성화 Gate

아래는 초기 1 Replica 활성화와 2 Replica 전환 당시의 체크포인트입니다. 현재 실행할 일괄 지시나 현재 미완료 목록이 아니며, 당시 확인한 값·Revision과 전환 계획을 보존합니다.

1. Backend Container Image 존재 — 완료
2. Harbor Push 및 실제 Digest 확인 — 완료
3. `seokpan-app#50`의 TLS Client 구현 및 정적 검증 — 완료
4. Infra 인계값과 저장소 공개 CA Fingerprint 일치 — 완료
   - 실제 소비 Pod의 CA Mount와 MaxScale TLS 연결을 1 Replica에서 확인
5. MariaDB·Redis Provider 조립 — 완료
6. Runtime DB Secret 계약 확정 — 완료
   - Secret 공급 자동화·담당자 검증: [Infra #150](https://github.com/seokpan/seokpan-infra/issues/150) 완료. 실제 Cluster Secret의 Key 구조도 활성화 전 확인
7. One-shot Migration Kubernetes 실행 구조 및 `20260902_0002` 적용 — 완료
   - App #22 승인 참조로 실행했으며 적용 전후 Schema 분류와 기존 업무 행 보존을 확인
8. Production 시작 시 MariaDB 두 역할과 Redis 연결 Probe 구현·실제 Cluster 성공 — 완료
9. 초기 `replicas: 1` Smoke Test — 완료
   - Pod Ready·Restart 0, Image ID, CA Mount, `/health/startup`·`/health/live`·`/health/ready`, Argo CD Healthy 확인
10. Argo CD Child Application 연결 — 완료
    - `apps-backend`가 Root Application에 편입되어 `apps/backend`를 `main` 기준으로 관리하며 `prune: true`, `selfHeal: true`를 사용합니다.
    - 1 Replica 활성화 Revision `843dbea031b6549b9d056a35d60334d23a0c38b7`의 Sync/Health를 확인했습니다.
11. `replicas: 2` 공유 상태 검증 — 당시 롤링 전략 보완 후 재개 계획
    - 최초 적용에서 기존 두 Pod가 두 Worker를 점유한 채 Surge Pod를 먼저 생성해 `DoNotSchedule`과 교착되는 것을 확인했습니다. 기존 두 Pod는 Ready 상태를 유지해 서비스 장애는 없었습니다.
    - 당시 재개 계획은 `maxSurge: 0`, `maxUnavailable: 1` 적용 후 두 Worker 분산, PDB, 두 Pod Ready, 한 Pod에서 발급한 Guest Session의 다른 Pod 조회·폐기, 폐기 후 원 Pod 거부를 확인하는 것이었습니다.

초기에는 이 2 Replica 교차 검증을 Frontend·Gateway 활성화의 선행조건으로 두었습니다. 후속 통합 기록은 상단의 1차 종료 시점 상태에서 추적하며, 이 과거 체크포인트를 현재 Frontend·Gateway 미활성 상태로 읽지 않습니다.

## 후속 연결

- `seokpan-gitops#58` — Backend/Frontend Child Application Root 편입 및 Sync 검증
- `seokpan-gitops#44` — 승인형 One-shot Migration Kubernetes Job 실행 구조
- `seokpan-gitops#35` — Backend MaxScale TLS 공개 CA 주입 구조
- `seokpan-app#50` — Backend/Alembic MaxScale TLS Client
- `seokpan-gitops#7` — Redis 실제 Backend 연결
- `seokpan-app#22` — Alembic Provider Gate
- `seokpan-infra#102` — MaxScale TLS Listener 완료
- `seokpan-infra#138` — TLS SAN 변경 감지 자동화 완료
- `seokpan-gitops#27`, `seokpan-app#40` — Jenkins → Harbor → GitOps PR
- `seokpan-gitops#29` — Backend/Frontend Runtime Desired State 기반
