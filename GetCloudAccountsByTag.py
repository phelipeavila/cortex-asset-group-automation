"""GetCloudAccountsByTag - Cortex XSIAM/XSOAR Script

Retrieves cloud account IDs (AWS Account, Azure Subscription, GCP Project) that
carry a specific tag, using the Assets API (/public_api/v1/assets).

Azure reports tags inline, in xdm.asset.tags. AWS and GCP do NOT - their tags
must be fetched separately per account from
/public_api/v1/assets/{asset_id}/raw_fields (via core-api-get, asset_id in the
URI, no body):
    - AWS:  reply.data[0]["xdm.asset.raw_fields"]["Platform Discovery"]["Tags"]
            -> a list of {"Key","Value"}
    - GCP:  reply.data[0]["xdm.asset.raw_fields"]["Platform Discovery"]["labels"]
            -> a {key: value} object
This means one extra API call per AWS/GCP account; they are made in parallel
(see max_workers) to keep this from being too slow on large fleets.

Where each asset type gets its tags from is defined in TAG_SOURCE_BY_TYPE below.
If a provider's tag location changes, or another type needs the raw_fields path,
update that map - the matching logic itself does not need to change.

NOTE: demisto.executeCommand is called concurrently from multiple threads here.
If that proves unreliable in your Cortex tenant/engine, set max_workers=1 to
fall back to sequential calls.

This script always scans AWS Account, Azure Subscription and GCP Project assets
(see ASSET_TYPES below) - it is not configurable from the Cortex UI, by design.

Arguments:
    tag_key (str): Required. Tag key to look for.
    tag_value (list): Optional. Comma-separated tag values. When set, the tag must
        have one of these values; when empty, any account with the key matches.
    case_sensitive (bool): Optional. Default: false.
    max_workers (int): Optional. Parallel threads for AWS raw_fields lookups.
        Default: 10. Set to 1 for sequential (safest) execution.
    debug (bool): Optional. Show debug info in output. Default: false.

Output:
    Context path: GetCloudAccountsByTag.values (list of xdm.asset.cloud.account.id)
    Context path: GetCloudAccountsByTag.account_names (list of xdm.asset.name)
    Context path: GetCloudAccountsByTag.results_count
    Context path: GetCloudAccountsByTag.failed_lookups (accounts skipped due to a
        raw_fields fetch error - review with debug=true before trusting the result)
"""

import concurrent.futures
import json
import traceback


# ============================================================================
# CONSTANTS - Modify these to customize the script behavior
# ============================================================================

API_GET_ASSETS = "/public_api/v1/assets"
API_GET_RAW_FIELDS = "/public_api/v1/assets/{asset_id}/raw_fields"

# Fixed scope for this script - not exposed as a Cortex argument on purpose.
ASSET_TYPES = ["AWS Account", "Azure Subscription", "GCP Project"]

ASSET_TYPE_FIELD = "xdm.asset.type.name"
ASSET_ID_FIELD = "xdm.asset.id"
ACCOUNT_ID_FIELD = "xdm.asset.cloud.account.id"
ASSET_NAME_FIELD = "xdm.asset.name"
TAGS_FIELD = "xdm.asset.tags"
RAW_FIELDS_FIELD = "xdm.asset.raw_fields"

# Where to read tags from, per asset type. Anything not listed here falls back to
# DEFAULT_TAG_SOURCE (tags inline in xdm.asset.tags), which is how Azure reports
# them today.
TAG_SOURCE_BY_TYPE = {
    "AWS Account": {
        "source": "raw_fields",
        "category": "Platform Discovery",
        "tags_key": "Tags",
    },
    "GCP Project": {
        "source": "raw_fields",
        "category": "Platform Discovery",
        "tags_key": "labels",
    },
    # "Azure Subscription": {"source": "inline", "field": "xdm.asset.tags"},
}
DEFAULT_TAG_SOURCE = {"source": "inline", "field": TAGS_FIELD}

PAGE_SIZE = 1000  # Matches the page size used by Cortex's other search_from/search_to APIs
MAX_PAGES = 1000  # Safety net against runaway pagination (up to 1,000,000 accounts)

DEFAULT_MAX_WORKERS = 10
MAX_WORKERS_CAP = 25  # Hard ceiling so a bad argument can't hammer the API


# ============================================================================
# API RESPONSE HANDLING
# ============================================================================

def parse_api_response(result: list, operation: str) -> dict:
    """Return the first valid response (containing 'reply') from a core-api-post
    or core-api-get result.

    The API can return an error entry (Type 4) ahead of the valid one, so every
    entry is inspected instead of only the first.
    """
    if not result:
        raise DemistoException(f"{operation}: Empty response from API")

    for entry in result:
        if not isinstance(entry, dict) or entry.get("Type") == 4:
            continue

        contents = entry.get("Contents", {})
        if not isinstance(contents, dict):
            continue

        response = contents.get("response", {})
        if response and "reply" in response:
            return response

    error_msg = get_error(result) if is_error(result) else "No valid response found"
    raise DemistoException(f"{operation}: {error_msg}")


# ============================================================================
# ASSET LISTING (paginated)
# ============================================================================

def build_filters(asset_types: list) -> dict:
    """Build filters: type == A OR type == B ..."""
    return {
        "OR": [
            {"SEARCH_FIELD": ASSET_TYPE_FIELD, "SEARCH_TYPE": "EQ", "SEARCH_VALUE": asset_type}
            for asset_type in asset_types
        ]
    }


def get_account_assets(asset_types: list, debug_info: list) -> list:
    """Fetch every account-level asset of the given types, paginating with search_from/search_to.

    Pages until the API returns fewer than PAGE_SIZE results (or filter_count is reached),
    so tenants with more than one page of matching accounts are handled correctly.
    """
    all_assets = []
    offset = 0
    filters = build_filters(asset_types)
    last_page_first_id = None

    for page_num in range(MAX_PAGES):
        payload = {
            "request_data": {
                "filters": filters,
                "sort": [{"FIELD": ASSET_NAME_FIELD, "ORDER": "DESC"}],
                "search_from": offset,
                "search_to": offset + PAGE_SIZE,
            }
        }
        debug_info.append(f"Fetching assets {offset} to {offset + PAGE_SIZE}")

        result = demisto.executeCommand("core-api-post", {
            "uri": API_GET_ASSETS,
            "body": json.dumps(payload),
        })
        reply = parse_api_response(result, "Query assets").get("reply", {})

        assets = reply.get("data", []) or []
        # metadata.total_count is the whole tenant's asset count; filter_count is the filtered one
        filter_count = (reply.get("metadata") or {}).get("filter_count")
        if offset == 0:
            debug_info.append(f"filter_count reported by API: {filter_count}")

        if not assets:
            debug_info.append(f"Page {page_num + 1}: empty page, stopping")
            break

        # Defensive check: if the API ignores search_from and keeps returning the same
        # page, stop instead of looping until MAX_PAGES.
        page_first_id = assets[0].get(ACCOUNT_ID_FIELD)
        if offset > 0 and page_first_id is not None and page_first_id == last_page_first_id:
            debug_info.append(
                f"Page {page_num + 1}: identical to previous page (search_from not advancing) - stopping"
            )
            break
        last_page_first_id = page_first_id

        all_assets.extend(assets)
        debug_info.append(f"Page {page_num + 1}: fetched {len(assets)} assets (running total: {len(all_assets)})")

        if len(assets) < PAGE_SIZE or (filter_count is not None and len(all_assets) >= filter_count):
            break
        offset += PAGE_SIZE
    else:
        debug_info.append(f"WARNING: stopped after reaching MAX_PAGES ({MAX_PAGES}); results may be incomplete")

    return all_assets


# ============================================================================
# RAW FIELDS LOOKUP (needed for asset types whose tags aren't inline, e.g. AWS)
# ============================================================================

def get_tag_source(asset_type: str) -> dict:
    """Return where to read tags from for this asset type (see TAG_SOURCE_BY_TYPE)."""
    return TAG_SOURCE_BY_TYPE.get(asset_type, DEFAULT_TAG_SOURCE)


def fetch_raw_fields(asset_id: str) -> dict | None:
    """Call /public_api/v1/assets/{asset_id}/raw_fields and return the raw_fields dict.

    Returns None when the API returned no record at all for this asset_id, which is
    reported separately from both successes and errors: such an account ends up
    treated as untagged, so it's worth knowing it happened.
    """
    result = demisto.executeCommand("core-api-get", {
        "uri": API_GET_RAW_FIELDS.format(asset_id=asset_id),
    })
    reply = parse_api_response(result, f"Query raw_fields for {asset_id}").get("reply", {})
    data = reply.get("data") or []
    if not data:
        return None
    return data[0].get(RAW_FIELDS_FIELD) or {}


def extract_tags_from_raw_fields(raw_fields: dict, tag_source: dict) -> dict | list:
    """Pull the tags out of a raw_fields dict per tag_source's category/tags_key.

    Returns whatever shape the provider uses (a list of {Key,Value} for AWS, a
    {key: value} object for GCP); normalize_tags handles both.
    """
    if not isinstance(raw_fields, dict):
        return []
    category_data = raw_fields.get(tag_source.get("category"), {})
    if not isinstance(category_data, dict):
        return []
    return category_data.get(tag_source.get("tags_key", "Tags"), []) or []


def fetch_raw_tags_for_assets(assets: list, max_workers: int, debug_info: list) -> tuple:
    """Fetch raw_fields for each asset in parallel.

    Returns (raw_fields_by_asset_id, failed_assets), where failed_assets is a list
    of (asset, error_message) for assets whose raw_fields call raised an exception -
    those are excluded from results rather than aborting the whole script.

    Assets for which the API returned no record are counted separately (and logged
    to debug_info): they are not errors, but they do end up treated as untagged.
    """
    if not assets:
        return {}, []

    def _fetch(asset):
        asset_id = asset.get(ASSET_ID_FIELD)
        if not asset_id:
            return asset, None, "asset has no xdm.asset.id"
        try:
            return asset, fetch_raw_fields(asset_id), None
        except Exception as ex:  # noqa: BLE001 - one bad account must not abort the batch
            return asset, None, str(ex)

    debug_info.append(f"Fetching raw_fields for {len(assets)} account(s) with max_workers={max_workers}")

    raw_fields_by_asset_id = {}
    failed_assets = []
    empty_assets = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_fetch, asset) for asset in assets]
        for future in concurrent.futures.as_completed(futures):
            asset, raw_fields, error = future.result()
            if error:
                failed_assets.append((asset, error))
            elif raw_fields is None:
                # API answered, but with no record for this asset
                empty_assets.append(asset)
            else:
                raw_fields_by_asset_id[asset.get(ASSET_ID_FIELD)] = raw_fields

    debug_info.append(
        f"raw_fields lookups: {len(raw_fields_by_asset_id)} succeeded, "
        f"{len(empty_assets)} returned no data, {len(failed_assets)} failed"
    )
    if empty_assets:
        sample = "\n".join(f"  {a.get(ACCOUNT_ID_FIELD)}" for a in empty_assets[:20])
        debug_info.append(
            f"raw_fields returned no data - treated as untagged (first 20):\n{sample}"
        )
    if failed_assets:
        sample = "\n".join(
            f"  {a.get(ACCOUNT_ID_FIELD)}: {err}" for a, err in failed_assets[:20]
        )
        debug_info.append(f"raw_fields failures (first 20):\n{sample}")

    return raw_fields_by_asset_id, failed_assets


# ============================================================================
# TAG MATCHING
# ============================================================================

def normalize_tags(tags) -> dict:
    """Return tags as a {key: value} dict.

    xdm.asset.tags normally arrives as an object; AWS raw_fields Tags arrive as a
    list of {"Key","Value"}; ["key:value"] strings are handled defensively too.
    """
    if isinstance(tags, dict):
        return tags

    normalized = {}
    if isinstance(tags, list):
        for item in tags:
            if isinstance(item, dict):
                key = item.get("key", item.get("Key"))
                if key is not None:
                    normalized[str(key)] = item.get("value", item.get("Value", ""))
            elif isinstance(item, str):
                key, _, value = item.partition(":")
                normalized[key] = value
    return normalized


def get_tags_for_asset(asset: dict, raw_fields_by_asset_id: dict) -> dict | list | None:
    """Return this asset's raw tags (dict, list or None - normalize_tags handles all
    three), from whichever source applies to its type. Returns [] if a raw_fields
    lookup was needed but is missing (the lookup failed, or returned no data) -
    such an asset is treated as having no tags.
    """
    tag_source = get_tag_source(asset.get(ASSET_TYPE_FIELD))
    if tag_source["source"] == "raw_fields":
        raw_fields = raw_fields_by_asset_id.get(asset.get(ASSET_ID_FIELD))
        if raw_fields is None:
            return []
        return extract_tags_from_raw_fields(raw_fields, tag_source)
    return asset.get(tag_source["field"])


def asset_has_tag(asset: dict, tag_key: str, tag_values: list, case_sensitive: bool,
                  raw_fields_by_asset_id: dict) -> bool:
    """True if the asset has tag_key (and, when tag_values is set, one of those values)."""
    def norm(val):
        text = str(val) if val is not None else ""
        return text if case_sensitive else text.lower()

    wanted_key = norm(tag_key)
    wanted_values = {norm(v) for v in tag_values}

    tags = get_tags_for_asset(asset, raw_fields_by_asset_id)
    for key, value in normalize_tags(tags).items():
        if norm(key) != wanted_key:
            continue
        if not wanted_values or norm(value) in wanted_values:
            return True
    return False


# ============================================================================
# EXTRACTION AND OUTPUT
# ============================================================================

def extract_accounts(assets: list) -> tuple:
    """Return (unique account IDs, account names) preserving API order."""
    seen = set()
    account_ids = []
    account_names = []

    for asset in assets:
        account_id = asset.get(ACCOUNT_ID_FIELD)
        if not account_id:
            continue
        account_id = str(account_id)
        if account_id in seen:
            continue
        seen.add(account_id)
        account_ids.append(account_id)

        name = asset.get(ASSET_NAME_FIELD)
        if name:
            account_names.append(str(name))

    return account_ids, account_names


def build_output(tag_key: str, tag_values: list, case_sensitive: bool, asset_types: list,
                 total_assets: int, account_ids: list, account_names: list,
                 failed_lookups: list, debug_mode: bool) -> str:
    """Build human-readable output for War Room."""
    case_mode = "case-sensitive" if case_sensitive else "case-insensitive"
    value_display = ", ".join(f"`{v}`" for v in tag_values) if tag_values else "(any)"

    output = (
        f"**Tag Key:** `{tag_key}` ({case_mode})\n"
        f"**Tag Value:** {value_display}\n"
        f"**Asset Types:** {', '.join(f'`{t}`' for t in asset_types)}\n"
        f"**Accounts Scanned:** {total_assets}\n"
        f"**Accounts Matched:** {len(account_ids)}\n"
    )

    if failed_lookups:
        output += (
            f"\n⚠️ **{len(failed_lookups)} account(s) could not be checked** "
            f"(raw_fields fetch failed) and are excluded from the results above. "
            f"Re-run with `debug=true` to see which ones.\n"
        )

    if account_ids:
        output += "\n### Account IDs\n\n```\n" + "\n".join(account_ids) + "\n```"
    if debug_mode and account_names:
        output += "\n\n### Account Names\n\n```\n" + "\n".join(account_names) + "\n```"

    return output


# ============================================================================
# MAIN COMMAND
# ============================================================================

def main():
    """Main entry point."""
    try:
        args = demisto.args()
        tag_key = (args.get("tag_key") or "").strip()
        tag_values = [v.strip() for v in argToList(args.get("tag_value")) if v.strip()]
        case_sensitive = argToBoolean(args.get("case_sensitive", "false"))
        debug_mode = argToBoolean(args.get("debug", "false"))

        try:
            max_workers = int(args.get("max_workers") or DEFAULT_MAX_WORKERS)
        except (TypeError, ValueError):
            raise ValueError("max_workers must be an integer")
        max_workers = max(1, min(max_workers, MAX_WORKERS_CAP))

        if not tag_key:
            raise ValueError("tag_key is required")

        debug_info = [
            f"Arguments - tag_key: {tag_key}, tag_value: {tag_values}, "
            f"case_sensitive: {case_sensitive}, max_workers: {max_workers}"
        ]

        assets = get_account_assets(ASSET_TYPES, debug_info)
        debug_info.append(f"Accounts fetched: {len(assets)}")

        # Only accounts whose type needs a raw_fields lookup (e.g. AWS) require the
        # extra per-account call; everyone else already has tags inline.
        raw_fields_assets = [
            a for a in assets if get_tag_source(a.get(ASSET_TYPE_FIELD))["source"] == "raw_fields"
        ]
        raw_fields_by_asset_id, failed_lookups = fetch_raw_tags_for_assets(
            raw_fields_assets, max_workers, debug_info
        )

        tagged = [
            a for a in assets
            if asset_has_tag(a, tag_key, tag_values, case_sensitive, raw_fields_by_asset_id)
        ]
        debug_info.append(f"Accounts with matching tag: {len(tagged)}")

        account_ids, account_names = extract_accounts(tagged)
        failed_account_ids = [a.get(ACCOUNT_ID_FIELD) for a, _ in failed_lookups]

        readable = build_output(tag_key, tag_values, case_sensitive, ASSET_TYPES,
                                len(assets), account_ids, account_names,
                                failed_account_ids, debug_mode)
        if debug_mode:
            readable += "\n\n### Debug Info\n\n```\n" + "\n".join(debug_info) + "\n```"

        return_results(CommandResults(
            outputs_prefix="GetCloudAccountsByTag",
            outputs_key_field="tag_key",
            outputs={
                "tag_key": tag_key,
                "tag_value": tag_values,
                "results_count": len(account_ids),
                "values": account_ids,
                "account_names": account_names,
                "failed_lookups": failed_account_ids,
            },
            readable_output=readable,
        ))

    except Exception as ex:
        demisto.error(traceback.format_exc())
        return_error(f"GetCloudAccountsByTag failed: {str(ex)}")


if __name__ in ("__main__", "__builtin__", "builtins"):
    main()
