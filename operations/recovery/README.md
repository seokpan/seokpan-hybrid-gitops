# Recovery 진입·Migration 후보 (HELD)

작성자: 최유준 / 작성 날짜: 2026/10/16

이 폴더는 Recovery Namespace(`seokpan-recovery`)의 **Migration 후보와 보류 후보**를 둔다. 실제 Apply/Sync/복원은 포함하지 않는다.

| 경로 | 역할 | 상태 |
| --- | --- | --- |
| `migration/` | suspended `current` Job + 전용 NetworkPolicy. 단독 빌드 대상 아님 | HELD |
| `compose/` | App Overlay + `migration/`을 한 번에 합성해 `backend-config` hash·Backend digest를 공통 변환 | 검토용 |
| `candidates/ws-timeout.yaml` | NGF `ProxySettingsPolicy` WS read/send 3600s 후보. 어떤 Kustomization에도 미포함 | A/D CRD 확인 전 보류 |
| `apps/overlays/recovery-run/` | Valkey 보존 전용 산출물: 정확히 StatefulSet·Service·ConfigMap 3개만 출력(FE/BE·Gateway·Route·NP 제외). 전체 Recovery 적용용이 아님 | live Diff 확인 전 적용 금지 |
| `apps/overlays/recovery-full-run/` | 전체 앱 실행용 후보: 전체 산출물에서도 Valkey를 1개로 유지(replicas 1 + runtime-config 참조 live 대응). FE/BE 0 유지 | 대응 전 전체 적용 보류, 자리표시자 유지 |

## 분리 산출물 만들기 (직접 Apply 금지)

```bash
make recovery-split APP_OUTPUT=/tmp/app.yaml JOB_OUTPUT=/tmp/job.yaml POLICY_OUTPUT=/tmp/np.yaml
```

`App` 산출물은 `apps/overlays/recovery` 단독 빌드와 동일해야 하며(어긋나면 거부), Job은 같은 hash 이름·digest를 쓴다.
hash 수동 고정과 `suffixHash` 해제는 하지 않는다. Job에 남은 `input-required` 표식은 B/C가 Secret·CA·Deadline·실행창을 확정할 때 제거한다.

## 아직 확정되지 않은 값 (A/B/C 확인 후 교체)

GatewayClass `nginx`(저장소 선언 기준, 클러스터 Accepted 미확인), `DATAPLANE_*_INPUT_REQUIRED`(Gateway data-plane Pod의 Namespace·Pod 라벨), Host `recovery.seokpan.soldesk.store`(후보), 외부 포트/Origin 포트, `recovery-entry-tls` Secret 공급, Migration Deadline·Secret/CA 공급·실행창.

## Valkey live 대조 (읽기 전용, 전체 산출물 적용 전)

실행 중인 `recovery-redis` Pod template이 Source와 같은지 확인한 값만 `recovery-full-run`에 반영한다. 수정·삭제·재시작 명령은 쓰지 않는다.

```bash
kubectl config current-context           # 기존 1차 Kubernetes(Recovery)인지 확인. ROSA/OCP Context와 혼동 금지
kubectl -n seokpan-recovery get sts recovery-redis -o yaml > live-redis.yaml
kustomize build apps/overlays/recovery-full-run > full.yaml
kubectl diff -f full.yaml                # 서버 Diff. Valkey 외 객체의 신규 생성은 아직 승인되지 않았음을 전제로 읽는다
```

대조 항목: replicas, image(digest), command/args, securityContext, resources, probes, volumes/volumeMounts 이름과 소스, **runtime-config ConfigMap 이름**,
`recovery-redis-config-<hash>` ConfigMap 이름, TLS/AUTH Secret 이름, ownerReferences·label, imagePullSecrets.

판정: scale-down, image, Pod template, volume, ConfigMap 참조 변경이 하나라도 있으면 전체 산출물을 적용하지 않는다.
live와 다른 값은 live 쪽 사실을 확인한 뒤 B/C와 검토해 Source를 맞추고, 임의로 Source에 맞춰 live를 바꾸지 않는다.

## 신규 Gateway 적용 순서와 통신 정책 (HELD, 값 수락 후에만)

신규 Gateway의 data-plane Pod는 Gateway와 같은 `seokpan-recovery`에 생성되므로 기존 `recovery-default-deny`가 그 Pod도 막는다.
Pod 라벨은 Gateway가 생성된 뒤에만 알 수 있다. 아래 순서를 지킨다(각 단계는 담당의 수락 후, 이 문서는 승인이 아님).

1. 진입 TLS Secret `recovery-entry-tls`를 보호 공급한다 (A/C). 없으면 Gateway는 ResolvedRefs 실패로 남는다.
2. 신규 Gateway를 생성한다. 이때 기존 application Gateway의 Listener/NodePort/허용 Namespace는 바꾸지 않는다.
3. 읽기 전용으로 신규 data-plane을 확인한다: Service -> EndpointSlice -> 실제 Pod/owner/labels/Namespace.
   기존 `application` Pod와 `nginx-gateway` Controller Pod의 라벨을 복사하지 않는다.
4. 확인한 Pod 라벨과 앞단 출발지(HAProxy 또는 NodePort 경유 노드 주소)를 `networkpolicy.yaml`의
   `recovery-entry-*`, `recovery-dataplane`의 자리표시자에 넣는 후속 PR을 연다 (게이트가 모양을 검사한다).
5. NP를 적용하고 Gateway Accepted/Programmed/ResolvedRefs, Route 상태, 실제 연결을 확인한다.

`recovery-dataplane` 정책 요약: egress는 Controller agent-grpc(Pod 포트 8443; Service 포트 443이 아님), Backend 8000, Frontend 8080, CoreDNS만,
ingress는 좁은 IPv4 출발지(최대 4개, /24보다 넓지 않음)에서 Gateway 리스너 포트만 허용한다.
앞단 HAProxy는 현재 defaults client/server 60s다(설정 파일 기준). NGF의 3600s 후보는 이 값이 정해지기 전에는 적용하지 않는다.
