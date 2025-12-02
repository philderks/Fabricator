FRONTEND_DIR := frontend
BACKEND_DIST := backend/fabricator_backend/frontend_dist

.PHONY: build-frontend clean-frontend

build-frontend:
	cd $(FRONTEND_DIR) && npm install && npm run build
	rm -rf $(BACKEND_DIST)
	mkdir -p $(BACKEND_DIST)
	cp -r $(FRONTEND_DIR)/dist/* $(BACKEND_DIST)/

clean-frontend:
	rm -rf $(BACKEND_DIST)
