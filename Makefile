PREFIX ?= $(HOME)/.local/bin
DATADIR ?= $(HOME)/.local/share/netbuoy
VENV ?= $(DATADIR)/venv
HELPER_APP ?= $(DATADIR)/NetbuoyVPNHelper.app
SHELL_RC ?= $(if $(wildcard $(HOME)/.zshrc),$(HOME)/.zshrc,$(HOME)/.bash_profile)

.PHONY: install install-sh uninstall ensure-path build-helper

ensure-path:
	@if echo "$$PATH" | tr ':' '\n' | grep -qx "$(PREFIX)"; then \
		true; \
	else \
		echo 'export PATH="$(PREFIX):$$PATH"' >> $(SHELL_RC); \
		echo "Added $(PREFIX) to PATH in $(SHELL_RC)"; \
		echo "Run: source $(SHELL_RC)  (or open a new terminal)"; \
	fi

build-helper:
	@mkdir -p $(DATADIR)
	@if command -v osacompile >/dev/null 2>&1; then \
		echo "Building VPN helper app..."; \
		osacompile -o $(HELPER_APP) helpers/vpn-reconnect.applescript; \
		echo "Built $(HELPER_APP)"; \
		echo ""; \
		echo ">>> Grant accessibility to NetbuoyVPNHelper:"; \
		echo ">>>   System Settings > Privacy & Security > Accessibility"; \
		echo ">>>   Click +, navigate to $(HELPER_APP)"; \
		echo ""; \
	else \
		echo "Warning: osacompile not found (not macOS?); VPN reconnect will not work"; \
	fi

install: ensure-path build-helper
	@mkdir -p $(PREFIX)
	@echo "Installing netbuoy to $(PREFIX)/netbuoy..."
	@python3 -m venv $(VENV)
	@$(VENV)/bin/pip install --quiet -r requirements.txt 2>/dev/null \
		|| echo "Warning: pip install failed; speed tests may not work"
	@sed '1s|.*|#!$(VENV)/bin/python3|' netbuoy.py > $(PREFIX)/netbuoy
	@chmod 755 $(PREFIX)/netbuoy
	@echo "Done. Run 'netbuoy' to start."

install-sh: ensure-path build-helper
	@mkdir -p $(PREFIX)
	@echo "Installing shell-only netbuoy to $(PREFIX)/netbuoy..."
	@install -m 755 netbuoy.sh $(PREFIX)/netbuoy
	@echo "Done. Run 'netbuoy' to start."

uninstall:
	@echo "Removing netbuoy from $(PREFIX)/netbuoy..."
	@rm -f $(PREFIX)/netbuoy
	@rm -rf $(DATADIR)
	@echo "Done."
