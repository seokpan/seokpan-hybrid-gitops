# Recovery Bundle 로컬 인벤토리 검사

`tools/check_recovery_bundle.py`는 반입된 **정지 상태의 보호된 로컬 사본**(POSIX: 루트와 모든 하위 폴더는 본인 소유700, 인벤토리·Artifact 일반 파일은 본인 소유600)에서 인벤토리 형식·파일 SHA-256·기존 Recovery 활성 Manifest Gate·컨테이너별 Image Mapping을 대조한다. 실제 Bundle을 지금 만들었다는 기록이 아니다. 테스트는 임시 합성 파일이며 실제 DB·Image·CA·암호화 자료가 아니다.

```bash
python3 tools/check_recovery_bundle.py /private/received-bundle
```

`inventory.json`의 기존 v1 계약은 `schema_version: 1`, `environment: recovery`, 승인 `namespace`·로컬 Harbor `registry`, 전체40자리 `source_revisions.app/gitops`, `images.backend/frontend/recovery-redis`의 실제 Harbor@sha256 참조, `server_command`, `secret_references`, `artifacts`다. Artifact 각 행은 `role`·Bundle 내부 상대 `path`·전체64자리 `sha256`만 갖는다. 경로 탈출·Symlink/reparse point·중복 JSON/경로·빠진 자료·추적되지 않은 파일·FIFO/socket 등 특수 파일·해시 불일치를 거부한다. 인벤토리/Artifact의 등록 경로는 실제 파일명·하위 폴더명과 대소문자까지 정확히 일치해야 한다. 등록되지 않은 대소문자 변형 파일도 거부하며, 등록 경로끼리 대소문자만 다른 중복은 이식 가능한 공급을 위해 계속 거부한다. 명시적으로 등록한 혼합 대소문자 경로 자체는 허용한다. 실제 입력/오류 원문/파일 내용은 판정 출력에 포함하지 않는다.

기존 v1의 필수 Artifact role은 `app_manifest`, `image_archive`, `database_dump`, `database_ca`, `redis_ca`, `protected_inputs`, `tool_archive`, `source_archive`다. 단일 Image Archive 내부에는 승인 FE/BE와 Recovery Engine을 포함하고, Dump 묶음에는 승인된 영속 Data 범위를 포함하도록 **별도 공급/내용 검증**한다. 이 검사는 압축파일을 열거나 DB를 읽거나 도구를 실행하지 않으므로 해시가 맞는 빈 의미의 Archive/Dump도 내용 검증 완료로 인정하지 않는다. Archive 내부 OCI index/blob·플랫폼·Source 개정·도구 의존성과 Dump DB/Schema/Data 시점은 공급 Owner 기록과 실제 Import/Restore에서 확인한다.

`secret_references`의 정확한 논리 이름/Key는 도구의 `REFS`와 공통 App/Migration 계약을 따른다. 값은 넣지 않는다. 보호 입력은 raw age 헤더 또는 프로젝트의 SOPS+age YAML 구조를 허용한다. SOPS는 중복 Key·Alias를 거부하고, `sops.age` 수신자/age envelope·암호문 MAC·버전과 모든 비메타데이터 Leaf의 `ENC[AES256_GCM,...]` 구조를 확인한다. 일부 값만 암호화되고 나머지가 평문이면 거부한다. 입력은 최대256KiB·깊이32로 제한한다. 이 검사는 형식만 확인하며 실제 암호화·MAC 무결성·복호화 가능·키 보유·Identity를 증명하지 않는다. 합성 시험의 암호문도 실제 복호화 자료가 아니다. 실제 공급 때 C의 SOPS 복호화/MAC 확인과 보호 개정 수락이 별도로 필요하다. [SOPS 공식 형식](https://getsops.io/docs/)을 따른다. CA는 공개 PEM 표식과 Private Key 부재만 검사하고 X.509 체인·수명·DNS/SAN 신뢰는 실제 TLS 시험에서 판정한다. Secret 공급은 App Manifest와 분리하며 두 CA Artifact의 실제 ConfigMap 공급 내용 동일성은 별도 수락한다.

Recovery 서버 명령은 채택한 Valkey 7.2.14 Source/Gate의 `valkey-server`와 맞아야 한다. 이 계약은 특정 Image의 binary 존재나 Engine 채택을 승인하지 않는다. C/D가 승인한 Image가 다른 binary를 요구하면 Recovery Source와 기존 Gate 및 이 인벤토리 계약/시험을 같은 리뷰에서 개정한다. lab의 Valkey 명령·저장소·CA를 그대로 가져오지 않는다. TCP Probe 성공은 TLS/AUTH 성공을 대신하지 않는다.

독립 사본 수락은 별도다. Controller 밖의 보존 위치/Owner·복호화 Key 확보 경로·새 복원 환경 Identity·CA·도구 가용성·실제 사본 해시를 확인하고, Controller가 없는 조건에서 공급/복원 가능한지 시험한다. 다른 폴더에 같은 Bundle을 놓는 것만으로 독립 사본을 증명하지 않는다. RTO10분·영속 DB RPO30분·Portable Backup15분 요구는 실제 Data 시점/완성 지연·탐지부터 업무 재개 시간으로 검증한다.

**검사 중에는 Bundle을 변경하지 않는다.** 생산자·동기화·복사 작업을 마치고 사본을 고정한 뒤 검사한다. 검사 도중이나 이후 파일·인벤토리를 바꾸면 해당 결과를 재사용하지 않고 고정한 새 사본을 다시 검사한다. 이 도구는 동시 변경 방지나 검사 후 무결성을 보장하지 않는다.

순서: C/A 대상·Namespace·저장소·DB/Engine/CA 입력 수락 → B Source/Release 대조 → D Image/도구와 C Dump/보호 자료 반입 → 이 로컬 검사 → 독립 사본/복원 Identity 확인 → 새 격리 Restore → Migration current → App/WS/새 게임/완료기록 확인 → RTO/RPO 실제 수락. 실제 자료 인계 전에는 기존 Recovery 0 Replica 보류와 INPUT_REQUIRED를 유지한다.

SOPS 공급 계약은 YAML이다. SOPS JSON은 지원 형식에 포함하지 않는다. SOPS가 암호화하지 않는 빈 문자열도 평문 Leaf로 거부하므로, 사용하지 않는 선택 Key는 공급본에서 생략한다. 빈 값이 필수라면 계약을 먼저 검토하며 임의 암호문으로 바꾸지 않는다.

## 최신 periodic DB를 분리하는 v2 계약

새 Bundle은 `schema_version: 2`를 사용한다. v1의 8개 role 중 `database_dump`를 제외한 보호 자산7개와 `database_restore`를 넣는다. 고정 덤프를 최신 DB 사본으로 승계하지 않는다. v1은 이전 사본 대조 호환용으로 유지되며 결과에 `LEGACY_FIXED_DUMP_NOT_CURRENT_RPO_EVIDENCE`를 표시한다.

```json
"database_restore": {
  "database": "stone_game",
  "backup_kind": "periodic",
  "selection": "backup_id_utc_descending_sha256_valid",
  "procedure": "seokpan-hybrid-infra#48",
  "script": "ansible/data/controller/restore.sh",
  "rpo_limit_seconds": 1800
}
```

DB 복원은 [Infra #48](https://github.com/seokpan/seokpan-hybrid-infra/issues/48)의 기존 `restore.sh`로 진행한다. 운영 자동 선택은 `periodic-*`의 Backup ID UTC 데이터 시각 내림차순이며 SHA-256이 맞는 사본을 선택한다. 파일 도착 시각이나 `rehearsal-*`를 운영 기준으로 쓰지 않는다. 이후 age/gunzip/import 종료 코드·Revision·테이블 수·비교를 확인한다. 본 Bundle 검사기는 SSH·DB·복원 스크립트를 실행하지 않는다.

현재 `restore.sh`는 사본의 최대 나이30분을 실행 전에 거부하지 않는다. 따라서 선택된 사본이 최신이라고 RPO30분을 통과한 것은 아니다. 실제 수행자는 선택 Backup ID의 데이터 시각과 T0를 대조하고30분을 넘으면 RPO PASS로 수락하지 않는다. 복호화·가져오기 실패를 자동 재시도로 덮지 않는다. 독립 사본·복원 Identity·실제 RTO/RPO는 계속 `NOT_VERIFIED`다.

## 2026-10-13 채택한 Recovery 초기 계약

B(정태훈/tjung03)가 대상 `seokpan-recovery`, Valkey 7.2.14와 초기 자원안을 채택했다. Source 계약을 선택한 것으로 실제 Namespace 생성, Image 공급/실행, 연결 성공을 뜻하지 않는다.

| 구성 | CPU requests/limits | 메모리 requests/limits |
|---|---|---|
| FE | 25m/250m | 32Mi/64Mi |
| BE | 100m/500m | 128Mi/256Mi |
| Valkey | 100m/500m | 512Mi/512Mi |

Valkey의 `maxmemory 384mb`, `dir /data`, 비영속/noeviction 설정은 두 외부 Include 뒤에 고정하며 Gate가 변경·중복을 거부한다. 외부 runtime Include는 여전히 C가 공급한다. maxmemory는 전체 RSS 제한이 아니며 임의 UID의 /data 쓰기·TLS/AUTH·실제 peak/OOM 시험이 필요하다. Engine 이미지 Placeholder, 외부 Secret/CA와 replicas 0 보류는 유지한다. 이미지 태그/보고만으로 7.2.14 binary 실행을 인정하지 않는다.

Image 공급 담당 D는 실제 Valkey 7.2.14 고정 Digest/플랫폼과 `valkey-server` 실행 파일을 확인한다. 현재 Probe는 TCP listener만 확인하고 CLI를 실행하지 않는다. 후속 AUTH 진단은 `valkey-cli --tls`와 Secret으로 공급한 `VALKEYCLI_AUTH`를 사용하며, 호환 `REDISCLI_AUTH`만으로 인증된다고 가정하지 않는다. 비밀번호를 명령 인수에 넣지 않는다. 공급된 이미지에서 실제 TLS/SNI/CA/AUTH PING을 확인하기 전에는 readiness/업무 성공으로 수락하지 않는다.

정상 메모리 예약은 672Mi, limits 합계는 832Mi다. FE 이전 Pod 완전 종료 뒤 BE 한 개만 rolling 교체하면 추가 BE와 512Mi 여유를 포함한 예약은 1312Mi, limits envelope는 1600Mi다. FE 종료 중 Pod가 겹치면 1344/1664Mi이므로 이전 FE 완전 종료를 먼저 확인한다. 이는 초기 예산이며 실제 Node 수용/성능 PASS가 아니다. 격리는 Namespace 이름만으로 증명되지 않고 실제 Context/RBAC/CNI·통신 경계를 확인해야 한다.

담당 경계: B는 Overlay/소비 검사와 App 업무 검증, A는 기반/네트워크 인계, C는 DB 복원·AUTH/CA·외부 runtime 입력/도구, D는 Image/Registry·시험 및 Evidence 조율을 맡는다. 완료한 Run7 FE/BE 공급·Pull을 반복 요청하지 않는다.

최종 Cloud 이관은 Recovery 복원과 별개다. Foundation Apply 뒤에는 C의 중지 전 준비를 진행한다. ROSA Ready와 App 배포 입력 준비 뒤 B가 원본 전체 Writer를 중지하고, C의 최종 dump/import/비교(6)와 계정/거부 시험(7/8), B의 Migration current/Backend 기동·업무 검증(9)까지 중지를 유지한다. 단계6 비교만으로 원본 쓰기를 재개하지 않는다. Cloud 업무 시험 쓰기도 새 쓰기로 취급하며 발생 뒤에는 원본 단순 재개를 복귀로 인정하지 않는다. C는 본인 Infra #44 절차의 끝점을 이 기준에 맞춰 정합화한다.

초기 공동 시간 예산은 준비30분(쓰기 중지 밖), 중지75분과 종료 여유15분을 합한 120분이다. 실측/날짜 확정이 아니며 ROSA 설치 시간과 실패 시 실제 복귀 시간은 별도다. 보호 조건(Runtime 2000ms 포함)을 완화하지 않는다.
