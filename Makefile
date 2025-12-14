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

.PHONY: help all venv hamlib-bootstrap hamlib-configure hamlib-build hamlib-install \
        python-bindings-install bindings reinstall clean distclean venv-contained \
        check-prereqs ensure-prefix-dir ensure-venv-dirs

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
	@echo "  make clean                     # Clean Hamlib build directory"
	@echo "  make distclean                 # Remove build + install outputs (keeps submodule)"

all: hamlib-install python-bindings-install

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
hamlib-bootstrap:
	@cd "$(HAMLIB_DIR)" && ./bootstrap

# Configure (out-of-tree). Ensure autotools bootstrap has been run first.
hamlib-configure: hamlib-bootstrap ensure-prefix-dir | $(BUILD_DIR)
	@cd "$(BUILD_DIR)" && \
		PKG_CONFIG_PATH="$(PKGCFG_PATH)" \
		PYTHON="$(UV_PY_ABS)" \
		LDFLAGS="-Wl,-rpath,$(PREFIX_ABS)/lib" \
		../configure --prefix="$(PREFIX_ABS)" --with-python-binding --with-python-sys-prefix

$(BUILD_DIR):
	@mkdir -p "$(BUILD_DIR)"

# Build core libraries and tools
hamlib-build: hamlib-configure
	@$(MAKE) -C "$(BUILD_DIR)" -j"$(JOBS)"

# Install into local prefix
hamlib-install: hamlib-build ensure-prefix-dir
	@$(MAKE) -C "$(BUILD_DIR)" install

# Install Python bindings into the project .venv using uv
# Notes:
# - Ensures the venv exists
# - Exposes PKG_CONFIG_PATH so the build can locate the just-installed libhamlib
# - The Python bindings live under ext/hamlib/bindings/python (standard Hamlib layout)
python-bindings-install: check-prereqs venv hamlib-install
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
	@$(MAKE) hamlib-build
	@echo "[Hamlib] Installing into $(VENV_DIR)"
	@$(MAKE) hamlib-install
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

distclean:
	@echo "Removing Hamlib build and install directories"
	@rm -rf "$(BUILD_DIR)" "$(PREFIX)"
