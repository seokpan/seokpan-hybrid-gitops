KUSTOMIZE ?= kustomize
PYTHON ?= python3
ENVIRONMENT ?= lab

.PHONY: preview release-manifest test

# Diagnostic preview only. Checked-in overlays remain input-required drafts.
preview:
	$(KUSTOMIZE) build apps/overlays/$(ENVIRONMENT)

# No Apply, Sync or cluster call. OUTPUT must name a separate artifact path.
release-manifest:
	@test -n "$(OUTPUT)" || (echo 'OUTPUT is required' >&2; exit 2)
	$(PYTHON) tools/render_release.py $(ENVIRONMENT) --output "$(OUTPUT)" --kustomize "$(KUSTOMIZE)"

test:
	KUSTOMIZE="$(KUSTOMIZE)" $(PYTHON) -m unittest discover -s tools -p 'test_app_manifests.py' -v
