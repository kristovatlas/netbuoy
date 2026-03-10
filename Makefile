PREFIX ?= $(HOME)/.local/bin
VENV ?= $(HOME)/.local/share/netbuoy/venv

.PHONY: install install-sh uninstall

install:
	@mkdir -p $(PREFIX)
	@echo "Installing netbuoy to $(PREFIX)/netbuoy..."
	@python3 -m venv $(VENV)
	@$(VENV)/bin/pip install --quiet -r requirements.txt 2>/dev/null \
		|| echo "Warning: pip install failed; speed tests may not work"
	@sed '1s|.*|#!$(VENV)/bin/python3|' netbuoy.py > $(PREFIX)/netbuoy
	@chmod 755 $(PREFIX)/netbuoy
	@echo "Done. Run 'netbuoy' to start."
	@echo "Make sure $(PREFIX) is in your PATH."

install-sh:
	@mkdir -p $(PREFIX)
	@echo "Installing shell-only netbuoy to $(PREFIX)/netbuoy..."
	@install -m 755 netbuoy.sh $(PREFIX)/netbuoy
	@echo "Done. Run 'netbuoy' to start."
	@echo "Make sure $(PREFIX) is in your PATH."

uninstall:
	@echo "Removing netbuoy from $(PREFIX)/netbuoy..."
	@rm -f $(PREFIX)/netbuoy
	@rm -rf $(VENV)
	@echo "Done."
