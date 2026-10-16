KUSTOMIZE ?= kustomize
PYTHON ?= python3
ENVIRONMENT ?= lab

.PHONY: preview release-manifest preflight-lab-valkey migration-source-check recovery-split test

# Diagnostic preview only. Checked-in overlays remain input-required drafts.
preview:
	$(KUSTOMIZE) build apps/overlays/$(ENVIRONMENT)

# No Apply, Sync or cluster call. OUTPUT must name a separate artifact path.
release-manifest:
	@test -n "$(OUTPUT)" || (echo 'OUTPUT is required' >&2; exit 2)
	$(PYTHON) tools/render_release.py $(ENVIRONMENT) --output "$(OUTPUT)" --kustomize "$(KUSTOMIZE)"

# Stage-1 lab Valkey Source gate only. Does not replace release-manifest. No Apply/Sync.
preflight-lab-valkey:
	$(PYTHON) tools/preflight_lab_valkey.py --kustomize "$(KUSTOMIZE)"

# Compare separate reviewed artifacts only. No Apply/Sync/Secret/DB calls.
migration-source-check:
	@test -n "$(APP_MANIFEST)" -a -n "$(MIGRATION_MANIFEST)" -a -n "$(MIGRATION_DEADLINE_SECONDS)" || (echo 'APP_MANIFEST, MIGRATION_MANIFEST and MIGRATION_DEADLINE_SECONDS are required' >&2; exit 2)
	$(PYTHON) tools/check_migration_manifest.py --app-manifest "$(APP_MANIFEST)" --job-manifest "$(MIGRATION_MANIFEST)" --reviewed-deadline-seconds "$(MIGRATION_DEADLINE_SECONDS)"

# Common Recovery composition -> separate App / Migration Job / Job NetworkPolicy drafts. No Apply/Sync/cluster call.
recovery-split:
	@test -n "$(APP_OUTPUT)" -a -n "$(JOB_OUTPUT)" -a -n "$(POLICY_OUTPUT)" || (echo 'APP_OUTPUT, JOB_OUTPUT and POLICY_OUTPUT are required' >&2; exit 2)
	$(PYTHON) tools/split_recovery_render.py --kustomize "$(KUSTOMIZE)" --app-output "$(APP_OUTPUT)" --job-output "$(JOB_OUTPUT)" --policy-output "$(POLICY_OUTPUT)"

test:
	KUSTOMIZE="$(KUSTOMIZE)" $(PYTHON) -m unittest discover -s tools -p 'test_*_manifests.py' -v
