"""GetCloudAccountsByTag - Cortex XSIAM/XSOAR Script

Retrieves cloud account IDs (AWS Account, Azure Subscription, GCP Project) that
carry a specific tag, using a single XQL query on the asset_inventory dataset
(xdr-xql-generic-query, from the Cortex XDR - XQL Query Engine integration).

Each provider keeps its tags in a different place inside xdm.asset.raw_fields;
the query extracts all of them in one pass (see XQL_QUERY_TEMPLATE):
    - AWS:   "Platform Discovery".Tags   -> list of {"Key","Value"} (tags_aws),
             converted to {key: value} here
    - Azure: "Platform Discovery".tags   -> JSON object (tags_azure)
    - GCP:   "Platform Discovery".labels -> JSON object (tags_gcp)
Tag matching (key, optional values, case sensitivity) is then done here, on the
query results.

By default this script scans AWS Account, Azure Subscription and GCP Project
assets (see ASSET_TYPE_BY_PROVIDER below); the cloud_provider argument narrows
that down to one or more providers, in the query itself. The asset type names
themselves are not configurable from the Cortex UI, by design.

Arguments:
    tag_key (str): Required. Tag key to look for.
    tag_value (list): Optional. Comma-separated tag values. When set, the tag must
        have one of these values; when empty, any account with the key matches.
    cloud_provider (list): Optional. Comma-separated cloud providers to scan
        (AWS, Azure, GCP - case-insensitive). When empty, all providers are scanned.
    case_sensitive (bool): Optional. Default: false.
    debug (bool): Optional. Show debug info (query, raw rows) in output. Default: false.

Output:
    Context path: GetCloudAccountsByTag.values (list of xdm.asset.cloud.account.id)
    Context path: GetCloudAccountsByTag.account_names (list of xdm.asset.name)
    Context path: GetCloudAccountsByTag.accounts_by_provider (the same account IDs
        grouped by provider: {"AWS": [...], "AZURE": [...], "GCP": [...]})
    Context path: GetCloudAccountsByTag.results_count
    Context path: GetCloudAccountsByTag.failed_lookups (accounts whose tags could
        not be parsed - they are excluded from the results; review with debug=true)
"""

import json
import time
import traceback


# ============================================================================
# CONSTANTS - Modify these to customize the script behavior
# ============================================================================

XQL_COMMAND = "xdr-xql-generic-query"
XQL_RESULTS_COMMAND = "xdr-xql-get-query-results"  # used only if the query is still pending
XQL_QUERY_NAME = "GetCloudAccountsByTag"
XQL_TIME_FRAME = "7 days"
XQL_TIMEOUT_SECONDS = 300
XQL_POLL_INTERVAL_SECONDS = 10

XQL_STATUS_DONE = ("SUCCESS", "PARTIAL_SUCCESS")
XQL_STATUS_PENDING = ("PENDING",)

# Asset type scanned per cloud provider. Keys are the (lowercase) values accepted
# by the cloud_provider argument; the asset type names are not exposed on purpose.
ASSET_TYPE_BY_PROVIDER = {
    "aws": "AWS Account",
    "azure": "Azure Subscription",
    "gcp": "GCP Project",
}
ASSET_TYPES = list(ASSET_TYPE_BY_PROVIDER.values())

# Query column holding each provider's tags
TAGS_COLUMN_BY_PROVIDER = {
    "aws": "tags_aws",
    "azure": "tags_azure",
    "gcp": "tags_gcp",
}

# {asset_types} is replaced with the quoted, comma-separated asset type names
XQL_QUERY_TEMPLATE = """dataset = asset_inventory
| filter xdm.asset.type.name in ({asset_types})
| alter cloud_provider = if(xdm.asset.type.name = "AWS Account", "aws",
                         if(xdm.asset.type.name = "Azure Subscription", "azure", "gcp"))
| alter tags_aws   = json_extract_array(xdm.asset.raw_fields, "$.Platform Discovery.Tags"),
        tags_azure = json_extract(xdm.asset.raw_fields, "$.Platform Discovery.tags"),
        tags_gcp   = json_extract(xdm.asset.raw_fields, "$.Platform Discovery.labels")
| fields cloud_provider, xdm.asset.cloud.account.id as account_id, xdm.asset.name as account_name,
         tags_aws, tags_azure, tags_gcp
| sort asc cloud_provider, asc account_id"""


# ============================================================================
# XQL QUERY
# ============================================================================

def resolve_providers(cloud_providers: list) -> list:
    """Map the cloud_provider argument (case-insensitive) to provider keys.

    An empty list means every provider. Unknown providers raise a ValueError
    rather than being silently ignored, so a typo can't shrink the scan.
    """
    if not cloud_providers:
        return list(ASSET_TYPE_BY_PROVIDER)

    providers = []
    unknown = []
    for provider in cloud_providers:
        key = provider.lower()
        if key not in ASSET_TYPE_BY_PROVIDER:
            unknown.append(provider)
        elif key not in providers:
            providers.append(key)

    if unknown:
        raise ValueError(
            f"Unknown cloud_provider: {', '.join(unknown)}. "
            f"Valid values (case-insensitive): {', '.join(ASSET_TYPE_BY_PROVIDER)}"
        )
    return providers


def build_query(providers: list) -> str:
    """Build the XQL query, scanning only the given providers' asset types."""
    asset_types = ", ".join(f'"{ASSET_TYPE_BY_PROVIDER[p]}"' for p in providers)
    return XQL_QUERY_TEMPLATE.format(asset_types=asset_types)


def iter_records(data):
    """Yield every dict nested anywhere inside data (lists and dicts)."""
    if isinstance(data, list):
        for item in data:
            yield from iter_records(item)
    elif isinstance(data, dict):
        yield data
        for value in data.values():
            if isinstance(value, (dict, list)):
                yield from iter_records(value)


def find_query_data(result: list, operation: str) -> dict:
    """Return the query status object ({status, execution_id, results, ...}) from
    an XQL command result.

    It is looked for in Contents and EntryContext, since its exact location
    isn't documented. Error entries (Type 4) are skipped.
    """
    for entry in result or []:
        if not isinstance(entry, dict) or entry.get("Type") == 4:
            continue
        for data in (entry.get("Contents"), entry.get("EntryContext")):
            for record in iter_records(data):
                if "status" in record and ("results" in record or "execution_id" in record):
                    return record

    error_msg = get_error(result) if is_error(result) else "No query results found"
    raise DemistoException(f"{operation}: {error_msg}")


def run_query(query: str, debug_info: list) -> tuple:
    """Run the XQL query and return (rows, warning).

    When the command returns while the query is still pending, its results are
    polled with xdr-xql-get-query-results until done or XQL_TIMEOUT_SECONDS.
    warning is set when the query reports more results than it returned.
    """
    debug_info.append(f"XQL query:\n{query}")
    result = demisto.executeCommand(XQL_COMMAND, {
        "query": query,
        "time_frame": XQL_TIME_FRAME,
        "query_name": XQL_QUERY_NAME,
    })
    data = find_query_data(result, XQL_COMMAND)

    deadline = time.time() + XQL_TIMEOUT_SECONDS
    while str(data.get("status")).upper() in XQL_STATUS_PENDING:
        execution_id = data.get("execution_id")
        if not execution_id:
            raise DemistoException("XQL query is pending but returned no execution_id to poll")
        if time.time() > deadline:
            raise DemistoException(f"XQL query {execution_id} still pending after {XQL_TIMEOUT_SECONDS}s")
        debug_info.append(f"Query {execution_id} pending, polling again in {XQL_POLL_INTERVAL_SECONDS}s")
        time.sleep(XQL_POLL_INTERVAL_SECONDS)  # noqa: polling an async query
        result = demisto.executeCommand(XQL_RESULTS_COMMAND, {"query_id": execution_id})
        data = find_query_data(result, XQL_RESULTS_COMMAND)

    status = str(data.get("status")).upper()
    if status not in XQL_STATUS_DONE:
        raise DemistoException(f"XQL query failed with status {status}: {data.get('error') or ''}")

    rows = [r for r in (data.get("results") or []) if isinstance(r, dict)]
    reported = data.get("number_of_results")
    debug_info.append(f"Query status: {status}, rows returned: {len(rows)}, number_of_results: {reported}")

    warning = None
    if isinstance(reported, int) and reported > len(rows):
        warning = (f"The query reported {reported} results but only {len(rows)} were returned - "
                   f"the result may be incomplete.")
    return rows, warning


# ============================================================================
# TAG MATCHING
# ============================================================================

def parse_tags(raw) -> dict:
    """Return a row's tags as a {key: value} dict.

    Azure and GCP tags are a {key: value} object; AWS tags are a list of
    {"Key", "Value"}. Either may arrive already parsed or as a JSON string (and
    AWS list items as JSON strings too). An empty value means no tags. Raises
    ValueError when the value can't be parsed.
    """
    if raw in (None, "", "null"):
        return {}
    tags = json.loads(raw) if isinstance(raw, str) else raw
    if tags is None:
        return {}
    if isinstance(tags, dict):
        return tags
    if not isinstance(tags, list):
        raise ValueError(f"expected a JSON object or list, got {type(tags).__name__}")

    normalized = {}
    for item in tags:
        if isinstance(item, str):
            item = json.loads(item)
        if not isinstance(item, dict) or "Key" not in item:
            raise ValueError(f"unexpected tag item: {item!r}")
        value = item.get("Value")
        normalized[str(item["Key"])] = "" if value is None else value
    return normalized


def row_has_tag(tags: dict, tag_key: str, tag_values: list, case_sensitive: bool) -> bool:
    """True if tags has tag_key (and, when tag_values is set, one of those values)."""
    def norm(val):
        text = str(val) if val is not None else ""
        return text if case_sensitive else text.lower()

    wanted_key = norm(tag_key)
    wanted_values = {norm(v) for v in tag_values}

    for key, value in tags.items():
        if norm(key) != wanted_key:
            continue
        if not wanted_values or norm(value) in wanted_values:
            return True
    return False


def match_rows(rows: list, tag_key: str, tag_values: list, case_sensitive: bool,
               debug_info: list) -> tuple:
    """Return (matching rows, rows whose tags couldn't be parsed)."""
    matched = []
    failed = []

    for row in rows:
        provider = str(row.get("cloud_provider") or "").lower()
        column = TAGS_COLUMN_BY_PROVIDER.get(provider)
        if column is None:
            failed.append((row, f"unknown cloud_provider {provider!r}"))
            continue
        try:
            tags = parse_tags(row.get(column))
        except ValueError as ex:  # json.JSONDecodeError is a ValueError
            failed.append((row, f"could not parse {column}: {ex}"))
            continue
        if row_has_tag(tags, tag_key, tag_values, case_sensitive):
            matched.append(row)

    if failed:
        sample = "\n".join(f"  {r.get('account_id')}: {err}" for r, err in failed[:20])
        debug_info.append(f"Rows whose tags could not be parsed (first 20):\n{sample}")
    return matched, failed


# ============================================================================
# EXTRACTION AND OUTPUT
# ============================================================================

def extract_accounts(rows: list) -> tuple:
    """Return (unique account IDs, account names, account IDs grouped by provider)
    preserving query order. Providers are keyed in uppercase (AWS, AZURE, GCP),
    matching the AppSec Applications API provider values."""
    seen = set()
    account_ids = []
    account_names = []
    accounts_by_provider = {}

    for row in rows:
        account_id = row.get("account_id")
        if not account_id:
            continue
        account_id = str(account_id)
        if account_id in seen:
            continue
        seen.add(account_id)
        account_ids.append(account_id)

        provider = str(row.get("cloud_provider") or "other").upper()
        accounts_by_provider.setdefault(provider, []).append(account_id)

        name = row.get("account_name")
        if name:
            account_names.append(str(name))

    return account_ids, account_names, accounts_by_provider


def build_output(tag_key: str, tag_values: list, case_sensitive: bool, providers: list,
                 total_rows: int, account_ids: list, account_names: list,
                 failed_lookups: list, warning: str | None, debug_mode: bool) -> str:
    """Build human-readable output for War Room."""
    case_mode = "case-sensitive" if case_sensitive else "case-insensitive"
    value_display = ", ".join(f"`{v}`" for v in tag_values) if tag_values else "(any)"
    asset_types = [ASSET_TYPE_BY_PROVIDER[p] for p in providers]

    output = (
        f"**Tag Key:** `{tag_key}` ({case_mode})\n"
        f"**Tag Value:** {value_display}\n"
        f"**Asset Types:** {', '.join(f'`{t}`' for t in asset_types)}\n"
        f"**Accounts Scanned:** {total_rows}\n"
        f"**Accounts Matched:** {len(account_ids)}\n"
    )

    if warning:
        output += f"\n⚠️ **{warning}**\n"
    if failed_lookups:
        output += (
            f"\n⚠️ **{len(failed_lookups)} account(s) could not be checked** "
            f"(tags could not be parsed) and are excluded from the results above. "
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
        cloud_providers = [p.strip() for p in argToList(args.get("cloud_provider")) if p.strip()]
        case_sensitive = argToBoolean(args.get("case_sensitive", "false"))
        debug_mode = argToBoolean(args.get("debug", "false"))

        if not tag_key:
            raise ValueError("tag_key is required")

        providers = resolve_providers(cloud_providers)

        debug_info = [
            f"Arguments - tag_key: {tag_key}, tag_value: {tag_values}, "
            f"cloud_provider: {cloud_providers}, case_sensitive: {case_sensitive}",
        ]

        rows, warning = run_query(build_query(providers), debug_info)
        matched, failed = match_rows(rows, tag_key, tag_values, case_sensitive, debug_info)
        debug_info.append(f"Accounts with matching tag: {len(matched)}")

        account_ids, account_names, accounts_by_provider = extract_accounts(matched)
        failed_account_ids = [r.get("account_id") for r, _ in failed]

        readable = build_output(tag_key, tag_values, case_sensitive, providers,
                                len(rows), account_ids, account_names,
                                failed_account_ids, warning, debug_mode)
        if debug_mode:
            readable += "\n\n### Debug Info\n\n```\n" + "\n".join(debug_info) + "\n```"

        return_results(CommandResults(
            outputs_prefix="GetCloudAccountsByTag",
            outputs_key_field="tag_key",
            outputs={
                "tag_key": tag_key,
                "tag_value": tag_values,
                "cloud_provider": cloud_providers,
                "results_count": len(account_ids),
                "values": account_ids,
                "account_names": account_names,
                "accounts_by_provider": accounts_by_provider,
                "failed_lookups": failed_account_ids,
            },
            readable_output=readable,
        ))

    except Exception as ex:
        demisto.error(traceback.format_exc())
        return_error(f"GetCloudAccountsByTag failed: {str(ex)}")


if __name__ in ("__main__", "__builtin__", "builtins"):
    main()
