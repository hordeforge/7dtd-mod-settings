ROOT := $(CURDIR)

# Timestamps baked into the package, so the same tree always zips to the
# same bytes. Override with SOURCE_DATE_EPOCH=<unix seconds>.
SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct 2>/dev/null || date +%s)

# This mod ships no asset bundles, so there is deliberately no
# build-assets or validate-assets target: both are for a mod that owns
# bundles built by the sibling asset pipeline.
.PHONY: build package test lint-shell validate-xml verify-patched-config validate-patch-targets install-server deploy-server server-smoke playtest clean

# Offline contract/unit suite: every scripts/test_*.py must exit 0.
# Optional substring filters: make test TF="xml layout"
TF ?=
test:
	$(ROOT)/scripts/run-offline-tests.sh $(TF)

# Shellcheck over every tracked shell script (full severity).
lint-shell:
	$(ROOT)/scripts/lint-shell.sh

# Stage the deployable modlet under dist/Wrench/ (compiles the DLL
# when src/ exists; needs .local.env for the game install).
build:
	$(ROOT)/scripts/build.sh

# Zip dist/Wrench/ so extracting into Mods/ yields
# Mods/Wrench/ModInfo.xml immediately. Entries are added in sorted order at a
# fixed timestamp, so the archive is byte-reproducible across machines.
package: build
	cd $(ROOT)/dist && rm -f Wrench.zip && \
		find Wrench -exec touch -h -d "@$(SOURCE_DATE_EPOCH)" {} + && \
		find Wrench -print | LC_ALL=C sort | zip -q -X -@ Wrench.zip
	@echo "OK -> dist/Wrench.zip"

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
	rm -rf $(ROOT)/dist $(ROOT)/src/Wrench/bin $(ROOT)/src/Wrench/obj $(ROOT)/scripts/playtest/dist $(ROOT)/.tmp
