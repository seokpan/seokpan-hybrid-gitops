# OCP Source 인계 카드 — 병합 후 다음 실행 (2026-10-05)

**목적:** 병합된 App와 GitOps 선언을 D의 실제 OCP 배포와 C의 Data 검토에 연결한다. 이 카드는 Source 제출·입력 수신·실제 실행을 따로 표시한다. 상세 절차는 [OCP 최초 배포 안내](OCP_FIRST_DEPLOYMENT.md), B 원본은 [GitOps #10](https://github.com/seokpan/seokpan-hybrid-gitops/issues/10), 개인 상위는 [Docs #21](https://github.com/seokpan/seokpan-hybrid-docs/issues/21)이다.

## 1. 현재 제출한 것과 아직 확인하지 않은 것

| 구분 | 이번 결과 | 다음 담당 |
|---|---|---|
| Source | App `c12b3d15a4dd2c806fac4326a9eb30ed6e8a81b3`; GitOps `3dc624d4dc9a774a6207708bfd68248101890401` / Tree `24a6c69fd22b8065bc537b5c77aef10336c9026b`. 이 병합 기준의 GitOps 49개 Blob·권한을 원격 manifest와 대조, #11 검토 Tree와 동일. 인계 PR artifact의 실제 checkout SHA/Tree는 artifact manifest에서 별도 확인 | B가 Source 묶음을 제출. D/C 수신·보완은 각 원 이슈에 기록 |
| Native Source/Render 검사 | 병합 HEAD의 [Run 37323213534](https://github.com/seokpan/seokpan-hybrid-gitops/actions/runs/37323213534), Job 111807272347: Kustomize v5.7.1·Python 3.12·PyYAML 6.0.2, App18+OCP6+Release6+Cloud9 = **39 PASS**, skip0. 테스트가 실제 Kustomize Build 후 객체·참조·보류 조건 검사 | 실제 Cluster Admission·Image Pull·Data 연결·업무는 D/B/C 별도 |
| Render 인계 파일·Hash | 병합 HEAD의 기존 Workflow는 Build 결과 본문/Hash를 artifact로 보존하지 않았다. 이번 인계 PR은 기존 39개 검사 뒤 **8개 OCP 진단 Render·SHA256·객체 목록·실제 checkout SHA/Tree**를 별도 artifact로 보존하는 단계만 추가한다. 새 PR Native CI·artifact의 실제 결과는 #10/PR에 연결하며 그 확인 전 완료로 쓰지 않는다 | B가 실제 artifact를 검증·제출, D/C 수신·보완 별도 |
| 실제 lab 상태 | 기존 #5 기록상 공유 Controller `openshift-gitops`, 대상 `seokpan-argotest`, managed-by 라벨 유지. 이번 작업에서는 OCP API를 조회하지 않았으므로 현재 실행 상태·권한·Owner·사용 승인을 확인했다고 쓰지 않음 | D와 공유 Owner가 적용 직전 재확인 |
| 새 조합 실제 실행 | 새 승인 Image/Scan/Digest·lab/Secret/CA/Schema 수락 기록을 아직 확인하지 못함. OCP Apply/Sync·Registry 조회·Migration/DDL·AWS 호출 **NOT RUN** | 최소 입력 수락 → 별도 활성화 개정 → 최초 수동 Sync·새 Run |

#9/#11 Branch는 삭제됐으므로 위 SHA와 파일 링크를 사용한다. 이번 PR은 인계 문서와 검사 결과 보존만 바꾸며 App·플랫폼·Migration 선언은 병합 기준과 같다. artifact는 실제 checkout SHA/Tree를 기록하므로 문서 기준 SHA와 구분하고, 실행할 때는 사용할 전체 SHA와 선언을 다시 대조한다. 개인 clone의 미push/미커밋 변경 확인은 본인 환경에서 해야 한다.

## 2. 코드가 OCP에 반영되는 실제 경로

`App 코드 → D Build → 승인 Image Digest → B lab 선언 입력 → D가 정확 SHA/Path로 Application 등록·수동 Sync → OCP가 Image Pull·Pod 기동 → B/C/D 검증`.

- **Image**는 실행할 프로그램과 파일을 묶은 것이다. App PR 병합은 Image 생성이나 OCP 교체가 아니다.
- **Manifest**는 어떤 Image·설정·개수로 실행할지 적은 YAML이다. `apps/base` 공통 선언에 `apps/overlays/lab`의 OCP 대상·Route·설정을 합친다.
- **Render**는 Kustomize가 위 입력을 최종 YAML로 계산하는 작업이다. Render만 하면 클러스터는 바뀌지 않는다.
- **Application**은 Argo CD에 Repo·SHA·Path·대상을 알려주는 객체다. 현재 Source는 수동 최초 Sync이며 자동 Sync가 없다. 따라서 GitHub 병합만으로 이 OCP 새 조합이 배포됐다고 볼 수 없다.
- **Sync**를 승인·실행하면 Argo CD가 그 선언을 OCP API에 적용하고, OCP가 Image를 내려받아 Pod를 만든다. `Ready`와 업무 시험으로 실제 결과를 판정한다.

ROSA는 AWS에서 제공하는 별도 OpenShift 클러스터다. 현재 `cloud` 선언과 Infra의 ROSA 코드는 준비됐지만 이 코드 병합만으로 ROSA가 생성되거나 기존 OCP가 ROSA로 바뀌지 않는다.

## 3. 지금 빠진 최소 입력과 바로 풀리는 실행

| 필요한 입력·수신 기록 | 공급·수락 담당 | 막는 실행 | 병행 가능한 B 작업 |
|---|---|---|---|
| App SHA → FE/BE 승인 Image, Registry별 전체 Digest·Platform·Build/Test/Scan·실제 Pull 방식/CA | D: [App #2](https://github.com/seokpan/seokpan-hybrid-app/issues/2) | 새 Image 활성화·Image/SCC/업무 Case | Manifest·Case·Image Mapping 항목 준비 |
| Context·Caller/RBAC·Controller/Project/Application·Namespace Owner·실제 managed-by·Repo 인증·4조 공지/공유 사용 수락 | D/공유 Owner: [GitOps #5](https://github.com/seokpan/seokpan-hybrid-gitops/issues/5) | 실제 Application 등록·변경·Sync | 기존 승인 `reuse` 경로와 제한 Project 비교. 새 Namespace 자동 생성 금지 |
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

이미 준비한 GitOps clone에서 개인 변경을 먼저 보존하고, 별도 detached worktree로 같은 SHA를 확인한다. 아래는 Source만 읽고 로컬 파일을 쓰는 명령이다. `/absolute/new/...` 경로는 실제 별도 경로로 바꾼다. 출력에는 미해결 입력이 남으므로 **Apply/Sync 금지**다.

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

Kustomize는 기존 검사와 같은 v5.7.1을 쓴다. 이번 인계 PR의 Native Workflow도 위 **8경로**를 Build한다. artifact의 `source-manifest.json`에 실행 SHA/Tree·도구 개정·Path별 실제 객체 개수·종류/이름/Namespace·YAML SHA256이 있고 `SHA256SUMS`로 내려받은 8개 파일을 대조할 수 있다. `README.md`는 **NOT DEPLOYABLE·Runtime NOT RUN** 범위를 명시한다. 기존 Native 검사 자체의 App base/lab/Recovery 3경로 + OCP6경로 =9경로와, 이번 OCP 인계 artifact의 base/lab 2경로 + OCP6경로 =8경로는 다른 범위다.

artifact 보존은 **7일**이며 Source/인계 검토용이다. GitHub artifact 다운로드에 로그인이 필요할 수 있으므로 D/C가 받을 보존 위치와 읽은 개정을 별도로 기록한다. 보호된 Secret/CA 값·Runtime Run/Index·DB Backup/Recovery Release 보존 정책과 별개다. 만료 뒤에는 수락한 정확 SHA에서 재생성할 수 있다. 실제 PR CI 결과·artifact 다운로드 대조·D/C의 읽은 개정과 수신 여부를 #10에 기록한다. 로컬 Native Kustomize 부재와 공식 바이너리 다운로드 timeout 때문에 로컬 Render는 실행하지 않았으며 합성 Render/Hash로 대신하지 않는다.

현재 Source의 실제 예는 아래와 같다.

```yaml
# apps/overlays/lab/kustomization.yaml
namespace: seokpan-argotest
images:
  - name: seokpan-backend
    newName: lab-registry-input-required.invalid/backend
    newTag: INPUT_REQUIRED
```

`apps/base/backend.yaml`·`frontend.yaml`는 `replicas: 0`이다. 승인 Image가 수락되기 전 입력 대기 상태라는 뜻이며, 이 상태의 Synced를 실행 성공으로 세지 않는다. 활성화는 승인 Digest/설정·같은 Image의 Migration·필요 Schema를 대조한 별도 개정으로 만들고 `make release-manifest` 입력 검사를 통과한 뒤 최초 수동 Sync한다.

## 5. 실제 시험 Case — 기대와 실제를 따로 쓰기

| Case | 기대·확인할 조건 | 이번 실제 결과 |
|---|---|---|
| 대상/Owner/수동 Sync/삭제 보호 | Context·SHA/Path·Namespace·Project 범위·단일 Owner. App 자동 Sync/Prune 보류, finalizer 없는 수동 정리·보호 대상 분리 | **NOT RUN**, D/Owner 현장 수락 대기 |
| Image Pull·임의 UID·쓰기 | 승인 Digest 실제 Pull, 고정 UID/권한 확대 없이 기동·CA읽기·`/tmp`쓰기·ReadOnlyRootFS | **NOT RUN**, D 새 Image/lab 입력 대기 |
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
