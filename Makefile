# cc-monitor Makefile
# ==========================================================================

PORT     ?= 9876
HOST     ?= 0.0.0.0
VENV     := $(HOME)/Projects/venv_313
PROJROOT := $(shell pwd)
APK_SRC  := $(PROJROOT)/android_app
APK_OUT  := $(APK_SRC)/build/app/outputs/flutter-apk/app-debug.apk

# ---- Server ----

.PHONY: restart-server
restart-server:
	./scripts/restart-server.sh $(PORT) $(HOST)

.PHONY: test
test:
	$(VENV)/bin/pytest tests/ -v

.PHONY: test-quick
test-quick:
	$(VENV)/bin/pytest tests/ -q

.PHONY: install
install:
	$(VENV)/bin/pip install -e ".[dev]"

# ---- Android APK (Flutter Docker) ----

FLUTTER_IMAGE := cc-monitor-flutter

DOCKER := $(shell docker ps > /dev/null 2>&1 && echo docker || echo "sudo docker")

# Use host network when proxy is on localhost (127.0.0.1)
DOCKER_NET := $(shell [ "$$HTTP_PROXY" = "http://127.0.0.1:7780" ] && echo "--network=host" || echo "")

.PHONY: docker-flutter-image
docker-flutter-image:
	$(DOCKER) build \
		--build-arg HTTP_PROXY=$$HTTP_PROXY \
		--build-arg HTTPS_PROXY=$$HTTPS_PROXY \
		-f Dockerfile.flutter \
		-t $(FLUTTER_IMAGE) .

.PHONY: build-apk
build-apk: docker-flutter-image
	$(DOCKER) run --rm $(DOCKER_NET) \
		-e HTTP_PROXY=$$HTTP_PROXY \
		-e HTTPS_PROXY=$$HTTPS_PROXY \
		-e http_proxy=$$HTTP_PROXY \
		-e https_proxy=$$HTTPS_PROXY \
		-v $(PROJROOT):/build \
		--workdir /build/android_app \
		--entrypoint /usr/local/bin/preflight \
		$(FLUTTER_IMAGE) bash -c "flutter pub get && flutter build apk --debug"
	@echo "=== APK built ==="
	@ls -lh $(APK_OUT)

.PHONY: build-apk-release
build-apk-release: docker-flutter-image
	$(DOCKER) run --rm $(DOCKER_NET) \
		-e HTTP_PROXY=$$HTTP_PROXY \
		-e HTTPS_PROXY=$$HTTPS_PROXY \
		-e http_proxy=$$HTTP_PROXY \
		-e https_proxy=$$HTTPS_PROXY \
		-v $(PROJROOT):/build \
		--workdir /build/android_app \
		--entrypoint /usr/local/bin/preflight \
		$(FLUTTER_IMAGE) bash -c "flutter pub get && flutter build apk --release"
	@echo "=== APK built ==="
	@ls -lh $(APK_SRC)/build/app/outputs/flutter-apk/app-release.apk

# ---- Android install ----

.PHONY: adb-install
adb-install:
	adb install -r $(APK_OUT) || (adb uninstall com.ccmonitor.cc_monitor_app && adb install $(APK_OUT))

.PHONY: deploy-apk
deploy-apk: build-apk adb-install
	@echo "=== APK deployed to device ==="

# ---- Full deploy (server + APK) ----

.PHONY: deploy
deploy: restart-server deploy-apk
	@echo "=== Full deploy complete ==="

# ---- Docker ----

# Set via environment: export DOCKER_PROXY=http://your-proxy:port
DOCKER_PROXY ?=

.PHONY: docker-build
docker-build:
	$(DOCKER) build \
		$(if $(DOCKER_PROXY),--build-arg HTTP_PROXY=$(DOCKER_PROXY) --build-arg HTTPS_PROXY=$(DOCKER_PROXY)) \
		-t cc-monitor:latest .

.PHONY: docker-up
docker-up:
	$(DOCKER) compose up -d

.PHONY: docker-down
docker-down:
	$(DOCKER) compose down

.PHONY: docker-restart
docker-restart: docker-build
	$(DOCKER) rm -f cc-monitor 2>/dev/null || true
	$(DOCKER) compose up -d

.PHONY: docker-logs
docker-logs:
	$(DOCKER) logs -f cc-monitor

# ---- Help ----

.PHONY: help
help:
	@echo "cc-monitor Makefile"
	@echo ""
	@echo "  Server:"
	@echo "    make restart-server      Kill, reinstall, restart native server"
	@echo "    make test                 Run all tests (verbose)"
	@echo "    make test-quick           Run all tests (quiet)"
	@echo "    make install              Reinstall package in dev mode"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-build         Build Docker image"
	@echo "    make docker-up            Start Docker container"
	@echo "    make docker-down          Stop Docker container"
	@echo "    make docker-restart       Rebuild + restart Docker"
	@echo "    make docker-logs          Follow container logs"
	@echo ""
	@echo "  Android:"
	@echo "    make build-apk            Build debug APK via Docker"
	@echo "    make build-apk-release    Build release APK via Docker"
	@echo "    make adb-install          ADB install debug APK to device"
	@echo "    make deploy-apk           Build + ADB install debug APK"
	@echo ""
	@echo "  Full cycle:"
	@echo "    make deploy               Restart server + build & install APK"
