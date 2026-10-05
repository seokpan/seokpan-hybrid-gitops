# OCP-lab 첫 Source 인계

이 경로는 승인 구조를 연결하는 **기동 보류 Source 리뷰 후보**다. 실제 Controller Namespace/Instance·Owner·권한·Revision·Image/Secret/Schema 입력과 그 대상의 검토 전에는 Apply/Sync하지 않는다. `gitops-controller-input-required`, `GITOPS_REVISION_INPUT_REQUIRED`는 실제 환경을 관측한 값이 아니다. Application 이름은 검토용 후보이며 기존 같은 객체의 이름·Owner를 먼저 대조한다.

[h-gitops Issue #5](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5)와 [D 리뷰](https://github.com/seokpan/seokpan-hybrid-gitops/pull/9#pullrequestreview-5413591924)는 공유 Controller Namespace `openshift-gitops`, 대상 `seokpan-argotest`의 managed-by 유지, 4조 사전 공지를 기록한다. 실제 적용 직전에 D/공유 Owner가 Instance·Context/권한·기존 라벨 값/Controller 일치·공유 사용 수락을 다시 확인한다. 이 Source 작업은 Runtime 조회·공지 발송·실제값 반영이 아니다. 새 Namespace는 managed-by 필요 값·지원 동작·생성/관리 Owner까지 확인하며 추정 라벨을 넣지 않는다.

## 경로 선택과 단일 Owner

| 상황 | 선언 원본 | 먼저 확인할 것 |
| --- | --- | --- |
| 기존 승인 Project/Application 사용 | `reuse/`는 대조용 Application 후보; 승인 기존 객체를 우선 사용 | 실제 Controller/Project/Application과 허용 Repo·Namespace·종류·권한·Owner. 기존 Application이 같은 App를 관리하면 후보를 추가 등록하지 않음 |
| 새 격리 Root가 필요하고 Namespace는 기존 Owner 소유 | `bootstrap/` → `root/` | Infra의 설치/Root 최초 등록 예외 후 GitOps로 책임 인계. Root에는 AppProject/Application만 있음. 기존 Namespace에 추적 Label/권한을 새로 덮어쓰지 않음 |
| 새 Namespace 생성도 승인됨 | 선택 경로 `new-namespace/` → `platform/ocp-lab/new-namespace` | Namespace가 없고 해당 Owner가 이 생성/보호를 수락한 때만 사용. 기본 Root에 포함하지 않음. Platform은 수동 Sync |

Operator Subscription/OperatorGroup은 Infra 원본이며 여기서 설치하지 않는다. Secret 값/Object·CA 공급은 별도 Owner다. AppProject는 고정 Repo·목적 Namespace·Resource 종류만 허용하며, App Project는 Namespace/Secret/Job/PVC/Operator를 관리하지 않는다. Namespace 생성 권한은 선택 Platform Project에만 있으며 실제 Controller/RBAC와 이름 제한은 환경 Owner가 확인한다.

`reuse`의 기존 Project가 `default`처럼 넓다면 `root/app-project.yaml`의 제한 Project 후보와 실효 허용 범위를 비교한다. 제한 Project를 기존 Controller/등록 경로에서 사용하는 선택도 가능하며 새 전체 Root를 먼저 요구하지 않는다. 실제 Project 등록 원본·단일 Owner·RBAC와 Application의 Project 참조 변경을 D/Owner가 수락해야 한다. 기존 Application과 새 후보가 같은 App를 동시에 관리하지 않는다.

## 검사와 실제 순서

`make test`는 기존 App/Recovery와 새 lab 제어 선언의 Source 경계를 검사한다. 진단 Render는 다음과 같다. 출력은 활성 Release나 실제 Admission/보호 성공 증거가 아니다.

```sh
kustomize build clusters/ocp-lab/bootstrap
kustomize build clusters/ocp-lab/root
kustomize build clusters/ocp-lab/reuse
kustomize build clusters/ocp-lab/new-namespace
kustomize build platform/ocp-lab/new-namespace
kustomize build operations/ocp-lab/migration
make preview ENVIRONMENT=lab
```

1. D/공유 Owner의 실제 Context·Controller 버전/CRD·권한·객체 Owner와 경로 하나를 수락한다. Repo의 전체 Commit을 고정하고 실제 namespace/revision을 검토한 별도 변경으로 반영한다.
2. 필요한 경우에만 Infra 최소 설치/Root 최초 등록, Root/필요 Platform 수동 Sync. 새 Child Application 등록과 그 App 객체의 Sync는 별개다.
3. App는 0 Replica/입력 대기·수동 Sync를 유지한다. Secret/CA·새 Image·DB 목적 대상/Schema를 확인하고 필요한 Migration만 별도 단일 실행한다.
4. 승인한 동일 Source/Image/설정 조합의 활성화 변경 후 App 최초 수동 Sync. Ready·Client/TLS/AUTH·FE/API/WSS·업무·종료를 실제 새 Run에 기록한다.
5. 수락 후 별도 변경에서 App AutoSync/SelfHeal을 검토한다. Root/Platform 수동·자동 Prune 보류를 유지한다.

모든 후보 Application은 autoSync·삭제 finalizer·강제 Replace/Force를 넣지 않는다. `FailOnSharedResource=true`는 Argo 추적 충돌을 검출하는 보조이며, 추적되지 않는 기존 객체나 외부 Apply Owner를 모두 판별하는 보장은 아니다. 외부 Owner 대조가 필요하다. 보호 객체의 `Prune=false,Delete=false`는 Argo 동작을 제한하는 선언이며 직접 Namespace 삭제나 다른 Controller/사용자 삭제를 막는 보장은 아니다. 실제 격리된 Case로 별도 확인한다.

## 정리 방법과 범위

현재 finalizer 없는 Application을 삭제하면 배포 리소스가 남는다. 기본 정리는 결과/Release 보존·공유 사용 종료·Owner 수락 후 Sync/SelfHeal과 재등록 경로를 보류하고, Application 등록 해제와 **`seokpan-argotest`의 이 App 관리 객체만** 수동 정리하는 방식이다. 삭제 전/후 Deployment/Service/Route/생성 ConfigMap 목록과 잔존을 기록하고 공유 Namespace/Secret/CA·DB/Redis·Operator·1차/복구 자산을 보호한다.

기존 #5의 cascade 절차를 사용할 대안은 실제 Argo 동작·보호 annotation·관리 객체 범위를 대조한 **별도 승인 변경으로 해당 lab App 하나에만** finalizer를 적용하는 경우다. Root/Platform·공유 Namespace까지 cascade를 확대하지 않으며 현재 Source는 이 변경을 하지 않는다. 수동 정리와 대안의 기대/실제·미수락/미실행 상태는 [인계서 Cleanup Case](../../handoff/OCP_FIRST_DEPLOYMENT.md#실습-정리-방법-선택)와 #5/새 Run에 기록한다.

## Migration은 App Sync Hook이 아니다

`operations/ocp-lab/migration`은 App/Root 경로에 포함하지 않은 별도 suspended Job 후보다. App Image의 실제 `seokpan-migration-gate`와 `/app` 자산을 사용한다. 기본 action은 `current`이고 `--execute`는 없다. `suspend: true`, `parallelism/completions: 1`, `backoffLimit: 0`을 유지한다. 이것만으로 중복 실행 불가능을 보장하지는 않는다.

실제 Job은 DB Host/Name·Image Digest·사용 ConfigMap의 Render된 hash 이름·Migration Secret/CA·Pull·권한·최대 실행 시간·유일한 Run 이름과 수행자를 확인한 별도 검토본으로 만든다. 설정은 App와 동일한 비민감 대상 계약을 사용하되 Runtime 자격을 넣지 않는다. DB 쓰기는 C의 필요성/Schema·Backup·대상 수락 후에만 `stamp-baseline` 또는 `upgrade-head`와 `--execute --approval-ref`를 명시한다. 기존 Schema라면 불필요한 DDL을 실행하지 않는다. 실패/Job 재생성/재시도 전에 대상과 기존 결과를 다시 확인한다. Suspended Job을 App 활성화로 오인하지 않는다.

후보 Job의 `activeDeadlineSeconds: 300`은 **기동 보류·읽기 전용 `current` 후보의 제한 상한**이다. 실제 DB 크기·Lock·Action의 소요와 DB 쓰기 안전성/RTO를 측정한 값이 아니다. 실제 실행은 C가 수락한 Action별 deadline을 별도 활성화 개정에 고정한다. deadline 초과/실패 후 Schema·DB 작업이 취소됐다고 추정하거나 새 Job으로 바로 반복하지 않는다. 대상·DB/Schema 상태·원 결과·후속 처리 수락을 먼저 확인한다.

App main `c12b3d15a4dd2c806fac4326a9eb30ed6e8a81b3`의 실행 경로를 대조했다. `backend/src/seokpan/persistence/mariadb/migration_gate.py`의 `run`은 `MigrationSettings`와 DB CA만 사용한다. 이 Settings는 `DatabaseTargetSettings`를 상속해 Redis 키를 소비하지 않으며, `backend/migrations/env.py`도 같은 MigrationSettings·DB engine/대상·models만 사용한다. 따라서 이 Job의 공유 ConfigMap에 `SEOKPAN_REDIS_CA_FILE`이 있어도 **현재 Migration 실행은 Redis 설정/CA를 로드하지 않아 Redis CA Mount가 필요하지 않다**. 실제 Job의 App Image가 이 Source와 같은 Digest인지 확인하며, 이 경로가 바뀌면 설정/CA 소비를 다시 대조한다.

활성 lab Render와 별도 Job Render는 다음 Source 입력 검사로 같은 Backend Digest·대상 Namespace·ConfigMap Hash/DB 대상·DB CA·별도 Migration 자격·Action/deadline을 대조한다. 경로는 해당 개정으로 바꾸고 `REVIEWED_MIGRATION_DEADLINE_SECONDS`에는 C가 수락한 정수 초 값을 먼저 지정한다.

```sh
python3 tools/check_migration_manifest.py --app-manifest /separate/new/path/lab.yaml --job-manifest /separate/new/path/migration.yaml --reviewed-deadline-seconds "$REVIEWED_MIGRATION_DEADLINE_SECONDS"
```

도구에 초 값·승인 Ref를 넣었다는 사실은 실제 C의 수락·단일 실행·DB 안전성·Runtime 성공을 증명하지 않는다. 이 도구는 실행/Apply하지 않으며 Job은 실제 입력·승인한 수동 실행까지 보류한다.

## 리뷰와 남은 범위

Source 리뷰·병합은 Image/lab 수락·실제 활성화·전체 TH 완료와 다르다. 현재 인계 입력과 실행 Case는 [첫 배포 인계](../../handoff/OCP_FIRST_DEPLOYMENT.md)를 따른다. 이 최소 묶음은 전체 Cloud Root/NP/UWM·Recovery Bundle·Infra Operator 설치 코드 완료를 주장하지 않는다. 그 남은 범위는 기존 Issue #10에 유지한다.

참고: [Argo Sync Options](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/), [Argo Projects](https://argo-cd.readthedocs.io/en/stable/user-guide/projects/), [Kubernetes Job](https://kubernetes.io/docs/concepts/workloads/controllers/job/). 실제 lab 버전/CRD 지원은 적용 직전 별도 확인한다.
