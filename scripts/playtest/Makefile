ROOT := $(CURDIR)
WRENCH_ROOT := $(abspath $(ROOT)/../..)
MOD_NAME := WrenchPlaytest
DIST := $(ROOT)/dist/$(MOD_NAME)

GAME ?= $(shell if [ -f "$(WRENCH_ROOT)/.local.env" ]; then set -a; . "$(WRENCH_ROOT)/.local.env"; set +a; printf '%s' "$$SEVEN_DAYS_TO_DIE_DIR"; fi)
PLAYTEST_ROOT ?=
HARNESS_DLL ?= $(if $(PLAYTEST_ROOT),$(PLAYTEST_ROOT)/dist/7dtd-playtest/7dtd-playtest.dll)
WRENCH_DLL ?= $(WRENCH_ROOT)/dist/Wrench/Wrench.dll
MANAGED := $(GAME)/7DaysToDie_Data/Managed

.PHONY: build clean

build:
	@test -n "$(GAME)" || (echo "ERROR: set GAME or Wrench's .local.env SEVEN_DAYS_TO_DIE_DIR." >&2; exit 1)
	@test -f "$(MANAGED)/Assembly-CSharp.dll" || (echo "ERROR: missing $(MANAGED)/Assembly-CSharp.dll." >&2; exit 1)
	@test -n "$(HARNESS_DLL)" || (echo "ERROR: set HARNESS_DLL or PLAYTEST_ROOT." >&2; exit 1)
	@test -f "$(HARNESS_DLL)" || (echo "ERROR: missing playtest harness DLL: $(HARNESS_DLL); build hordeforge/7dtd-playtest first." >&2; exit 1)
	@test -f "$(WRENCH_DLL)" || (echo "ERROR: missing $(WRENCH_DLL); run make build in the mod root first." >&2; exit 1)
	rm -rf "$(DIST)"
	mkdir -p "$(DIST)"
	dotnet build "$(ROOT)/Source/WrenchPlaytest.csproj" -c Release -o "$(DIST)" -v q \
		-p:GameManagedDir="$(MANAGED)" -p:PlaytestHarnessPath="$(HARNESS_DLL)" -p:WrenchDllPath="$(WRENCH_DLL)"
	cp "$(ROOT)/ModInfo.xml" "$(DIST)/ModInfo.xml"
	@echo "OK -> $(DIST)"

clean:
	rm -rf "$(ROOT)/dist" "$(ROOT)/Source/bin" "$(ROOT)/Source/obj"
