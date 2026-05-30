#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: bash scripts/release.sh [BUMP|VERSION] [--push]

BUMP may be one of: major, minor, patch, stable, alpha, beta, rc, post, dev.
If omitted, BUMP defaults to patch.

Examples:
  bash scripts/release.sh
  bash scripts/release.sh minor
  bash scripts/release.sh 0.2.0 --push
USAGE
}

die() {
    echo "error: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

require_clean_worktree() {
    [[ -z "$(git status --porcelain)" ]] || die 'working tree is not clean'
}

release_arg=''
push=0

while (($#)); do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --push)
            push=1
            ;;
        --*)
            die "unknown option: $1"
            ;;
        *)
            [[ -z "$release_arg" ]] || die 'only one bump or version argument is allowed'
            release_arg="$1"
            ;;
    esac
    shift
done

release_arg="${release_arg:-patch}"

require_command git
require_command uv

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

require_clean_worktree

case "$release_arg" in
    v*)
        die 'pass the project version without a leading v'
        ;;
    major|minor|patch|stable|alpha|beta|rc|post|dev)
        target_version="$(uv version --bump "$release_arg" --dry-run --short)"
        ;;
    *)
        target_version="$(uv version "$release_arg" --dry-run --short)"
        ;;
esac

tag="v$target_version"

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    die "local tag already exists: $tag"
fi

if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
    die "remote tag already exists: $tag"
fi

case "$release_arg" in
    major|minor|patch|stable|alpha|beta|rc|post|dev)
        uv version --bump "$release_arg"
        ;;
    *)
        uv version "$release_arg"
        ;;
esac

version="$(uv version --short)"
[[ "$version" == "$target_version" ]] || die "expected version $target_version, got $version"

tag="v$version"

git add pyproject.toml uv.lock
if git diff --cached --quiet; then
    echo "Version is already $version; no release commit created."
else
    git commit -m "Release $tag"
fi

git tag -a "$tag" -m "$tag"
echo "Created tag $tag"

if ((push)); then
    branch="$(git branch --show-current)"
    [[ -n "$branch" ]] || die 'cannot push from detached HEAD'
    git push origin "$branch" "$tag"
else
    echo "To publish: git push origin HEAD $tag"
fi
