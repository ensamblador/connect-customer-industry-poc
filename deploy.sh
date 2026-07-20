#!/usr/bin/env bash
set -e

# CDK project folders (auto-detected at script creation time)
CDK_FOLDERS=("agentic-cx-airline" "agentic-cx-bank" "agentic-cx-telco" "general-localization")

deploy_folder() {
    local folder="$1"
    local stack="$2"

    echo "========================================"
    echo "Deploying in: $folder"
    echo "========================================"

    pushd "$folder" > /dev/null

    # Activate virtual environment
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    else
        echo "WARNING: No .venv found in $folder, skipping venv activation"
    fi

    # Deploy
    if [ -n "$stack" ]; then
        echo "Stack: $stack"
        cdk deploy "$stack" --require-approval never
    else
        echo "Stack: --all"
        cdk deploy --all --require-approval never
    fi

    # Deactivate if we activated
    if [ -d ".venv" ]; then
        deactivate 2>/dev/null || true
    fi

    popd > /dev/null
    echo ""
}

# Main
FOLDER="${1:-}"
STACK="${2:-}"

if [ -n "$FOLDER" ]; then
    # Deploy specific folder
    if [ ! -d "$FOLDER" ]; then
        echo "ERROR: Folder '$FOLDER' not found"
        exit 1
    fi
    deploy_folder "$FOLDER" "$STACK"
else
    # Deploy all CDK folders
    echo "No folder specified — deploying all CDK projects..."
    echo ""
    for f in "${CDK_FOLDERS[@]}"; do
        if [ -d "$f" ]; then
            deploy_folder "$f" "$STACK"
        else
            echo "WARNING: $f not found, skipping"
        fi
    done
fi

echo "Done!"
