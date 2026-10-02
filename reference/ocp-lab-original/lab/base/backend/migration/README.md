# Backend One-shot Migration

이 디렉터리는 `seokpan-app#22`의 승인형 Alembic Migration Gate를 Kubernetes `Job`으로 실행하기 위한 자산을 관리합니다.

이 자산은 일반 Backend Desired State와 분리되어 있으며 `apps/backend/kustomization.yaml`에 포함하지 않습니다.

따라서 일반 Argo CD Auto-Sync가 Migration Job을 자동 생성하거나 DDL을 실행하지 않습니다.

## Kubernetes Job 정책

각 승인 실행은 새로운 Job으로 생성합니다.

    completions: 1
    parallelism: 1
    backoffLimit: 0
    restartPolicy: Never

`backoffLimit: 0`은 실패한 Schema 변경을 Kubernetes가 자동 재시도하지 않도록 하기 위한 정책입니다.

이 구조를 exactly-once 보장으로 해석하지 않습니다.

실패 시 기존 Job을 수정하거나 재사용하지 않고 DB 상태 확인과 새로운 승인 후 새로운 Job을 생성합니다.

## Credential

Migration Job은 다음 Secret만 소비합니다.

    Secret: backend-db-migration
    Key: SEOKPAN_MIGRATION_DATABASE_URL

다음 Runtime Credential은 소비하지 않습니다.

    backend-db-runtime
    SEOKPAN_IDENTITY_DATABASE_URL
    SEOKPAN_GAME_DATABASE_URL

실제 Secret 값 공급은 `seokpan-infra#150`의 책임입니다.

## CA

Migration Job은 기존 공개 Root CA 계약을 재사용합니다.

    ConfigMap: seokpan-internal-ca
    Key: ca.crt
    Mount: /etc/seokpan/pki/ca.crt
    Env: SEOKPAN_DATABASE_CA_FILE=/etc/seokpan/pki/ca.crt

CA Private Key와 MaxScale Service Private Key는 사용하지 않습니다.

## Image

별도 Migration Image는 만들지 않습니다.

실제 Migration 실행에서는 반드시 검증된 Backend Image Digest를 사용합니다.

    harbor.seokpan.soldesk.store/seokpan/backend@sha256:<verified-digest>

`git-pending`, `latest` 또는 이동 가능한 Tag는 실제 실행에 사용하지 않습니다.

Private Backend Image Pull에는 일반 Backend Deployment와 같은
`application/harbor-pull-secret`을 명시적으로 사용합니다. 이 Secret은
Application Runtime 전용 pull-only Harbor Robot으로 공급하며 CI Push/API
Credential을 재사용하지 않습니다.

## 지원 Action

    current
    stamp-baseline
    upgrade-head

Mutation Action은 다음 두 가지입니다.

    stamp-baseline
    upgrade-head

Mutation Action은 반드시 승인 Reference를 요구합니다.

Renderer는 Mutation Action에 대해 다음 App Gate 인자를 생성합니다.

    --execute
    --approval-ref seokpan/<repo>#<issue-number>:issuecomment-<comment-id>

Application의 `seokpan-migration-gate`가 Container 내부에서 다시 검증하므로 Renderer는 Application Gate를 대체하지 않습니다.

## Render 예시

### Read-only current

    python3 apps/backend/migration/render-job.py \
      current \
      --image 'harbor.seokpan.soldesk.store/seokpan/backend@sha256:<verified-digest>' \
      --output /tmp/backend-migration-current.yaml

### Baseline stamp

    python3 apps/backend/migration/render-job.py \
      stamp-baseline \
      --image 'harbor.seokpan.soldesk.store/seokpan/backend@sha256:<verified-digest>' \
      --approval-ref 'seokpan/seokpan-gitops#44:issuecomment-1234567890' \
      --output /tmp/backend-migration-stamp.yaml

### Upgrade head

    python3 apps/backend/migration/render-job.py \
      upgrade-head \
      --image 'harbor.seokpan.soldesk.store/seokpan/backend@sha256:<verified-digest>' \
      --approval-ref 'seokpan/seokpan-gitops#44:issuecomment-1234567890' \
      --output /tmp/backend-migration-upgrade.yaml

`approval-ref`는 승인된 GitHub Issue Comment를 가리키는 다음 형식을 사용합니다.

    seokpan/<repo>#<issue-number>:issuecomment-<comment-id>

예:

    seokpan/seokpan-gitops#44:issuecomment-1234567890

Approval Reference 자체에는 실행 상세나 Credential을 중복 기록하지 않습니다.
참조되는 승인 Comment가 최소 다음 Evidence를 보유해야 합니다.

    Action
    실행 대상
    승인 시각
    Backend Image Digest
    사전 검증 결과
    승인자

`approval-ref` 및 참조되는 승인 Comment에는 다음 값을 포함하지 않습니다.

    Password
    DB URL
    Secret Value
    Token
    Private Key

## 실행 전 Gate

실제 Mutation 실행 전에 최소 다음을 확인합니다.

1. 승인된 Action
2. Approval Reference
3. `seokpan-infra#150` 완료
4. `backend-db-migration` Secret 존재 및 Key 구조
5. 검증된 Backend Image Digest
6. 해당 Image에 Migration Gate와 Alembic 자산 포함
7. DB 상태
8. Replication 상태
9. Backup / Restore 가능 상태
10. CA 준비 상태
11. 다른 Active Migration Job 부재

Active Job 확인 예:

    kubectl get jobs -n application \
      -l app.kubernetes.io/name=backend-db-migration \
      -o custom-columns='NAME:.metadata.name,ACTIVE:.status.active,SUCCEEDED:.status.succeeded,FAILED:.status.failed'

Active Migration Job이 있으면 새로운 Mutation Job을 생성하지 않습니다.

## API 검증

실제 DDL을 수행하지 않고 Kubernetes API의 CREATE 요청만 검증합니다.

    kubectl create --dry-run=server -f /tmp/backend-migration-<run>.yaml

server-side dry-run 성공은 실제 Migration 성공을 의미하지 않습니다.

## 실제 실행

모든 승인과 선행 Gate가 완료된 경우에만 새로운 Job을 생성합니다.

    kubectl create -f /tmp/backend-migration-<run>.yaml

완료되거나 실패한 기존 Job에 `kubectl apply`하여 재사용하지 않습니다.

## 실패

    Migration Job Failed
    → Backend Runtime 활성화 Gate 중단
    → Job 상태와 Log 확인
    → DB 상태 확인
    → Replication 확인
    → Rollback / Restore 필요 여부 판단
    → 원인 해결
    → 새로운 승인
    → 새로운 Job 생성

여기서 Backend Runtime 활성화 Gate 중단은 별도 Controller가 자동으로 Rollout을 막는다는 의미가 아닙니다.

현재 프로젝트에서는 Migration 성공과 후검증을 Backend Runtime 활성화의 명시적 선행조건으로 운영합니다.

## 완료 판정

Job `Succeeded`만으로 Migration 완료를 선언하지 않습니다.

실제 실행 후 최소 다음을 확인합니다.

    Job terminal status
    Alembic current
    Replication
    MaxScale Read/Write
    기존 데이터 보존

실제 Migration 결과와 Backend Provider E2E 완료는 별도로 기록합니다.

## 관련

- `seokpan-gitops#44`
- `seokpan-gitops#40` / PR #42
- `seokpan-infra#150`
- `seokpan-app#22`
- `seokpan-app#50`
- `seokpan-gitops#35` / PR #36
