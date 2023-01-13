import argparse
import json
import logging
import subprocess
import sys


def run_gh_cli(*args, json_response=True):
    """Run command with GitHub CLI"""
    output = subprocess.check_output(
        ["gh", "api", "-H", "Accept: application/vnd.github+json", *args]
    )
    if json_response:
        return json.loads(output)
    return output


def delete_cache(cache_: dict) -> None:
    logging.info(f"Deleting cache id {cache_['id']} on {cache_['ref']} with key {cache_['key']}")
    run_gh_cli(
        "--method",
        "DELETE",
        "/repos/{owner}/{repo}/actions/caches/" + str(cache_["id"]),
        json_response=False,
    )
    global bytes_used
    bytes_used -= cache["size_in_bytes"]


# Parse required GitHub Actions contexts
# (https://docs.github.com/en/actions/learn-github-actions/contexts)
# from command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--github.ref", required=True)
parser.add_argument("--needs.get-build-matrix.outputs.build-matrix", required=True)
parser.add_argument("--matrix.charm.path", required=True)
parser.add_argument("--matrix.charm.bases_index", required=True)


# argparse converts "-" to "_" in argument names
class ArgumentDict(dict):
    def __getitem__(self, key):
        return super().__getitem__(key.replace("-", "_"))


GITHUB_ACTIONS_CONTEXT = ArgumentDict(vars(parser.parse_args()))

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
caches = run_gh_cli(
    "--method",
    "GET",
    "/repos/{owner}/{repo}/actions/caches",
    "--raw-field",
    "key=charmcraft-pack-",
    "--raw-field",
    "sort=created_at",
    "--raw-field",
    "direction=desc",  # Most recently created first
)["actions_caches"]
if not caches:
    logging.info("No caches")
    exit()
# Updated about every 5 minutes
# https://docs.github.com/en/rest/actions/cache?apiVersion=2022-11-28#get-github-actions-cache-usage-for-a-repository
bytes_used = run_gh_cli("--method", "GET", "/repos/{owner}/{repo}/actions/cache/usage")[
    "active_caches_size_in_bytes"
]
CURRENT_REF = GITHUB_ACTIONS_CONTEXT["github.ref"]

# Remove caches that are no longer in the build matrix
# Usually, each instance in the build matrix prunes its own caches
# However, in the following cases, the instance is no longer part of the build matrix:
# - charmcraft.yaml file is deleted
# - number of bases in charmcraft.yaml decreases
BUILD_MATRIX = json.loads(GITHUB_ACTIONS_CONTEXT["needs.get-build-matrix.outputs.build-matrix"])
prefixes_in_build_matrix = [
    f"charmcraft-pack-{element['path']}-{element['bases_index']}" for element in BUILD_MATRIX
]
caches_not_in_build_matrix = []
for cache in caches:
    # Path component of key might contain "-"; remove components from end of key
    # (components at the end of key will not contain "-")
    key_prefix = "-".join(cache["key"].split("-")[:-3])

    if key_prefix not in prefixes_in_build_matrix:
        if cache["ref"] == CURRENT_REF:
            delete_cache(cache)
        else:
            caches_not_in_build_matrix.append(cache)

CACHE_KEY_PREFIX = f"charmcraft-pack-{GITHUB_ACTIONS_CONTEXT['matrix.charm.path']}-{GITHUB_ACTIONS_CONTEXT['matrix.charm.bases_index']}-"
caches = [cache for cache in caches if cache["key"].startswith(CACHE_KEY_PREFIX)]
if not caches:
    logging.info("No caches")
    exit()
fresh_caches = {}  # Last created cache for a ref (branch or PR)
for cache in caches:
    if (ref := cache["ref"]) not in fresh_caches:
        fresh_caches[ref] = cache
    else:
        # Cache is stale (no longer in use); delete it
        delete_cache(cache)

expected_cache_size = (fresh_caches.get(CURRENT_REF) or list(fresh_caches.values())[0])[
    "size_in_bytes"
]
current_ref_cache = fresh_caches.pop(CURRENT_REF, None)
cache_deletion_order = list(fresh_caches.items())
cache_deletion_order += [(cache["ref"], cache) for cache in caches_not_in_build_matrix]
# Delete caches from end of list to beginning of list
# Delete caches in order of oldest to newest
cache_deletion_order.sort(key=lambda cache_item: cache_item[1]["created_at"], reverse=True)
# Delete current ref cache first
if current_ref_cache:
    cache_deletion_order.append((CURRENT_REF, current_ref_cache))
bytes_required = int(expected_cache_size * 1.2)  # Add 20% margin
GIBIBYTE = 1073741824  # 1 GiB
while (bytes_available := 10 * GIBIBYTE - bytes_used) < bytes_required:
    logging.info(
        f"{bytes_available / GIBIBYTE:.1f} GiB available, {bytes_required / GIBIBYTE:.1f} GiB required"
    )
    if not cache_deletion_order:
        break
    # Delete current ref cache if it exists or delete the oldest cache
    ref, cache = cache_deletion_order.pop(-1)
    if ref == "refs/heads/main":
        continue
    delete_cache(cache)
