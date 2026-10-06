AGORIS — lokale Entwicklung und Tests
======================================

## Schnellstart

	make doctor        # Prüft, ob der Rechner mitmacht
	make inspect       # Innenansicht des Käfigs
	make attacks       # 14 Ausbruchversuche
	make test          # Komplettcheck aller Agenten
	make run            # Demo-Lauf

---

.PHONY: doctor inspect attacks test run verify clean docker

PYTHON := python3
AGORIS := $(PYTHON) agoris.py

## Lokale Befehle (direkt auf Linux)

doctor:
	$(AGORIS) doctor

inspect:
	$(AGORIS) inspect

attacks:
	$(AGORIS) attacks

test:
	$(AGORIS) test

run:
	$(AGORIS)

verify:
	$(AGORIS) verify runs/*-minimal

clean:
	rm -rf runs/

## Docker (funktioniert auf Windows, macOS und Linux)

# Voraussetzung: Docker mit --privileged Support
# Unter Windows/macOS: Docker Desktop, dann "Settings → Resources → File Sharing"
docker:
	docker run --rm --privileged -v "$$(pwd)/runs:/agoris/runs" agoris $(AGORIS) doctor

## Hinweise

# Unter Windows: Alternativ WSL2 installieren
#   wsl --install
#   in WSL2: make doctor

# Unter macOS: Docker Desktop oder GitHub Codespaces nutzen
#   Codespaces: .devcontainer/devcontainer.json wird automatisch verwendet
