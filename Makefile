ROOT := $(CURDIR)

# Timestamps baked into the package, so the same tree always zips to the
# same bytes. Override with SOURCE_DATE_EPOCH=<unix seconds>.
#
# The last commit's time is the conventional reproducible-builds.org source,
# and it is the only one that is a property of the tree. Outside a git
# checkout (a release tarball, the modlet extracted as a build input) the
# fallback is the 1980 DOS epoch zip can represent exactly, never `date`:
# reading the wall clock put that second's value into the shipped bytes, so
# the same source packaged twice produced two different archives.
SOURCE_DATE_EPOCH ?= $(strip $(shell git log -1 --format=%ct 2>/dev/null))
ifeq ($(SOURCE_DATE_EPOCH),)
SOURCE_DATE_EPOCH := 315532800
endif

# This mod ships no asset bundles, so there is deliberately no
# build-assets or validate-assets target: both are for a mod that owns
# bundles built by the sibling asset pipeline.
.PHONY: help check build package verify-package buildinfo test lint lint-python lint-shell validate-xml verify-patched-config validate-patch-targets install-server deploy-server rollback-server server-smoke playtest clean

# Every target a contributor is expected to use, with what it needs. The
# only list that cannot drift out of date is the one make prints itself.
help:
	@echo "Targets (SUITE=<id> selects a playtest suite, TF=<substr> filters make test):"
	@echo "  help                      this list"
	@echo "  check                     everything CI runs: test, lint, verify-package, buildinfo"
	@echo "  test                      offline gates: every scripts/test_*.py (no game install; needs the .NET SDK for the two TOML round-trip gates)"
	@echo "  lint                      ruff + mypy --strict over scripts/, then shellcheck"
	@echo "  lint-python               ruff + mypy --strict only"
	@echo "  lint-shell                shellcheck only"
	@echo "  build                     stage dist/Wrench/ (needs .local.env, net48 SDK)"
	@echo "  package                   dist/Wrench.zip, extracting to Mods/Wrench/ (needs build)"
	@echo "  verify-package            the package extracts where it should and is byte-reproducible (what CI checks)"
	@echo "  validate-xml              every Config xpath against the installed game (needs .local.env)"
	@echo "  verify-patched-config     every patch element proven applied, from a save's ConfigsDump"
	@echo "  validate-patch-targets    every [HarmonyPatch] target against Assembly-CSharp (needs ilspycmd)"
	@echo "  install-server            provision the dedicated server via SteamCMD (EAC off)"
	@echo "  deploy-server             swap the packaged mod into the server's Mods/"
	@echo "  rollback-server           put back the deployment the last one replaced"
	@echo "  server-smoke              deploy + boot the server briefly, prove the mod loaded"
	@echo "  playtest                  live wrench-mod-settings suite via hordeforge/7dtd-playtest"
	@echo "  clean                     remove dist/, build outputs and .tmp/"

# Offline contract/unit suite: every scripts/test_*.py must exit 0.
# No game install, but the two TOML round-trip gates compile C# and need the
# .NET SDK (the runtime alone answers `dotnet` and lists no SDKs).
# Everything .github/workflows/ci.yml runs, in the order it runs them, so a
# green local run means a green push. The workflow's package step calls
# scripts/verify-package.sh rather than repeating it, so this target and
# CI cannot drift apart.
check: test lint verify-package buildinfo

# Optional substring filters: make test TF="xml layout"
TF ?=
test:
	$(ROOT)/scripts/run-offline-tests.sh $(TF)

# Every static analyzer this tree runs, blocking: ruff + mypy --strict over
# scripts/, then shellcheck at full severity.
lint: lint-python lint-shell

# ruff and mypy --strict over every tracked *.py (pyproject.toml at the root),
# at the dev-group versions uv.lock pins.
lint-python:
	uv run --locked $(ROOT)/scripts/lint-python.sh

# Shellcheck over every tracked shell script (full severity).
lint-shell:
	$(ROOT)/scripts/lint-shell.sh

# Stage the deployable modlet under dist/Wrench/ (compiles the DLL
# when src/ exists; needs .local.env for the game install).
build:
	$(ROOT)/scripts/build.sh

# Zip dist/Wrench/ so extracting into Mods/ yields
# Mods/Wrench/ModInfo.xml immediately. Entries are added in sorted order at a
# fixed timestamp, with the entry modes normalized by scripts/build.sh and
# TZ pinned to UTC, so the archive is byte-reproducible across machines: zip
# writes the DOS timestamp in the local zone, so an unset TZ put the build
# machine's offset into the shipped bytes.
package: build
	cd $(ROOT)/dist && rm -f Wrench.zip && \
		export TZ=UTC LC_ALL=C && \
		find Wrench -exec touch -h -d "@$(SOURCE_DATE_EPOCH)" {} + && \
		find Wrench -print | sort | zip -q -X -@ Wrench.zip
	@echo "OK -> dist/Wrench.zip"

# The two package checks CI runs, on the XML-only package (no game install).
verify-package:
	$(ROOT)/scripts/verify-package.sh

# The build environment, recorded next to the artifacts it produced. A zip
# that does not reproduce is only diagnosable with the tool versions, the
# commit and the timestamp epoch it was made from, and none of those are in
# the artifact itself. Every line degrades to a printed value rather than a
# failure: this reports, it does not gate.
buildinfo:
	@echo "commit    $(shell git rev-parse HEAD 2>/dev/null || echo none)"
	@echo "epoch     $(SOURCE_DATE_EPOCH)"
	@echo "python3   $$(python3 -V 2>&1 || echo 'not found')"
	@echo "dotnet    $${DOTNET:-$$(command -v dotnet || echo not-found)} $$(dotnet --version 2>/dev/null || echo no-sdk)"
	@echo "zip       $$(zip -v 2>/dev/null | sed -n 2p | tr -s ' ' || echo 'not found')"
	@echo "shellcheck $$(shellcheck --version 2>/dev/null | sed -n 2p | tr -s ' ' || echo 'not found')"
	@echo "ruff      $$(ruff --version 2>/dev/null || echo 'not found')"
	@echo "mypy      $$(mypy --version 2>/dev/null || echo 'not found')"
	@echo "package   $$(sha256sum dist/Wrench.zip 2>/dev/null | cut -d' ' -f1 || echo 'not built')"

# Every Config/*.xml xpath checked against the installed game's vanilla
# files (needs .local.env; not part of the offline suite).
validate-xml:
	python3 $(ROOT)/scripts/validate-xml-targets.py

# Prove every shipped XPath actually applied, from a loaded world's own
# ConfigsDump (a patch matching nothing applies silently, log clean).
verify-patched-config:
	python3 $(ROOT)/scripts/verify-patched-config.py

# Every [HarmonyPatch] target re-checked against the installed
# Assembly-CSharp (needs .local.env and ilspycmd).
validate-patch-targets:
	python3 $(ROOT)/scripts/verify-patch-targets.py

# Dedicated-server lane (needs SEVEN_DAYS_TO_DIE_SERVER_DIR in .local.env):
# provision via SteamCMD with a mod-owned EAC-off serverconfig, stage the
# package into the server's Mods/, boot it briefly and prove the mod loaded.
install-server:
	$(ROOT)/scripts/install-server.sh

deploy-server:
	$(ROOT)/scripts/deploy-server.sh

# Put the deployment that the last one replaced back into place.
rollback-server:
	$(ROOT)/scripts/deploy-server.sh --rollback

server-smoke:
	$(ROOT)/scripts/server-smoke.sh


# Live suite via hordeforge/7dtd-playtest (shared client lock; deploys
# Wrench + AtomicDoomsday + the WrenchPlaytest provider).
playtest:
	$(ROOT)/scripts/playtest-maci.sh $(if $(SUITE),--suite "$(SUITE)",)

clean:
	chmod -R u+w $(ROOT)/dist 2>/dev/null || true
	rm -rf $(ROOT)/dist $(ROOT)/src/Wrench/bin $(ROOT)/src/Wrench/obj $(ROOT)/scripts/playtest/dist $(ROOT)/.tmp
