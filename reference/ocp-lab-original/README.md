# OCP 실습(demo2) 원본 Overlay/Manifest 스냅샷 (참고용, I01)

- 작성자: 최유준 / 스냅샷 날짜: 2026-10-02
- 원본 위치: 실습 bastion `/root/seokpan/ocp-test/` (git 저장소가 아니어서 커밋 이력 없음. 이 브랜치의 커밋이 최초 기록)
- 출처 단서: backend `seokpan.io/app-source-commit=6fb8b75fed633769936ea206e8a88351eb062b9a`, frontend `26fac7ed6ba17955bac902ad9d727b9efcc9a765`
- 파일별 sha256: `SHA256SUMS`
- 렌더 확인(2026-10-02): backend/frontend/redis 구성요소별 `oc kustomize` OK. 루트(overlays/ocp-lab)에는 kustomization.yaml 없음
- lab 전용 값(Cloud에 쓰지 말 것): Route host `game-seokpan.apps.demo2.ocp4lab.com`, hostAliases, `seokpan-lab-ca`(만료 2026-10-31), alert-receiver, harbor-pull-secret 참조, lab StorageClass
- `lab/overlays/ocp-lab/migration/job.yaml` = `job-current.yaml` (동일 파일)
- 제외: ocp-test/tls/(CA·서버 키, db-pass.env, 롤백 SQL), kubeconfig, 로그, 시험용 Pod/Rule(16-test-pods, 27-test-rule)
- 이 브랜치는 참고용이며 main에 병합하지 않는다. Cloud 배포 참조는 lab 브랜치와 분리한다.
- NetworkPolicy(monitoring/28-np-*): Ingress 사전검증용(policyTypes=Ingress만, Egress 미검증). base 반영은 네트워크 담당과 협의 필요.
  - 28-np-00-default-deny.yaml에는 정책 2개: 00(Namespace Ingress 전체 차단), 05(alert-receiver Pod 전용, lab 전용 수신기라 ROSA 해당 없음)
  - 28-np-10(같은 NS 전체 허용), 28-np-20(Router 허용, 포트 미지정)은 lab(Redis/MariaDB가 같은 NS, HostNetwork 라우터) 전용
  - ROSA base에는 복사하지 말고 03 §3-B.9.5 NET-01~04 기준으로 새로 작성할 것
