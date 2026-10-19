# Recovery 진입·Migration 후보 (HELD)

작성자: 최유준 / 작성 날짜: 2026/10/16

이 폴더는 Recovery Namespace(`seokpan-recovery`)의 **Migration 후보와 보류 후보**를 둔다. 실제 Apply/Sync/복원은 포함하지 않는다.

| 경로 | 역할 | 상태 |
| --- | --- | --- |
| `migration/` | suspended `current` Job + 전용 NetworkPolicy. 단독 빌드 대상 아님 | HELD |
| `compose/` | App Overlay + `migration/`을 한 번에 합성해 `backend-config` hash·Backend digest를 공통 변환 | 검토용 |
| `candidates/ws-timeout.yaml` | NGF `ProxySettingsPolicy` WS read/send 3600s 후보. 어떤 Kustomization에도 미포함 | A/D CRD 확인 전 보류 |

| `apps/overlays/recovery-run/` | Valkey 보존 전용 산출물: 정확히 StatefulSet·Service·ConfigMap 3개만 출력(FE/BE·Gateway·Route·NP 제외). 전체 Recovery 적용용이 아님 | live Diff 확인 전 적용 금지 |

## 분리 산출물 만들기 (직접 Apply 금지)

```bash
make recovery-split APP_OUTPUT=/tmp/app.yaml JOB_OUTPUT=/tmp/job.yaml POLICY_OUTPUT=/tmp/np.yaml
```

`App` 산출물은 `apps/overlays/recovery` 단독 빌드와 동일해야 하며(어긋나면 거부), Job은 같은 hash 이름·digest를 쓴다.
hash 수동 고정과 `suffixHash` 해제는 하지 않는다. Job에 남은 `input-required` 표식은 B/C가 Secret·CA·Deadline·실행창을 확정할 때 제거한다.

## 아직 확정되지 않은 값 (A/B/C 확인 후 교체)

GatewayClass `nginx`(저장소 선언 기준, 클러스터 Accepted 미확인), `DATAPLANE_*_INPUT_REQUIRED`(Gateway data-plane Pod의 Namespace·Pod 라벨), Host `recovery.seokpan.soldesk.store`(후보), 외부 포트/Origin 포트, `recovery-entry-tls` Secret 공급, Migration Deadline·Secret/CA 공급·실행창.
