AGORIS — lokale Entwicklung und Tests
======================================

## Schnellstart

	make doctor        # Prüft, ob der Rechner mitmacht
	make inspect       # Innenansicht des Käfigs
	make attacks       # 14 Ausbruchversuche
	make test          # Komplettcheck aller Agenten
	make run           # Demo-Lauf
	make benchmark     # Sandbox-Performance messen

---

.PHONY: doctor inspect attacks test run benchmark verify clean docker docker-build wsl2 codespaces help

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

benchmark:
	$(AGORIS) benchmark

verify:
	$(AGORIS) verify runs/*-minimal

clean:
	rm -rf runs/

## Docker (funktioniert auf Windows, macOS und Linux)

# Voraussetzung: Docker mit --privileged Support
# Unter Windows/macOS: Docker Desktop, dann "Settings → Resources → File Sharing"
docker-build:
	docker build -t agoris .

docker: docker-build
	docker run --rm --privileged -v "$$(pwd)/runs:/agoris/runs" agoris $(AGORIS) doctor

docker-test: docker-build
	docker run --rm --privileged -v "$$(pwd)/runs:/agoris/runs" agoris $(AGORIS) test

docker-benchmark: docker-build
	docker run --rm --privileged -v "$$(pwd)/runs:/agoris/runs" agoris $(AGORIS) benchmark

## WSL2 (Windows Subsystem for Linux) — empfohlen für Windows

wsl2-install:
	@echo "Installiere WSL2... (PowerShell als Administrator nötig)"
	wsl --install

wsl2-setup:
	@echo "Richte WSL2 für AGORIS ein..."
	wsl sudo apt update && sudo apt install -y git python3
	wsl git clone https://github.com/noahkafemann/ai-agent-security.git
	wsl cd ai-agent-security && python3 agoris.py doctor

wsl2-doctor:
	wsl cd /mnt/c/$(shell basename $(CURDIR)) && python3 agoris.py doctor

wsl2-test:
	wsl cd /mnt/c/$(shell basename $(CURDIR)) && python3 agoris.py test

## GitHub Codespaces (einfachste Möglichkeit, keine Installation)

codespaces:
	@echo "Öffne https://github.com/noahkafemann/ai-agent-security in github.dev"
	@echo "Oder: GitHub → Code → Open with Codespaces"
	@echo "Dann im Terminal: python3 agoris.py doctor"

## Hilfe

help:
	@echo "Verfügbare Ziele:"
	@echo "  doctor           - System prüfen (Linux direkt)"
	@echo "  inspect          - Innenansicht des Käfigs"
	@echo "  attacks          - 14 Ausbruchversuche"
	@echo "  test             - Komplettcheck aller Agenten"
	@echo "  run              - Demo-Lauf"
	@echo "  benchmark        - Sandbox-Performance messen"
	@echo "  verify           - Audit-Hashkette prüfen"
	@echo "  clean            - Lauf-Ordner löschen"
	@echo "  docker-build     - Docker-Image bauen"
	@echo "  docker           - doctor im Docker-Container"
	@echo "  docker-test      - Volltest im Docker-Container"
	@echo "  docker-benchmark - Benchmark im Docker-Container"
	@echo "  wsl2-install     - WSL2 installieren (Windows, Admin nötig)"
	@echo "  wsl2-setup       - WSL2 einrichten + AGORIS klonen"
	@echo "  wsl2-doctor      - doctor in WSL2 (aktuelles Verzeichnis)"
	@echo "  wsl2-test        - test in WSL2 (aktuelles Verzeichnis)"
	@echo "  codespaces       - Anleitung für GitHub Codespaces"
	@echo ""
	@echo "Windows-Nutzer: Nutze WSL2 (make wsl2-setup), Docker (make docker),"
	@echo "                oder GitHub Codespaces (make codespaces)."
	@echo "macOS-Nutzer:     Nutze Docker (make docker) oder Codespaces."

## Hinweise

# Unter Windows: Alternativ WSL2 installieren
#   make wsl2-install
#   make wsl2-setup

# Unter macOS: Docker Desktop oder GitHub Codespaces nutzen
#   Codespaces: .devcontainer/devcontainer.json wird automatisch verwendet
