# 작성자: 최유준 / 작성 날짜: 2026-10-15
# ROSA 앱 모니터링 선언 (seokpan-cloud)

ROSA 위 앱(Backend/Frontend) 계층의 모니터링 Desired State다. 클러스터/플랫폼 계층은 OpenShift 기본 Monitoring을 사용하며 여기서 선언하지 않는다. UWM 활성화는 ROSA 클러스터 설정(Terraform 소유)이라 포함하지 않는다.

## 구성
- `app/`: ServiceMonitor(Backend `/metrics`, 포트 `http`), PrometheusRule(가용성·재시작·5xx), NetworkPolicy(UWM → Backend 8000 추가 허용)
- `project/`: AppProject `seokpan-cloud-monitoring`와 Application 원본. 자동 Sync 없음
- `smoke/`: Alert 경로 검증용 임시 규칙. Application 미포함, 검증 후 삭제

## 소유 경계
- 기존 Service·앱 NetworkPolicy(`seokpan-deny-ingress` 등)는 `platform/cloud` 계약 소유이며 수정하지 않는다.
- 추가 NP는 기본 차단을 유지하고 UWM 수집원 → Backend metrics 포트만 허용한다.
- Root/Project 최초 등록은 Infra Ansible, 권한(Controller SA/운영자)은 B 담당이다.

## Sync 순서
1. 모니터링 Application만 선택 수동 Sync (앱·Migration과 함께 실행하지 않음)
2. smoke 규칙을 별도 적용해 firing → resolved 확인 후 삭제

## 앱 기동 전후 구분
- 기동 전: Sync 성공, 규칙 로드, smoke Alert
- 기동 후: ServiceMonitor target UP, 가용성/5xx 규칙 평가, 알림 전달 수락

## 롤백
Argo에서 모니터링 Application의 리소스 3종을 수동 삭제한다. 앱 리소스에는 영향이 없다.

## 수신 경로 시험 파일 (receiver/)
- `receiver/`는 Argo 경로(`app/`) 밖의 **시험용** 선언이다. Alertmanager 메일 수신 경로(규칙 → Alertmanager → 메일) 시험에 한 번 쓰고, 영구 배포 대상이 아니다.
- `alertmanagerconfig-seokpan-cloud.yaml`: 비밀번호는 Secret `alertmanager-smtp-credential`(키 `smtp-password`)을 참조한다. Secret 값은 Git에 두지 않고 Vault → Ansible 경로로 주입한다.
- `prometheusrule-receiver-test.yaml`: 임시 규칙. 메일 확인 후 생성 UID와 대조해 삭제한다.
- UWM 설정(`user-workload-monitoring-config`)은 수동 적용이며 레포에 없다. ROSA 재생성 시 재현되지 않으므로 영구화(소유자 결정, AppProject 허용 종류·Controller 권한 추가)는 별도 작업이다.
