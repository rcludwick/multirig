# MultiRig Makefile — build Hamlib (submodule) and install Python bindings into .venv using uv

# Configurable variables (can be overridden: make VAR=value)
UV            ?= uv
PYTHON        ?= python3
VENV_DIR      ?= .venv
HAMLIB_DIR    ?= ext/hamlib
BUILD_DIR     ?= $(HAMLIB_DIR)/build
# Default install prefix for Hamlib inside the repo. Avoid "install" name to
# prevent conflicts with macOS case-insensitive filesystems (hamlib has INSTALL file).
PREFIX        ?= $(HAMLIB_DIR)/prefix
JOBS          ?= $(shell sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)

# Derived (use absolute paths where required by configure)
UV_PY         := $(VENV_DIR)/bin/python
PREFIX_ABS    := $(abspath $(PREFIX))
VENV_ABS      := $(abspath $(VENV_DIR))
UV_PY_ABS     := $(abspath $(UV_PY))
PKGCFG_PATH   := $(PREFIX_ABS)/lib/pkgconfig

PREFIX_ID     := $(shell $(PYTHON) -c "import hashlib; print(hashlib.sha1('$(PREFIX_ABS)'.encode()).hexdigest())")
CONFIG_STAMP  := $(BUILD_DIR)/.configured.$(PREFIX_ID)
BUILD_STAMP   := $(BUILD_DIR)/.built.$(PREFIX_ID)
INSTALL_STAMP := $(PREFIX_ABS)/.installed.$(PREFIX_ID)

.DEFAULT_GOAL := all

.PHONY: help all venv hamlib-bootstrap hamlib-configure hamlib-build hamlib-install \
        python-bindings-install bindings reinstall clean distclean venv-contained \
        check-prereqs ensure-prefix-dir ensure-venv-dirs run generate-rig-list

help:
	@echo "Targets:"
	@echo "  make all                       # Build Hamlib and install Python bindings into .venv"
	@echo "  make venv                      # Create .venv using uv"
	@echo "  make hamlib-bootstrap          # Run ./bootstrap in ext/hamlib (needed for git checkout)"
	@echo "  make hamlib-configure          # Configure Hamlib with prefix $(PREFIX)"
	@echo "  make hamlib-build              # Build Hamlib (parallel: $(JOBS) jobs)"
	@echo "  make hamlib-install            # Install Hamlib into $(PREFIX)"
	@echo "  make python-bindings-install   # Install Hamlib Python bindings into .venv via uv"
	@echo "  make venv-contained            # Build+install Hamlib core into .venv and install bindings with rpath"
	@echo "  make check-prereqs             # Check build prerequisites (autotools, pkg-config, swig)"
	@echo "  make generate-rig-list         # Generate multirig/static/rig_models.json from rigctl --list"
	@echo "  make run                       # Ensure Hamlib is installed and run the server (via run.sh)"
	@echo "  make clean                     # Clean Hamlib build directory"
	@echo "  make distclean                 # Remove build + install outputs (keeps submodule)"

all: python-bindings-install generate-rig-list

# Verify common prerequisites and provide actionable guidance
check-prereqs:
	@ok=1; \
	for cmd in autoreconf automake libtool pkg-config; do \
	  if ! command -v $$cmd >/dev/null 2>&1; then \
	    echo "[Missing] $$cmd not found. On macOS: brew install autoconf automake libtool pkg-config"; \
	    ok=0; \
	  fi; \
	done; \
	if ! command -v swig >/dev/null 2>&1; then \
	  echo "[Missing] swig not found (required to build Hamlib's Python bindings)."; \
	  echo "          Install it: macOS → brew install swig; Debian/Ubuntu → sudo apt-get install swig"; \
	  ok=0; \
	fi; \
	if ! command -v uv >/dev/null 2>&1; then \
		echo "[Missing] uv not found."; \
		echo "          Install it: pip3 install --user uv"; \
	fi; \
	if [ $$ok -eq 0 ]; then exit 1; fi; \
	echo "[OK] Prerequisites present"

# Create virtualenv managed by uv
venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		$(UV) venv "$(VENV_DIR)"; \
	fi
	@"$(UV)" pip install pip
	@"$(UV_PY)" -m pip -q install --upgrade pip setuptools wheel >/dev/null

# Ensure the chosen PREFIX is a directory (Hamlib configure/install require an absolute dir)
ensure-prefix-dir:
	@if [ -e "$(PREFIX_ABS)" ] && [ ! -d "$(PREFIX_ABS)" ]; then \
	  echo "[Error] PREFIX=$(PREFIX_ABS) exists but is not a directory." 1>&2; \
	  echo "        Move/delete that file or choose a different PREFIX." 1>&2; \
	  exit 1; \
	fi
	@mkdir -p "$(PREFIX_ABS)"

# Ensure .venv paths exist for venv-contained builds
ensure-venv-dirs:
	@if [ -e "$(VENV_ABS)" ] && [ ! -d "$(VENV_ABS)" ]; then \
	  echo "[Error] VENV_DIR=$(VENV_ABS) exists but is not a directory." 1>&2; \
	  exit 1; \
	fi
	@mkdir -p "$(VENV_ABS)/lib/pkgconfig" "$(VENV_ABS)/bin"

# Prepare autotools (for submodule checked out from git)
hamlib-bootstrap: $(HAMLIB_DIR)/configure

$(HAMLIB_DIR)/configure:
	@cd "$(HAMLIB_DIR)" && ./bootstrap

# Configure (out-of-tree). Ensure autotools bootstrap has been run first.
hamlib-configure: $(CONFIG_STAMP)

$(CONFIG_STAMP): $(HAMLIB_DIR)/configure ensure-prefix-dir | $(BUILD_DIR)
	@cd "$(BUILD_DIR)" && \
		PKG_CONFIG_PATH="$(PKGCFG_PATH)" \
		PYTHON="$(UV_PY_ABS)" \
		LDFLAGS="-Wl,-rpath,$(PREFIX_ABS)/lib" \
		../configure --prefix="$(PREFIX_ABS)" --with-python-binding --with-python-sys-prefix
	@touch "$@"

$(BUILD_DIR):
	@mkdir -p "$(BUILD_DIR)"

# Build core libraries and tools
hamlib-build: $(BUILD_STAMP)

$(BUILD_STAMP): $(CONFIG_STAMP)
	@$(MAKE) -C "$(BUILD_DIR)" -j"$(JOBS)"
	@touch "$@"

# Install into local prefix
hamlib-install: $(INSTALL_STAMP)

$(INSTALL_STAMP): $(BUILD_STAMP) ensure-prefix-dir
	@$(MAKE) -C "$(BUILD_DIR)" install
	@touch "$@"

# Install Python bindings into the project .venv using uv
# Notes:
# - Ensures the venv exists
# - Exposes PKG_CONFIG_PATH so the build can locate the just-installed libhamlib
# - The Python bindings live under ext/hamlib/bindings/python (standard Hamlib layout)
python-bindings-install: check-prereqs venv
	@if "$(UV_PY)" -c 'import Hamlib' >/dev/null 2>&1; then \
		echo "[Info] Hamlib already importable in venv, skipping build/install."; \
	else \
		$(MAKE) hamlib-install; \
	fi
	@echo "[Info] Verifying Hamlib Python bindings (installed via configure --with-python-binding)"
	@"$(UV_PY)" -c "import sys; import Hamlib; print('[OK] Verified: Python can import Hamlib (version:', getattr(Hamlib,'__version__','n/a'), ')')" \
		|| (echo "[ERROR] Hamlib import failed" 1>&2; exit 1)

# Fully contain Hamlib inside the virtualenv and avoid LD/DYLD env vars.
# This target will:
#  - configure/build/install Hamlib with prefix=$(VENV_DIR)
#  - install Python bindings into the venv and set an rpath to $(VENV_DIR)/lib
venv-contained: check-prereqs venv ensure-venv-dirs hamlib-bootstrap
	@echo "[Hamlib] Configuring with prefix=$(VENV_DIR)"
	@$(MAKE) hamlib-configure PREFIX=$(VENV_ABS)
	@echo "[Hamlib] Building"
	@$(MAKE) hamlib-build PREFIX=$(VENV_ABS)
	@echo "[Hamlib] Installing into $(VENV_DIR)"
	@$(MAKE) hamlib-install PREFIX=$(VENV_ABS)
	@echo "[Hamlib] Installing Python bindings into $(VENV_DIR) with rpath to $(VENV_DIR)/lib"
	@cd "$(HAMLIB_DIR)/bindings/python" && \
		PKG_CONFIG_PATH="$(VENV_ABS)/lib/pkgconfig" \
		LDFLAGS="-Wl,-rpath,$(VENV_ABS)/lib" \
		$(UV) pip install --python "$(UV_PY)" -U .
	@echo "[OK] Hamlib core + Python bindings installed inside $(VENV_DIR)"
	@echo "[Tip] Ensure $(VENV_DIR)/bin is on your PATH to use rigctl/rigctld from the venv."
	@"$(UV_PY)" -c "import sys, Hamlib; print('[OK] Verified (venv-contained): Python can import Hamlib (version:', getattr(Hamlib, '__version__', 'n/a'), ')')" \
		|| (echo "[WARN] Hamlib import failed" 1>&2; exit 1)

# Convenience alias
bindings: python-bindings-install

# Reinstall bindings (without rebuilding C libs)
reinstall: venv
	@cd "$(HAMLIB_DIR)/bindings/python" && \
		PKG_CONFIG_PATH="$(PKGCFG_PATH)" $(UV) pip install --python "$(UV_PY)" -U --force-reinstall .

clean:
	@echo "Cleaning Hamlib build artifacts"
	@$(MAKE) -C "$(BUILD_DIR)" clean || true
	@rm -f "$(BUILD_DIR)"/.configured.* "$(BUILD_DIR)"/.built.*
	@rm -f "multirig/static/rig_models.json"
	@if [ -x "$(UV_PY)" ]; then \
		echo "Cleaning Hamlib from $(VENV_DIR)"; \
		"$(UV_PY)" -m pip uninstall -y Hamlib >/dev/null 2>&1 || true; \
		"$(UV_PY)" -m pip uninstall -y hamlib >/dev/null 2>&1 || true; \
		SITEPKG=$$("$(UV_PY)" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])' 2>/dev/null); \
		if [ -n "$$SITEPKG" ]; then \
			rm -rf "$$SITEPKG"/Hamlib* "$$SITEPKG"/_Hamlib*; \
		fi; \
		rm -f "$(VENV_DIR)/bin/rigctl" "$(VENV_DIR)/bin/rigctld"; \
		rm -f "$(VENV_DIR)/lib/pkgconfig/hamlib.pc"; \
		rm -rf "$(VENV_DIR)/include/hamlib" "$(VENV_DIR)/share/hamlib"; \
		rm -f "$(VENV_DIR)/lib"/libhamlib*; \
	fi
	@rm -f "$(PREFIX_ABS)"/.installed.* "$(VENV_ABS)"/.installed.*

distclean:
	@echo "Removing Hamlib build and install directories"
	@rm -rf "$(BUILD_DIR)" "$(PREFIX)"

# Generate rig models list from rigctl --list
generate-rig-list: hamlib-install
	@echo "[Info] Generating rig models list from rigctl"
	@$(PYTHON) scripts/generate_rig_list.py "$(PREFIX_ABS)/bin/rigctl" "multirig/static/rig_models.json"

# Run the server (ensures Hamlib is installed first, but skips rebuild if already importable)
run: python-bindings-install
	@echo "[Info] Starting server via run.sh"
	@bash run.sh
