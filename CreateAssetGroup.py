"""CreateAssetGroup - Cortex XSIAM/XSOAR Script

Creates or updates a dynamic asset group based on a list of realm IDs.
If an asset group with the same name exists, it will be updated;
otherwise, a new group will be created.

Arguments:
    group_name (str): Required. Name for the asset group.
    realm_list (list): Required. Comma-separated list of realm IDs.
    group_description (str): Optional. Description for the asset group.
    dry_run (bool): Optional. Preview changes without executing them.

Output:
    Context path: CreateAssetGroup
        - group_id: The asset group ID
        - group_name: The asset group name
        - action: created/updated/would be created/would be updated
        - realm_count: Number of realms included
        - status: success/dry_run
"""

import traceback
import json


# =============================================================================
# CONSTANTS
# =============================================================================

API_GET_GROUPS = "/public_api/v1/asset-groups"
API_CREATE_GROUP = "/public_api/v1/asset-groups/create"
API_UPDATE_GROUP = "/public_api/v1/asset-groups/update"

DEFAULT_DESCRIPTION = "Dynamic asset group created by automation script"
GROUP_TYPE = "Dynamic"
GROUP_ID_FIELD = "XDM.ASSET_GROUP.ID"


# =============================================================================
# API RESPONSE HANDLING
# =============================================================================

def parse_api_response(result: list, operation: str) -> dict:
    """
    Parse the response from a core-api-post command.
    
    Handles an unusual edge case where the API may return a 401 error entry
    followed by the actual valid response. This function iterates through
    all response entries and returns the first valid one.
    
    Args:
        result: The raw result from demisto.executeCommand()
        operation: Name of the operation (for error messages)
    
    Returns:
        The parsed response dictionary containing the 'reply' field
    
    Raises:
        DemistoException: If no valid response is found
    """
    if not result:
        raise DemistoException(f"{operation}: Empty response from API")
    
    # Iterate through entries to find a valid response
    # (API sometimes returns error entries before the actual data)
    for entry in result:
        if not isinstance(entry, dict):
            continue
        
        # Skip error entries (Type 4 = error)
        if entry.get("Type") == 4:
            continue
        
        # Extract response from Contents
        contents = entry.get("Contents", {})
        if not isinstance(contents, dict):
            continue
            
        response = contents.get("response", {})
        if response and "reply" in response:
            return response
    
    # No valid response found - raise error with details
    error_msg = get_error(result) if is_error(result) else "No valid response found"
    raise DemistoException(f"{operation}: {error_msg}")


# =============================================================================
# ASSET GROUP HELPERS
# =============================================================================

def extract_group_id(group_data: dict) -> str | None:
    """
    Extract the asset group ID from API response data.
    
    Args:
        group_data: Dictionary containing asset group fields
    
    Returns:
        The group ID as a string, or None if not found
    """
    value = group_data.get(GROUP_ID_FIELD)
    return str(value) if value is not None else None


def build_membership_predicate(realm_list: list) -> dict:
    """
    Build the membership predicate for dynamic asset group filtering.
    
    Creates a predicate structure that matches assets belonging to any
    of the specified realms using OR logic within an AND wrapper.
    
    Structure:
        {
            "AND": [{
                "OR": [
                    {"SEARCH_FIELD": "xdm.asset.realm", "SEARCH_TYPE": "WILDCARD", "SEARCH_VALUE": "realm1"},
                    {"SEARCH_FIELD": "xdm.asset.realm", "SEARCH_TYPE": "WILDCARD", "SEARCH_VALUE": "realm2"},
                    ...
                ]
            }]
        }
    
    Args:
        realm_list: List of realm IDs to include
    
    Returns:
        The membership predicate dictionary
    
    Raises:
        ValueError: If realm_list is empty
    """
    if not realm_list:
        raise ValueError("realm_list cannot be empty")
    
    # Build OR conditions - one per realm
    or_conditions = [
        {
            "SEARCH_FIELD": "xdm.asset.realm",
            "SEARCH_TYPE": "WILDCARD",
            "SEARCH_VALUE": str(realm)
        }
        for realm in realm_list
    ]
    
    # Wrap in AND > OR structure (required by API)
    return {"AND": [{"OR": or_conditions}]}


def build_group_payload(group_name: str, description: str, realm_list: list) -> dict:
    """
    Build the request payload for create/update asset group API calls.
    
    Args:
        group_name: Name of the asset group
        description: Description for the asset group
        realm_list: List of realm IDs for membership predicate
    
    Returns:
        The complete request payload dictionary
    """
    return {
        "request_data": {
            "asset_group": {
                "group_name": group_name,
                "group_type": GROUP_TYPE,
                "group_description": description,
                "membership_predicate": build_membership_predicate(realm_list)
            }
        }
    }


# =============================================================================
# API OPERATIONS
# =============================================================================

def get_existing_asset_group(group_name: str) -> dict | None:
    """
    Check if an asset group with the given name already exists.
    
    Args:
        group_name: The name of the asset group to search for
    
    Returns:
        The asset group data dictionary if found, None otherwise
    """
    payload = {
        "request_data": {
            "filters": {
                "AND": [{
                    "SEARCH_FIELD": "XDM.ASSET_GROUP.NAME",
                    "SEARCH_TYPE": "EQ",
                    "SEARCH_VALUE": group_name
                }]
            },
            "search_from": 0,
            "search_to": 100
        }
    }
    
    result = demisto.executeCommand("core-api-post", {
        "uri": API_GET_GROUPS,
        "body": json.dumps(payload)
    })
    
    response = parse_api_response(result, "Query asset groups")
    data = response.get("reply", {}).get("data", [])
    
    return data[0] if data else None


def create_asset_group(group_name: str, description: str, realm_list: list) -> dict:
    """
    Create a new dynamic asset group.
    
    Args:
        group_name: Name for the new asset group
        description: Description for the asset group
        realm_list: List of realm IDs to include
    
    Returns:
        The API response data containing the new group info
    """
    payload = build_group_payload(group_name, description, realm_list)
    
    result = demisto.executeCommand("core-api-post", {
        "uri": API_CREATE_GROUP,
        "body": json.dumps(payload)
    })
    
    response = parse_api_response(result, "Create asset group")
    return response.get("reply", {}).get("data", {})


def update_asset_group(group_id: str, group_name: str, description: str, realm_list: list) -> dict:
    """
    Update an existing asset group.
    
    Args:
        group_id: ID of the asset group to update
        group_name: New name for the asset group
        description: New description for the asset group
        realm_list: New list of realm IDs to include
    
    Returns:
        The API response data
    """
    payload = build_group_payload(group_name, description, realm_list)
    
    result = demisto.executeCommand("core-api-post", {
        "uri": f"{API_UPDATE_GROUP}/{group_id}",
        "body": json.dumps(payload)
    })
    
    response = parse_api_response(result, "Update asset group")
    return response.get("reply", {}).get("data", {})


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_dry_run_output(group_name: str, group_id: str, action: str, realm_list: list) -> str:
    """Format the human-readable output for dry run mode."""
    realm_text = "\n".join(str(r) for r in realm_list)
    return (
        f"### 🔍 DRY RUN - No Changes Made\n\n"
        f"**Group Name:** `{group_name}`\n"
        f"**Group ID:** `{group_id}`\n"
        f"**Action:** {action}\n"
        f"**Realms to Include:** {len(realm_list)}\n\n"
        f"### Realm List\n\n```\n{realm_text}\n```"
    )


def format_success_output(group_name: str, group_id: str, action: str, realm_count: int) -> str:
    """Format the human-readable output for successful execution."""
    return (
        f"### ✅ Asset Group {action.capitalize()}\n\n"
        f"**Group Name:** `{group_name}`\n"
        f"**Group ID:** `{group_id}`\n"
        f"**Action:** {action}\n"
        f"**Realms Included:** {realm_count}\n"
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
        args = demisto.args()
        
        # Parse and validate arguments
        group_name = args.get("group_name")
        realm_list = argToList(args.get("realm_list"))
        description = args.get("group_description") or DEFAULT_DESCRIPTION
        dry_run = argToBoolean(args.get("dry_run", "false"))
        
        if not group_name:
            raise ValueError("group_name is required")
        if not realm_list:
            raise ValueError("realm_list is required and cannot be empty")
        
        # Check if group already exists
        existing_group = get_existing_asset_group(group_name)
        is_update = existing_group is not None
        
        # Determine group_id and action
        if is_update:
            group_id = extract_group_id(existing_group)
            if not group_id:
                available_fields = list(existing_group.keys())
                raise ValueError(f"Could not extract group_id. Available fields: {available_fields}")
            action = "would be updated" if dry_run else "updated"
        else:
            group_id = "(new)" if dry_run else None
            action = "would be created" if dry_run else "created"
        
        # Execute operation (unless dry run)
        if not dry_run:
            if is_update:
                update_asset_group(group_id, group_name, description, realm_list)
            else:
                result = create_asset_group(group_name, description, realm_list)
                group_id = result.get("asset_group_id")
        
        # Build output
        output = {
            "group_id": group_id,
            "group_name": group_name,
            "action": action,
            "realm_count": len(realm_list),
            "status": "dry_run" if dry_run else "success",
            "dry_run": dry_run
        }
        
        if dry_run:
            output["realms"] = realm_list
            readable = format_dry_run_output(group_name, group_id, action, realm_list)
        else:
            readable = format_success_output(group_name, group_id, action, len(realm_list))
        
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
