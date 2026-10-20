# Recovery Redis 보호 입력 공급

> **B 전수 대조 후속 — 2026-10-21:** [최종 종료](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/execution/B_ROSA_FINAL_CLOSEOUT_20261021.md)와 [실제 시험 결과](https://github.com/seokpan/seokpan-hybrid-docs/blob/main/execution/HPA_ATTEMPT04_VERIFIED_RESULTS_20261021.md)를 우선한다. B ROSA·정확한 소유 범위 잔존 자원·Snapshot4개 정리는 완료다. 아래 절차·입력 대기·명령은 작성 당시 기록 또는 재사용 계약이며 현재 재실행 요청이 아니다. A 자원과 다른 담당의 종료는 판정하지 않는다. [전체 대조](https://github.com/seokpan/seokpan-hybrid-docs/pull/140).

선택 방식: **보호 SOPS와 소비 도구를 Bundle로 인계하고, 승인된 기존 Linux 실행 위치에서 Secret/ConfigMap만 분리 생성**한다. 새 Ansible 역할이나 App Manifest 안 평문 Secret을 만들지 않는다. 완료한 C 입력 해독을 준비 작업 때문에 반복하지 않는다.

대상은 `seokpan-recovery`의 Secret3개·ConfigMap2개다. `tools/supply_recovery_redis_inputs.py`와 같은 폴더의 `prepare_recovery_redis_inputs.py`를 함께 인계하고 Source/파일 해시를 Bundle inventory에 연결한다. Controller 밖 독립 사본·키·도구 가용성은 실제 복원 수락에서 확인한다.

실행 전: B가 승인한 실제 Context 이름·HTTPS API·기존 Namespace UID, 기존 인증/CA 신뢰·get/create 권한, 기존 본인 소유600 SOPS·승인 사용창/단일 실행자를 준비한다. 도구는 Namespace를 생성하지 않고 로그인/Token 발급·auth exec/provider·TLS 검증 해제를 하지 않는다. Workload는 정지 상태로 유지한다. SOPS 해시는 `4c931e6240e054d84b935ed47efc02ce1cede42f4cd255cbf10060b414b74ec0`, CA 개정은 기존 C 보고와 같다. 개정이 바뀌면 원본 보존 후 Source/해시를 함께 리뷰한다.

## 실제 대상 인계 뒤 실행 순서

실제 값은 보호 경로에서 설정한다. 비밀번호·Token·키는 CLI 인수/공개 댓글에 넣지 않는다.

```bash
recovery_cipher="$HOME/secrets/seokpan/recovery-redis.sops.yaml"
recovery_context='<existing-context>'
recovery_api_server='<https-api-server>'
recovery_namespace_uid='<existing-namespace-uid>'
recovery_input_run='<approved-run-id>'

# 서버 dry-run까지: 실제 객체는 생성하지 않는다.
python3 tools/supply_recovery_redis_inputs.py "$recovery_cipher" \
  --mode dry-run --context "$recovery_context" --api-server "$recovery_api_server" \
  --namespace-uid "$recovery_namespace_uid" --run-id "$recovery_input_run"

# dry-run PASS 확인과 B의 객체 생성 승인 후, 같은 대상/개정으로 한 번 실행.
python3 tools/supply_recovery_redis_inputs.py "$recovery_cipher" \
  --mode create --context "$recovery_context" --api-server "$recovery_api_server" \
  --namespace-uid "$recovery_namespace_uid" --run-id "$recovery_input_run"
```

create에서도 이름 부재·다섯 dry-run·쓰기 직전 대상 Identity를 확인한다. 기존 객체는 내용이 같아도 덮어쓰지 않는다. 각 객체 create 뒤 UID·내용·run marker를 readback한다. 실행당 SOPS1회·CLI35회 상한/명령당20초이며 평문은 메모리/stdin 파이프만 사용한다. 출력은 고정 판정·객체 이름/UID·호출 수뿐이다. 기본 `--mode check`는 API 없이 매핑만 확인한다.

STOP이면 **create/dry-run을 반복하지 않는다**. 확인된 생성 이름/UID·create 시도 수를 보존해 B가 현재 상태를 판단한다. 부분 생성은 남기며 자동 삭제/rollback하지 않는다. 읽기 대조는 다음과 같다. verify는 최초 누락/불일치에서 멈추고 그 전까지 내용/run marker가 맞았던 이름/UID를 verified_objects로 반환한다. 불확실한 create의 실제 성공과 누락 객체를 확인한 뒤 남은 공급은 별도로 결정한다.

```bash
python3 tools/supply_recovery_redis_inputs.py "$recovery_cipher" \
  --mode verify --context "$recovery_context" --api-server "$recovery_api_server" \
  --namespace-uid "$recovery_namespace_uid" --run-id "$recovery_input_run"
```

Namespace/Role 변경·기존 Apply/Patch/Delete·Replica/Sync·DB/부하는 없다. 공급 PASS는 객체 내용/UID까지다. 인증서 체인·키쌍·SAN/만료와 Valkey7.2.14 Image Digest/플랫폼·`valkey-server`/`valkey-cli`·TLS 사용 가능성은 별도 확인한다. 승인된 기동 뒤 CA/SNI 검증 TLS+AUTH PING·Backend 접속/업무·임의 UID /data 쓰기·RSS/기동Peak/OOM을 확인한다. AUTH는 보호 입력/환경의 `VALKEYCLI_AUTH`를 사용하며 argv에 넣지 않는다. TCP Ready·객체 공급을 실제 TLS/업무 PASS로 기록하지 않는다.

복귀는 이전 보호 개정/Bundle과 Workload 정지 조건을 함께 검토한다. 다른 실행자가 변경한 객체를 삭제/덮어쓰지 않는다. 도구/문서 병합은 공급·기동·복원 승인이 아니다.
