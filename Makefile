PREFIX ?= $(HOME)/.local/bin
VENV ?= $(HOME)/.local/share/netbuoy/venv
SHELL_RC ?= $(if $(wildcard $(HOME)/.zshrc),$(HOME)/.zshrc,$(HOME)/.bash_profile)

.PHONY: install install-sh uninstall ensure-path

ensure-path:
	@if echo "$$PATH" | tr ':' '\n' | grep -qx "$(PREFIX)"; then \
		true; \
	else \
		echo 'export PATH="$(PREFIX):$$PATH"' >> $(SHELL_RC); \
		echo "Added $(PREFIX) to PATH in $(SHELL_RC)"; \
		echo "Run: source $(SHELL_RC)  (or open a new terminal)"; \
	fi

install: ensure-path
	@mkdir -p $(PREFIX)
	@echo "Installing netbuoy to $(PREFIX)/netbuoy..."
	@python3 -m venv $(VENV)
	@$(VENV)/bin/pip install --quiet -r requirements.txt 2>/dev/null \
		|| echo "Warning: pip install failed; speed tests may not work"
	@sed '1s|.*|#!$(VENV)/bin/python3|' netbuoy.py > $(PREFIX)/netbuoy
	@chmod 755 $(PREFIX)/netbuoy
	@echo "Done. Run 'netbuoy' to start."

install-sh: ensure-path
	@mkdir -p $(PREFIX)
	@echo "Installing shell-only netbuoy to $(PREFIX)/netbuoy..."
	@install -m 755 netbuoy.sh $(PREFIX)/netbuoy
	@echo "Done. Run 'netbuoy' to start."

uninstall:
	@echo "Removing netbuoy from $(PREFIX)/netbuoy..."
	@rm -f $(PREFIX)/netbuoy
	@rm -rf $(VENV)
	@echo "Done."
