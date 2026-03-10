PREFIX ?= /usr/local/bin

.PHONY: install install-sh uninstall

install:
	@echo "Installing netbuoy to $(PREFIX)/netbuoy..."
	@pip3 install --quiet -r requirements.txt 2>/dev/null || echo "Warning: pip install failed; speed tests may not work"
	@install -m 755 netbuoy.py $(PREFIX)/netbuoy
	@echo "Done. Run 'netbuoy' to start."

install-sh:
	@echo "Installing shell-only netbuoy to $(PREFIX)/netbuoy..."
	@install -m 755 netbuoy.sh $(PREFIX)/netbuoy
	@echo "Done. Run 'netbuoy' to start."

uninstall:
	@echo "Removing netbuoy from $(PREFIX)/netbuoy..."
	@rm -f $(PREFIX)/netbuoy
	@echo "Done."
