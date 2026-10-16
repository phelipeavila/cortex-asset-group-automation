"""CreateApplication - Cortex Cloud Script

Creates or updates Business Applications (AppSec) from the cloud accounts that
carry a given tag. If an application with the same name exists, it is updated;
otherwise, a new one is created.

Accounts are found with a single XQL query on the asset_inventory dataset
(xdr-xql-generic-query, from the Cortex XDR - XQL Query Engine integration,
which must be enabled). Each provider keeps its tags in a different place
inside xdm.asset.raw_fields; the query extracts all of them in one pass (see
XQL_QUERY_TEMPLATE):
    - AWS:   "Platform Discovery".Tags   -> list of {"Key","Value"} (tags_aws),
             converted to {key: value} here
    - Azure: "Platform Discovery".tags   -> JSON object (tags_azure)
    - GCP:   "Platform Discovery".labels -> JSON object (tags_gcp)
Tag matching (key, optional values, case sensitivity) is then done here, on the
query results. This is the same lookup as the GetCloudAccountsByTag script,
embedded so this script has no dependency on it.

An application's asset filter takes a single provider, so accounts are grouped
by provider (AWS, AZURE, GCP):
    - one provider found:   one application, named exactly application_name
    - several found:        one application per provider, named
                            "<application_name> - <PROVIDER>" (APP_NAME_FORMAT)

Uses the AppSec Applications API via the Core REST API commands:
    - GET    /public_api/appsec/v1/application        (core-api-get, paginated)
    - POST   /public_api/appsec/v1/application        (core-api-post)
    - PUT    /public_api/appsec/v1/application/{id}   (core-api-put)
    - DELETE /public_api/appsec/v1/application/{id}   (core-api-delete)

Each application selects its assets with a "run" section ACCOUNT filter:
    {"selectionType": "filter", "section": "run",
     "filter": {"filterType": "ACCOUNT", "values": [...], "provider": "AWS"}}

LIMITATION: the update API (PUT) only accepts metadata (criticality, owners,
description...) - NOT the asset selection. So the account list is only set
when the application is created. When it differs from the existing one:
    - recreate_on_change=false (default): metadata is updated and a warning is
      returned; the existing account selection is left as is.
    - recreate_on_change=true: the application is deleted and created again
      with the new accounts. Its metadata (criticality, owners...) is carried
      over, but it gets a NEW application ID, and manual asset overrides are lost.
      If the create fails after the delete, the application is gone - use
      dry_run first.

Arguments:
    application_name (str): Required. Application name (or name prefix, when
        accounts span several providers).
    tag_key (str): Required. Tag key to look for.
    tag_value (list): Optional. Tag values; when empty, any value matches.
    cloud_provider (list): Optional. AWS, Azure, GCP (case-insensitive). When
        empty, all providers are scanned.
    case_sensitive (bool): Optional. Tag key/value matching. Default: false.
    business_criticality (str): Optional. Critical, High, Medium or Low.
        Default on create: Medium. On update, only changed when provided.
    description (str): Optional.
    business_unit (str): Optional.
    compliance (str): Optional. PCI-DSS, ISO 27001, SOX, NIST, GDPR, CCPA,
        HIPAA or FedRAMP.
    business_owner, dev_owner, devops_owner, product_manager (list): Optional.
    recreate_on_change (bool): Optional. See LIMITATION above. Default: false.
    dry_run (bool): Optional. Preview changes without executing them.
    debug (bool): Optional. Show the API requests and responses in output.

Output:
    Context path: CreateApplication (one entry per application)
        - application_id: The application ID
        - application_name: The application name
        - provider: AWS/AZURE/GCP
        - action: created/updated/recreated/unchanged/failed (or "would be ..."
          in dry run). "unchanged" = the application exists and no metadata
          arguments were provided, so there was nothing the API could update.
        - account_ids / account_count: Accounts found for this provider
        - accounts_changed: Whether they differ from the existing application's
        - accounts_added / accounts_removed: Found accounts missing from /
          extra in the existing application's selection (before this run)
        - status: success/warning/failed/dry_run
        - message: Warning or error text, if any
"""

import traceback
import json
import time


# =============================================================================
# CONSTANTS
# =============================================================================

XQL_COMMAND = "xdr-xql-generic-query"
XQL_RESULTS_COMMAND = "xdr-xql-get-query-results"  # used only if the query is still pending
XQL_QUERY_NAME = "CreateApplication"
XQL_TIME_FRAME = "7 days"
XQL_TIMEOUT_SECONDS = 300
XQL_POLL_INTERVAL_SECONDS = 10

XQL_STATUS_DONE = ("SUCCESS", "PARTIAL_SUCCESS")
XQL_STATUS_PENDING = ("PENDING",)

# Asset type scanned per cloud provider. Keys are the (lowercase) values accepted
# by the cloud_provider argument and returned in the query's cloud_provider column.
ASSET_TYPE_BY_PROVIDER = {
    "aws": "AWS Account",
    "azure": "Azure Subscription",
    "gcp": "GCP Project",
}

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

API_APPLICATIONS = "/public_api/appsec/v1/application"
API_APPLICATION = "/public_api/appsec/v1/application/{app_id}"

PAGE_SIZE = 100
FIRST_PAGE = 1     # Pages start at 1 per the AppSec API docs
MAX_PAGES = 1000   # Safety net against runaway pagination

# Name used per provider when the tagged accounts span more than one provider
APP_NAME_FORMAT = "{name} - {provider}"

CREATION_TYPE = "Manual"
DEFAULT_CRITICALITY = "Medium"
SECTION = "run"
SELECTION_TYPE = "filter"
FILTER_TYPE = "ACCOUNT"

# Accepted values, keyed by lowercase input -> value sent to the API.
# PROVIDERS keys match ASSET_TYPE_BY_PROVIDER's.
PROVIDERS = {p.lower(): p for p in ("AWS", "AZURE", "GCP")}
CRITICALITIES = {c.lower(): c for c in ("Critical", "High", "Medium", "Low")}
COMPLIANCES = {c.lower(): c for c in (
    "PCI-DSS", "ISO 27001", "SOX", "NIST", "GDPR", "CCPA", "HIPAA", "FedRAMP"
)}

# Script argument -> API field, for the list-valued owner fields
OWNER_FIELDS = {
    "business_owner": "businessOwner",
    "dev_owner": "devOwner",
    "devops_owner": "devOpsOwner",
    "product_manager": "productManager",
}


# =============================================================================
# API RESPONSE HANDLING
# =============================================================================

def parse_api_response(result: list, operation: str):
    """
    Return the response body from a core-api-* command result.

    The AppSec API returns its body directly (not wrapped in 'reply' like the
    v1 public APIs), so 'reply' is unwrapped only when present. Error entries
    (Type 4) ahead of the valid one are skipped.

    Args:
        result: The raw result from demisto.executeCommand()
        operation: Name of the operation (for error messages)

    Returns:
        The response body (dict or list)

    Raises:
        DemistoException: If no valid response is found
    """
    if not result:
        raise DemistoException(f"{operation}: Empty response from API")

    for entry in result:
        if not isinstance(entry, dict) or entry.get("Type") == 4:
            continue

        contents = entry.get("Contents", {})
        if not isinstance(contents, dict):
            continue

        response = contents.get("response")
        if isinstance(response, dict) and "reply" in response:
            return response["reply"]
        if response is not None:
            return response

    error_msg = get_error(result) if is_error(result) else "No valid response found"
    raise DemistoException(f"{operation}: {error_msg}")


def call_api(command: str, uri: str, operation: str, debug_info: list, body: dict = None):
    """Run a core-api-* command, log it to debug_info and return the parsed body."""
    args = {"uri": uri}
    if body is not None:
        args["body"] = json.dumps(body)
    debug_info.append(f"{command} {uri}" + (f"\n  body: {args['body']}" if body is not None else ""))

    result = demisto.executeCommand(command, args)
    response = parse_api_response(result, operation)
    debug_info.append(f"  response: {json.dumps(response, default=str)[:2000]}")
    return response


# =============================================================================
# ARGUMENT HELPERS
# =============================================================================

def normalize_choice(value: str, choices: dict, arg_name: str) -> str | None:
    """
    Map a case-insensitive argument value to its canonical API value.

    Returns None for an empty value; raises ValueError for an unknown one.
    """
    if not value:
        return None
    canonical = choices.get(value.strip().lower())
    if canonical is None:
        raise ValueError(f"Invalid {arg_name}: {value}. Valid values: {', '.join(choices.values())}")
    return canonical


def unique(values: list) -> list:
    """Return the non-empty values, stripped and deduplicated, preserving order."""
    seen = set()
    result = []
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def build_metadata(args: dict) -> dict:
    """
    Build the metadata fields accepted by both create and update.

    Only arguments that were actually provided are included, so an update
    never blanks out existing values.
    """
    metadata = {}

    criticality = normalize_choice(args.get("business_criticality"), CRITICALITIES, "business_criticality")
    if criticality:
        metadata["businessCriticality"] = criticality

    compliance = normalize_choice(args.get("compliance"), COMPLIANCES, "compliance")
    if compliance:
        metadata["compliance"] = compliance

    if args.get("description"):
        metadata["description"] = args["description"]
    if args.get("business_unit"):
        metadata["businessUnit"] = args["business_unit"]

    for arg_name, field in OWNER_FIELDS.items():
        owners = unique(argToList(args.get(arg_name)))
        if owners:
            metadata[field] = owners

    return metadata


def existing_metadata(app: dict) -> dict:
    """
    Return the metadata fields of an existing application, so a recreated
    application keeps them (arguments provided on this run override them).
    """
    fields = ("businessCriticality", "compliance", "description", "businessUnit",
              *OWNER_FIELDS.values())
    return {f: app[f] for f in fields if app.get(f) not in (None, "", [])}


def build_asset_selection(account_ids: list, provider: str) -> dict:
    """Build the "run" section ACCOUNT filter that selects the application's assets."""
    return {
        "selectionType": SELECTION_TYPE,
        "section": SECTION,
        "filter": {"filterType": FILTER_TYPE, "values": account_ids, "provider": provider},
    }


# =============================================================================
# ACCOUNT LOOKUP (XQL query on asset_inventory)
# =============================================================================

def resolve_providers(cloud_providers: list) -> list:
    """
    Map the cloud_provider argument (case-insensitive) to provider keys.

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
    """
    Return the query status object ({status, execution_id, results, ...}) from
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
    """
    Run the XQL query and return (rows, warning).

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
                   f"the account list may be incomplete.")
    return rows, warning


def parse_tags(raw) -> dict:
    """
    Return a row's tags as a {key: value} dict.

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


def has_tag(tags: dict, tag_key: str, tag_values: list, case_sensitive: bool) -> bool:
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


def find_tagged_accounts(providers: list, tag_key: str, tag_values: list, case_sensitive: bool,
                         debug_info: list) -> tuple:
    """
    Run the XQL query and return (groups, failed_account_ids, warning).

    groups is {provider: unique account IDs} with API provider values (AWS,
    AZURE, GCP) in that order, empty groups dropped. failed_account_ids are the
    accounts whose tags couldn't be parsed - they are left out of groups.
    """
    rows, warning = run_query(build_query(providers), debug_info)

    matched = {p: [] for p in PROVIDERS}
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
        if row.get("account_id") and has_tag(tags, tag_key, tag_values, case_sensitive):
            matched[provider].append(row["account_id"])

    groups = {PROVIDERS[p]: unique(ids) for p, ids in matched.items() if ids}
    debug_info.append(f"Tagged accounts by provider: {json.dumps(groups)}")
    if failed:
        sample = "\n".join(f"  {r.get('account_id')}: {err}" for r, err in failed[:20])
        debug_info.append(f"Rows whose tags could not be parsed (first 20):\n{sample}")

    return groups, [r.get("account_id") for r, _ in failed], warning


def application_names(base_name: str, providers: list) -> dict:
    """Return {provider: application name}: the base name alone for a single provider."""
    if len(providers) == 1:
        return {providers[0]: base_name}
    return {p: APP_NAME_FORMAT.format(name=base_name, provider=p) for p in providers}


# =============================================================================
# API OPERATIONS
# =============================================================================

def list_applications(debug_info: list) -> dict:
    """
    Return every application, keyed by name.

    The list API has no name filter, so all pages are read (once) and the
    applications are matched by name locally.
    """
    apps = {}
    for page in range(FIRST_PAGE, FIRST_PAGE + MAX_PAGES):
        uri = f"{API_APPLICATIONS}?page={page}&pageSize={PAGE_SIZE}"
        response = call_api("core-api-get", uri, "List applications", debug_info)

        data = response.get("data", []) if isinstance(response, dict) else response or []
        for app in data:
            if isinstance(app, dict) and app.get("name"):
                apps[app["name"]] = app

        if not isinstance(response, dict) or not response.get("hasNext") or not data:
            return apps

    debug_info.append(f"WARNING: stopped after reaching MAX_PAGES ({MAX_PAGES})")
    return apps


def get_current_selection(app: dict) -> tuple:
    """
    Return (account_ids, provider) of an existing application's ACCOUNT filter.

    Returns (None, None) when the application doesn't select assets by
    account (e.g. it was built from code repositories or in the UI with
    another filter), in which case it can't be compared.
    """
    selection = (app.get("config") or {}).get("assetSelection") or {}
    selection_filter = selection.get("filter")
    if (selection.get("section") != SECTION
            or not isinstance(selection_filter, dict)
            or selection_filter.get("filterType") != FILTER_TYPE):
        return None, None
    return unique(selection_filter.get("values") or []), selection_filter.get("provider")


def create_application(app_name: str, metadata: dict, account_ids: list, provider: str,
                       debug_info: list) -> str | None:
    """Create the application and return its ID."""
    body = {
        "name": app_name,
        "creationType": CREATION_TYPE,
        "businessCriticality": DEFAULT_CRITICALITY,
        **metadata,
        "assetSelection": build_asset_selection(account_ids, provider),
    }
    response = call_api("core-api-post", API_APPLICATIONS, "Create application", debug_info, body)
    return response.get("applicationId") if isinstance(response, dict) else None


def update_application(app_id: str, metadata: dict, debug_info: list) -> None:
    """Update the application's metadata (the API doesn't accept assetSelection)."""
    call_api("core-api-put", API_APPLICATION.format(app_id=app_id), "Update application",
             debug_info, metadata)


def delete_application(app_id: str, debug_info: list) -> None:
    """Delete the application."""
    call_api("core-api-delete", API_APPLICATION.format(app_id=app_id), "Delete application",
             debug_info)


def apply_application(app_name: str, provider: str, account_ids: list, metadata: dict,
                      existing: dict | None, recreate_on_change: bool, dry_run: bool,
                      debug_info: list) -> dict:
    """
    Create, update or recreate one application and return its output entry.

    Args:
        app_name: Application name
        provider: AWS/AZURE/GCP
        account_ids: Accounts the application should select
        metadata: Metadata fields from the arguments
        existing: The existing application with this name, or None
        recreate_on_change: Delete + recreate when the accounts changed
        dry_run: Only compute the action, don't call the write APIs
        debug_info: List that collects debug lines
    """
    warnings = []
    added, removed = [], []
    accounts_changed = False

    if existing is None:
        app_id = None
        action = "created"
    else:
        app_id = existing.get("id")
        if not app_id:
            raise ValueError(f"Could not read the application ID. Available fields: {list(existing.keys())}")

        current_accounts, current_provider = get_current_selection(existing)
        if current_accounts is None:
            accounts_changed = True
            warnings.append("The existing application doesn't select assets by account, so its "
                            "selection couldn't be compared with the tagged accounts.")
        else:
            added = [a for a in account_ids if a not in current_accounts]
            removed = [a for a in current_accounts if a not in account_ids]
            accounts_changed = bool(added or removed) or current_provider != provider

        if accounts_changed and recreate_on_change:
            action = "recreated"
            warnings.append("The application was deleted and created again with the new accounts: "
                            "it has a new ID, and manual asset overrides were lost.")
        else:
            # Only metadata can be updated; with none provided there's nothing to send
            action = "updated" if metadata else "unchanged"
            if accounts_changed:
                warnings.append("The account selection was NOT changed - the update API only accepts "
                                "metadata. Run with recreate_on_change=true to apply the new accounts.")

    if dry_run:
        debug_info.append(f"[{app_name}] would send assetSelection: "
                          f"{json.dumps(build_asset_selection(account_ids, provider))}")
        app_id = app_id or "(new)"
    elif action == "created":
        app_id = create_application(app_name, metadata, account_ids, provider, debug_info)
    elif action == "recreated":
        delete_application(app_id, debug_info)
        app_id = create_application(app_name, {**existing_metadata(existing), **metadata},
                                    account_ids, provider, debug_info)
    elif action == "updated":
        update_application(app_id, metadata, debug_info)

    return {
        "application_id": app_id,
        "application_name": app_name,
        "provider": provider,
        "action": f"would be {action}" if dry_run and action != "unchanged" else action,
        "account_ids": account_ids,
        "account_count": len(account_ids),
        "accounts_changed": accounts_changed,
        "accounts_added": added,
        "accounts_removed": removed,
        "status": "dry_run" if dry_run else ("warning" if warnings else "success"),
        "message": " ".join(warnings),
    }


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_output(tag_key: str, tag_values: list, results: list, notes: list, dry_run: bool) -> str:
    """Format the human-readable output for War Room."""
    value_display = ", ".join(f"`{v}`" for v in tag_values) if tag_values else "(any)"
    text = "### 🔍 DRY RUN - No Changes Made\n\n" if dry_run else "### Applications by Tag\n\n"
    text += f"**Tag Key:** `{tag_key}`\n**Tag Value:** {value_display}\n\n"

    if results:
        text += "| Application | Provider | Action | Accounts | Application ID |\n"
        text += "|---|---|---|---|---|\n"
        for r in results:
            text += (f"| {r['application_name']} | {r['provider']} | {r['action']} | "
                     f"{r['account_count']} | `{r['application_id']}` |\n")

    for r in results:
        # Diff against the existing application's selection (before this run)
        details = []
        if r["accounts_added"]:
            details.append(f"requested, not in existing application: {', '.join(r['accounts_added'])}")
        if r["accounts_removed"]:
            details.append(f"in existing application, not requested: {', '.join(r['accounts_removed'])}")
        if r["message"]:
            details.append(r["message"])
        if details:
            text += f"\n**{r['application_name']}**\n" + "".join(f"- {d}\n" for d in details)

    for note in notes:
        text += f"\n⚠️ {note}\n"
    return text


# =============================================================================
# MAIN COMMAND
# =============================================================================

def main():
    """
    Main entry point for the script.

    Finds the tagged accounts, groups them by provider and creates, updates
    or recreates one application per group. One application failing doesn't
    stop the others; the script only errors out if every one failed.
    """
    try:
        args = demisto.args()

        # Parse and validate arguments
        base_name = (args.get("application_name") or "").strip()
        tag_key = (args.get("tag_key") or "").strip()
        tag_values = unique(argToList(args.get("tag_value")))
        cloud_providers = unique(argToList(args.get("cloud_provider")))
        case_sensitive = argToBoolean(args.get("case_sensitive", "false"))
        recreate_on_change = argToBoolean(args.get("recreate_on_change", "false"))
        dry_run = argToBoolean(args.get("dry_run", "false"))
        debug_mode = argToBoolean(args.get("debug", "false"))

        if not base_name:
            raise ValueError("application_name is required")
        if not tag_key:
            raise ValueError("tag_key is required")

        providers = resolve_providers(cloud_providers)
        metadata = build_metadata(args)
        debug_info = []
        notes = []

        # Find the tagged accounts, grouped by provider
        groups, failed_lookups, query_warning = find_tagged_accounts(
            providers, tag_key, tag_values, case_sensitive, debug_info
        )
        if query_warning:
            notes.append(query_warning)
        if failed_lookups:
            notes.append(f"{len(failed_lookups)} account(s) could not be checked for the tag (their tags "
                         f"could not be parsed) and were left out - run with debug=true to see which.")

        results = []
        if not groups:
            notes.append("No accounts matched the tag - no application was created or updated.")
        else:
            names = application_names(base_name, list(groups))
            apps = list_applications(debug_info)

            # Applications left from a run that grouped the providers differently
            # (e.g. "<name>" from a single-provider run, now split per provider)
            candidates = {base_name} | {APP_NAME_FORMAT.format(name=base_name, provider=p)
                                        for p in PROVIDERS.values()}
            stale = sorted(candidates & set(apps) - set(names.values()))
            if stale:
                notes.append(f"Existing application(s) not touched by this run: {', '.join(stale)} - "
                             f"review and delete them if they are no longer needed.")

            for provider, account_ids in groups.items():
                app_name = names[provider]
                try:
                    results.append(apply_application(
                        app_name, provider, account_ids, metadata, apps.get(app_name),
                        recreate_on_change, dry_run, debug_info
                    ))
                except Exception as ex:  # noqa: BLE001 - one application must not block the others
                    demisto.error(traceback.format_exc())
                    results.append({
                        "application_id": None, "application_name": app_name, "provider": provider,
                        "action": "failed", "account_ids": account_ids, "account_count": len(account_ids),
                        "accounts_changed": False, "accounts_added": [], "accounts_removed": [],
                        "status": "failed", "message": str(ex),
                    })

        if results and all(r["status"] == "failed" for r in results):
            raise DemistoException("; ".join(f"{r['application_name']}: {r['message']}" for r in results))

        readable = format_output(tag_key, tag_values, results, notes, dry_run)
        if debug_mode or dry_run:
            readable += "\n\n### Debug Info\n\n```\n" + "\n".join(debug_info) + "\n```"

        return_results(CommandResults(
            outputs_prefix="CreateApplication",
            outputs_key_field="application_name",
            outputs=results,
            readable_output=readable
        ))

    except Exception as ex:
        demisto.error(traceback.format_exc())
        return_error(f"CreateApplication failed: {str(ex)}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ in ("__main__", "__builtin__", "builtins"):
    main()
