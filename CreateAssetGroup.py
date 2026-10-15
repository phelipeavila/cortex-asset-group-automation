"""CreateAssetGroup - Cortex XSIAM/XSOAR Script

Creates or updates a dynamic asset group based on a list of cloud account IDs.
If an asset group with the same name exists, it will be updated;
otherwise, a new group will be created.

Uses the platform's native asset group commands (no direct API calls):
    - getAssetGroup:    look up an existing group by name
    - createAssetGroup: create a new group
    - setAssetGroup:    update an existing group (by group_id)

Arguments:
    group_name (str): Required. Name for the asset group.
    account_ids (list): Required. Comma-separated list of cloud account IDs
        (AWS Account, Azure Subscription, GCP Project) - e.g. the output of
        GetCloudAccounts / GetCloudAccountsByTag.
    group_description (str): Optional. Description for the asset group.
    dry_run (bool): Optional. Preview changes without executing them.
    debug (bool): Optional. Show the raw command results in output. Default: false.

Output:
    Context path: CreateAssetGroup
        - group_id: The asset group ID
        - group_name: The asset group name
        - action: created/updated/would be created/would be updated
        - account_count: Number of accounts included
        - status: success/dry_run
"""

import traceback
import json


# =============================================================================
# TEST INPUTS - TEMPORARY, remove this section (and its use in main) after testing
# =============================================================================
# When USE_TEST_ARGS is True, these values replace the script arguments.
# Run twice: the 1st run should create the group, the 2nd should update it.

USE_TEST_ARGS = True

TEST_ARGS = {
    "group_name": "TEST - CreateAssetGroup script",
    "account_ids": ["279251427966"],
    "group_description": "Test group created by CreateAssetGroup script",
    "dry_run": "false",
    "debug": "true",
}


# =============================================================================
# CONSTANTS
# =============================================================================

CMD_GET_GROUP = "getAssetGroup"
CMD_CREATE_GROUP = "createAssetGroup"
CMD_UPDATE_GROUP = "setAssetGroup"

DEFAULT_DESCRIPTION = "Dynamic asset group created by automation script"
GROUP_TYPE = "Dynamic"

# Field names that may hold the group ID / name in the command results, checked
# case-insensitively and in this order. The commands' exact output shape isn't
# documented, so both the API-style (XDM.ASSET_GROUP.*) and plain names are tried.
GROUP_ID_KEYS = ("xdm.asset_group.id", "asset_group_id", "group_id", "id")
GROUP_NAME_KEYS = ("xdm.asset_group.name", "group_name", "name")

# For the create result, a bare "id" is too generic to trust - if none of these
# is found, the new group is looked up by name instead.
CREATED_ID_KEYS = ("xdm.asset_group.id", "asset_group_id", "group_id")


# =============================================================================
# COMMAND EXECUTION
# =============================================================================

def run_command(command: str, args: dict, debug_info: list) -> list:
    """
    Run a platform command and return its non-error entries.

    The platform may return an error entry (Type 4) ahead of the valid one,
    so error entries are skipped; the command only fails if nothing else
    came back.

    Args:
        command: Name of the command to execute
        args: Command arguments
        debug_info: List that collects debug lines

    Returns:
        The list of non-error result entries

    Raises:
        DemistoException: If the command returned only error entries
    """
    result = demisto.executeCommand(command, args) or []
    debug_info.append(f"{command} args: {json.dumps(args)}")
    debug_info.append(f"{command} raw result: {json.dumps(result, default=str)[:3000]}")

    entries = [e for e in result if isinstance(e, dict) and e.get("Type") != 4]
    if not entries:
        error_msg = get_error(result) if is_error(result) else "Empty response"
        raise DemistoException(f"{command} failed: {error_msg}")
    return entries


def entries_data(entries: list) -> list:
    """
    Collect everything a command returned: Contents (parsed if it is a JSON
    string) and EntryContext of every entry.
    """
    data = []
    for entry in entries:
        contents = entry.get("Contents")
        if isinstance(contents, str):
            try:
                contents = json.loads(contents)
            except ValueError:
                contents = None
        if contents:
            data.append(contents)
        if entry.get("EntryContext"):
            data.append(entry["EntryContext"])
    return data


# =============================================================================
# ASSET GROUP HELPERS
# =============================================================================

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


def get_field(record: dict, keys: tuple):
    """
    Return the first non-empty value among keys, matching keys case-insensitively.

    Args:
        record: Dictionary to read from
        keys: Candidate field names, in priority order (lowercase)

    Returns:
        The value found, or None
    """
    lowered = {str(k).lower(): v for k, v in record.items()}
    for key in keys:
        value = lowered.get(key)
        if value not in (None, ""):
            return value
    return None


def build_membership_predicate(account_ids: list) -> dict:
    """
    Build the membership predicate for dynamic asset group filtering.

    Creates a predicate structure that matches assets belonging to any
    of the specified cloud accounts using OR logic within an AND wrapper.
    Accounts are matched on xdm.asset.realm, which equals the cloud account ID
    (xdm.asset.cloud.account.id) for AWS, Azure and GCP.

    Structure:
        {
            "AND": [{
                "OR": [
                    {"SEARCH_FIELD": "xdm.asset.realm", "SEARCH_TYPE": "WILDCARD", "SEARCH_VALUE": "account1"},
                    {"SEARCH_FIELD": "xdm.asset.realm", "SEARCH_TYPE": "WILDCARD", "SEARCH_VALUE": "account2"},
                    ...
                ]
            }]
        }

    Args:
        account_ids: List of cloud account IDs to include

    Returns:
        The membership predicate dictionary

    Raises:
        ValueError: If account_ids is empty
    """
    if not account_ids:
        raise ValueError("account_ids cannot be empty")

    # Build OR conditions - one per account
    or_conditions = [
        {
            "SEARCH_FIELD": "xdm.asset.realm",
            "SEARCH_TYPE": "WILDCARD",
            "SEARCH_VALUE": str(account_id)
        }
        for account_id in account_ids
    ]

    # Wrap in AND > OR structure (required by API)
    return {"AND": [{"OR": or_conditions}]}


def build_group_args(group_name: str, description: str, account_ids: list) -> dict:
    """
    Build the arguments shared by createAssetGroup and setAssetGroup.

    Args:
        group_name: Name of the asset group
        description: Description for the asset group
        account_ids: List of cloud account IDs for membership predicate

    Returns:
        The command arguments dictionary
    """
    return {
        "group_name": group_name,
        "group_type": GROUP_TYPE,
        "group_description": description,
        "membership_json": json.dumps(build_membership_predicate(account_ids))
    }


# =============================================================================
# COMMAND OPERATIONS
# =============================================================================

def get_existing_group_id(group_name: str, debug_info: list) -> str | None:
    """
    Check if an asset group with the given name already exists.

    The name is matched exactly on the results, in case getAssetGroup's
    names filter does partial matching.

    Args:
        group_name: The name of the asset group to search for
        debug_info: List that collects debug lines

    Returns:
        The ID of the matching asset group, or None if not found

    Raises:
        ValueError: If a group with this name exists but its ID can't be read
    """
    entries = run_command(CMD_GET_GROUP, {"names": group_name}, debug_info)

    for record in iter_records(entries_data(entries)):
        if get_field(record, GROUP_NAME_KEYS) != group_name:
            continue
        group_id = get_field(record, GROUP_ID_KEYS)
        if group_id is None:
            raise ValueError(
                f"Found group '{group_name}' but could not extract its ID. "
                f"Available fields: {list(record.keys())}"
            )
        return str(group_id)

    return None


def create_asset_group(group_name: str, description: str, account_ids: list,
                       debug_info: list) -> str | None:
    """
    Create a new dynamic asset group.

    Args:
        group_name: Name for the new asset group
        description: Description for the asset group
        account_ids: List of cloud account IDs to include
        debug_info: List that collects debug lines

    Returns:
        The new group ID, or None if it couldn't be determined
    """
    args = build_group_args(group_name, description, account_ids)
    entries = run_command(CMD_CREATE_GROUP, args, debug_info)

    for record in iter_records(entries_data(entries)):
        group_id = get_field(record, CREATED_ID_KEYS)
        if group_id is not None:
            return str(group_id)

    # The create result didn't carry an ID we recognize - look the group up instead
    debug_info.append("Group ID not found in create result, looking it up by name")
    return get_existing_group_id(group_name, debug_info)


def update_asset_group(group_id: str, group_name: str, description: str, account_ids: list,
                       debug_info: list) -> None:
    """
    Update an existing asset group.

    Args:
        group_id: ID of the asset group to update
        group_name: New name for the asset group
        description: New description for the asset group
        account_ids: New list of cloud account IDs to include
        debug_info: List that collects debug lines
    """
    args = {"group_id": group_id, **build_group_args(group_name, description, account_ids)}
    run_command(CMD_UPDATE_GROUP, args, debug_info)


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_dry_run_output(group_name: str, group_id: str, action: str, account_ids: list) -> str:
    """Format the human-readable output for dry run mode."""
    account_text = "\n".join(str(a) for a in account_ids)
    return (
        f"### 🔍 DRY RUN - No Changes Made\n\n"
        f"**Group Name:** `{group_name}`\n"
        f"**Group ID:** `{group_id}`\n"
        f"**Action:** {action}\n"
        f"**Accounts to Include:** {len(account_ids)}\n\n"
        f"### Account IDs\n\n```\n{account_text}\n```"
    )


def format_success_output(group_name: str, group_id: str, action: str, account_count: int) -> str:
    """Format the human-readable output for successful execution."""
    return (
        f"### ✅ Asset Group {action.capitalize()}\n\n"
        f"**Group Name:** `{group_name}`\n"
        f"**Group ID:** `{group_id}`\n"
        f"**Action:** {action}\n"
        f"**Accounts Included:** {account_count}\n"
    )


# =============================================================================
# MAIN COMMAND
# =============================================================================

def main():
    """
    Main entry point for the script.

    Parses arguments, checks for existing groups, and either creates
    a new asset group or updates an existing one. Supports dry-run
    mode for previewing changes.
    """
    try:
        args = TEST_ARGS if USE_TEST_ARGS else demisto.args()  # TEMPORARY - see TEST INPUTS

        # Parse and validate arguments
        group_name = args.get("group_name")
        account_ids = argToList(args.get("account_ids"))
        description = args.get("group_description") or DEFAULT_DESCRIPTION
        dry_run = argToBoolean(args.get("dry_run", "false"))
        debug_mode = argToBoolean(args.get("debug", "false"))

        if not group_name:
            raise ValueError("group_name is required")
        if not account_ids:
            raise ValueError("account_ids is required and cannot be empty")

        debug_info = []

        # Check if group already exists
        existing_id = get_existing_group_id(group_name, debug_info)
        is_update = existing_id is not None

        # Determine group_id and action
        if is_update:
            group_id = existing_id
            action = "would be updated" if dry_run else "updated"
        else:
            group_id = "(new)" if dry_run else None
            action = "would be created" if dry_run else "created"

        # Execute operation (unless dry run)
        if not dry_run:
            if is_update:
                update_asset_group(group_id, group_name, description, account_ids, debug_info)
            else:
                group_id = create_asset_group(group_name, description, account_ids, debug_info)

        # Build output
        output = {
            "group_id": group_id,
            "group_name": group_name,
            "action": action,
            "account_count": len(account_ids),
            "status": "dry_run" if dry_run else "success",
            "dry_run": dry_run
        }

        if dry_run:
            output["account_ids"] = account_ids
            readable = format_dry_run_output(group_name, group_id, action, account_ids)
        else:
            readable = format_success_output(group_name, group_id, action, len(account_ids))

        if debug_mode:
            readable += "\n\n### Debug Info\n\n```\n" + "\n".join(debug_info) + "\n```"

        # Return results
        return_results(CommandResults(
            outputs_prefix="CreateAssetGroup",
            outputs_key_field="group_id",
            outputs=output,
            readable_output=readable
        ))

    except Exception as ex:
        demisto.error(traceback.format_exc())
        return_error(f"CreateAssetGroup failed: {str(ex)}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ in ("__main__", "__builtin__", "builtins"):
    main()
