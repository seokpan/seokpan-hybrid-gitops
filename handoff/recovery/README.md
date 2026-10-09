# Recovery Bundle 로컬 인벤토리 검사

`tools/check_recovery_bundle.py`는 반입된 **정지 상태의 보호된 로컬 사본**(POSIX: 루트와 모든 하위 폴더는 본인 소유700, 인벤토리·Artifact 일반 파일은 본인 소유600)에서 인벤토리 형식·파일 SHA-256·기존 Recovery 활성 Manifest Gate·컨테이너별 Image Mapping을 대조한다. 실제 Bundle을 지금 만들었다는 기록이 아니다. 테스트는 임시 합성 파일이며 실제 DB·Image·CA·암호화 자료가 아니다.

```bash
python3 tools/check_recovery_bundle.py /private/received-bundle
```

`inventory.json`의 v1 계약은 `schema_version: 1`, `environment: recovery`, 승인 `namespace`·로컬 Harbor `registry`, 전체40자리 `source_revisions.app/gitops`, `images.backend/frontend/recovery-redis`의 실제 Harbor@sha256 참조, `server_command`, `secret_references`, `artifacts`다. Artifact 각 행은 `role`·Bundle 내부 상대 `path`·전체64자리 `sha256`만 갖는다. 경로 탈출·Symlink/reparse point·중복 JSON/경로·빠진 자료·추적되지 않은 파일·FIFO/socket 등 특수 파일·해시 불일치를 거부한다. 실제 입력/오류 원문/파일 내용은 판정 출력에 포함하지 않는다.

필수 Artifact role은 `app_manifest`, `image_archive`, `database_dump`, `database_ca`, `redis_ca`, `protected_inputs`, `tool_archive`, `source_archive`다. 단일 Image Archive 내부에는 승인 FE/BE와 Recovery Engine을 포함하고, Dump 묶음에는 승인된 영속 Data 범위를 포함하도록 **별도 공급/내용 검증**한다. 이 검사는 압축파일을 열거나 DB를 읽거나 도구를 실행하지 않으므로 해시가 맞는 빈 의미의 Archive/Dump도 내용 검증 완료로 인정하지 않는다. Archive 내부 OCI index/blob·플랫폼·Source 개정·도구 의존성과 Dump DB/Schema/Data 시점은 공급 Owner 기록과 실제 Import/Restore에서 확인한다.

`secret_references`의 정확한 논리 이름/Key는 도구의 `REFS`와 공통 App/Migration 계약을 따른다. 값은 넣지 않는다. 보호 입력 Artifact는 현재 프로젝트 age 공급 형식의 헤더를 요구한다. 헤더 뒤 평문이나 손상된 데이터가 있어도 이 표식 검사만으로는 구분하지 못하므로, **PASS는 실제 암호화됨·정상 age 파일임을 증명하지 않는다**. 공급 Owner의 별도 암호화/복호화 확인이 필요하며 **복호화 가능 여부·Secret 개정·키 보유·대상 Identity는 판정하지 않는다**. CA는 공개 PEM 표식과 Private Key 부재만 검사하고 X.509 체인·수명·DNS/SAN 신뢰는 실제 TLS 시험에서 판정한다. Secret 공급은 App Manifest와 분리하며 두 CA Artifact의 실제 ConfigMap 공급 내용 동일성은 별도 수락한다.

Recovery 서버 명령은 현행 Source/Gate의 `redis-server`와 맞아야 한다. 이 계약은 특정 Image의 binary 존재나 Engine 채택을 승인하지 않는다. C/D가 승인한 Image가 다른 binary를 요구하면 Recovery Source와 기존 Gate 및 이 인벤토리 계약/시험을 같은 리뷰에서 개정한다. lab의 Valkey 명령·저장소·CA를 그대로 가져오지 않는다. TCP Probe 성공은 TLS/AUTH 성공을 대신하지 않는다.

독립 사본 수락은 별도다. Controller 밖의 보존 위치/Owner·복호화 Key 확보 경로·새 복원 환경 Identity·CA·도구 가용성·실제 사본 해시를 확인하고, Controller가 없는 조건에서 공급/복원 가능한지 시험한다. 다른 폴더에 같은 Bundle을 놓는 것만으로 독립 사본을 증명하지 않는다. RTO10분·영속 DB RPO30분·Portable Backup15분 요구는 실제 Data 시점/완성 지연·탐지부터 업무 재개 시간으로 검증한다.

**검사 중에는 Bundle을 변경하지 않는다.** 생산자·동기화·복사 작업을 마치고 사본을 고정한 뒤 검사한다. 검사 도중이나 이후 파일·인벤토리를 바꾸면 해당 결과를 재사용하지 않고 고정한 새 사본을 다시 검사한다. 이 도구는 동시 변경 방지나 검사 후 무결성을 보장하지 않는다.

순서: C/A 대상·Namespace·저장소·DB/Engine/CA 입력 수락 → B Source/Release 대조 → D Image/도구와 C Dump/보호 자료 반입 → 이 로컬 검사 → 독립 사본/복원 Identity 확인 → 새 격리 Restore → Migration current → App/WS/새 게임/완료기록 확인 → RTO/RPO 실제 수락. 실제 자료 인계 전에는 기존 Recovery 0 Replica 보류와 INPUT_REQUIRED를 유지한다.
