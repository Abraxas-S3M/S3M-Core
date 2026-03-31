#!/bin/bash
# S3M Air-Gapped Deployment Builder
# Run on an INTERNET-CONNECTED machine to download all dependencies
# Then transfer the output to the Jetson via secure USB
#
# Usage: bash scripts/build_offline.sh
# Output: offline_bundle/ directory ready for USB transfer

set -e

echo "═══════════════════════════════════════════════════════"
echo "  S3M AIR-GAPPED DEPLOYMENT BUILDER"
echo "  Building offline package for Jetson AGX Orin"
echo "═══════════════════════════════════════════════════════"

BUNDLE_DIR="offline_bundle"
mkdir -p "$BUNDLE_DIR/wheels"

echo ""
echo "[1/4] Downloading Python wheel packages..."
pip download -r requirements-all.txt -d "$BUNDLE_DIR/wheels/" 2>&1 | tail -5

echo ""
echo "[2/4] Copying source code..."
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='data/replays' --exclude='data/synthetic' \
    src/ configs/ scripts/ docs/ architecture/ requirements-all.txt \
    "$BUNDLE_DIR/"

echo ""
echo "[3/4] Copying Docker files..."
cp -r docker/ "$BUNDLE_DIR/docker/"

echo ""
echo "[4/4] Creating install script..."
cat > "$BUNDLE_DIR/install.sh" << 'INSTALL_EOF'
#!/bin/bash
# S3M Installer — Run on Jetson after USB transfer
set -e
echo "Installing S3M from offline bundle..."
pip install --no-index --find-links=./wheels/ -r requirements-all.txt
echo "Creating data directories..."
mkdir -p data/{threat_logs,security_audit,replays,synthetic,manifests,benchmarks,osint,decision_logs,interop,security_reports}
mkdir -p models/{policies,optimized}
mkdir -p configs/keys
echo "S3M installed successfully."
echo "Start with: python scripts/start_api.py"
echo "Dashboard: http://localhost:8080/dashboard/"
INSTALL_EOF
chmod +x "$BUNDLE_DIR/install.sh"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  BUNDLE COMPLETE: $BUNDLE_DIR/"
echo "  Size: $(du -sh "$BUNDLE_DIR" | cut -f1)"
echo ""
echo "  Transfer to Jetson via USB, then run:"
echo "    cd offline_bundle && bash install.sh"
echo "═══════════════════════════════════════════════════════"
