"""GetCloudAccounts - Cortex XSIAM/XSOAR Script

Retrieves cloud account IDs filtered by account name using Cloud Onboarding APIs.
Works with any cloud provider (AWS, Azure, GCP) based on the integration instance.

Arguments:
    instance_ids (array): Required. One or more cloud integration instance IDs.
        Mark as "Is array" in script configuration to accept multiple values.
    filter_keyword (str): Optional. Filter expression with optional flag prefix.
        - No flag: Simple contains match (e.g., "SOC")
        - -r: Regex pattern (e.g., "-r ^AWS-SOC.*")
        - -or: Match ANY keyword (e.g., "-or SOC, PROD, DEV")
        - -and: Match ALL keywords (e.g., "-and SOC, Production")
    case_sensitive (bool): Optional. Default: false.
    debug (bool): Optional. Show debug info in output. Default: false.

Output:
    Context path: GetCloudAccounts.values (list of cloud_account_id)
    Context path: GetCloudAccounts.account_names (list of account_name)
    Context path: GetCloudAccounts.instance_ids (list of instance IDs queried)
"""

import json
import re
import traceback


# ============================================================================
# CONSTANTS - Modify these to customize the script behavior
# ============================================================================

PAGE_SIZE = 100


# ============================================================================
# FUNCTIONS
# ============================================================================

def get_accounts_for_instance(instance_id: str, debug_info: list = None) -> list:
    """Fetch all accounts for a specific integration instance with pagination."""

    all_accounts = []
    offset = 0

    if debug_info is not None:
        debug_info.append(f"API Request URI: /public_api/v1/cloud_onboarding/get_accounts")

    while True:
        payload = {
            "request_data": {
                "instance_id": instance_id,
                "filter_data": {
                    "paging": {
                        "from": offset,
                        "to": offset + PAGE_SIZE
                    }
                }
            }
        }

        if debug_info is not None:
            debug_info.append(f"Fetching accounts {offset} to {offset + PAGE_SIZE}")

        results = demisto.executeCommand('core-api-post', {
            'uri': '/public_api/v1/cloud_onboarding/get_accounts',
            'body': json.dumps(payload)
        })

        if is_error(results):
            raise DemistoException(f"Failed to get accounts for instance {instance_id}: {get_error(results)}")

        contents = results[0].get('Contents', {})
        # Handle both direct reply and nested response.reply structures
        if 'response' in contents:
            response = contents.get('response', {}).get('reply', {})
        else:
            response = contents.get('reply', {})

        accounts = response.get('DATA', [])
        total_count = response.get('TOTAL_COUNT', 0)

        if debug_info is not None and offset == 0:
            debug_info.append(f"Total accounts in instance: {total_count}")

        all_accounts.extend(accounts)

        # Check if we've fetched all accounts
        if len(accounts) < PAGE_SIZE or len(all_accounts) >= total_count:
            break

        offset += PAGE_SIZE

    if debug_info is not None:
        debug_info.append(f"Pagination complete: fetched {len(all_accounts)} accounts in {(offset // PAGE_SIZE) + 1} page(s)")

    return all_accounts


def parse_filter(filter_arg: str) -> tuple:
    """Parse filter argument into (filter_type, filter_value).

    Returns:
        tuple: (filter_type, filter_value) where filter_type is one of:
            - None: No filter
            - "simple": Simple contains match
            - "regex": Regex pattern
            - "or": List of keywords (match any)
            - "and": List of keywords (match all)
    """
    if not filter_arg:
        return (None, None)

    filter_arg = filter_arg.strip()

    if filter_arg.startswith('-r '):
        pattern = filter_arg[3:].strip()
        if not pattern:
            raise ValueError("Filter flag -r requires a pattern")
        return ("regex", pattern)

    if filter_arg.startswith('-or '):
        keywords_str = filter_arg[4:].strip()
        if not keywords_str:
            raise ValueError("Filter flag -or requires keywords")
        keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
        if not keywords:
            raise ValueError("Filter flag -or requires at least one keyword")
        return ("or", keywords)

    if filter_arg.startswith('-and '):
        keywords_str = filter_arg[5:].strip()
        if not keywords_str:
            raise ValueError("Filter flag -and requires keywords")
        keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
        if not keywords:
            raise ValueError("Filter flag -and requires at least one keyword")
        return ("and", keywords)

    if filter_arg.startswith('-'):
        flag = filter_arg.split()[0]
        raise ValueError(f"Unknown filter flag: {flag}. Use -r, -or, or -and")

    return ("simple", filter_arg)


def filter_accounts_by_name(accounts: list, filter_type: str, filter_value, case_sensitive: bool = False) -> list:
    """Filter accounts by account_name field based on filter type.

    Args:
        accounts: List of account dictionaries
        filter_type: One of None, "simple", "regex", "or", "and"
        filter_value: The filter value (string or list depending on type)
        case_sensitive: Whether to use case-sensitive matching
    """
    if filter_type is None:
        return accounts

    def get_name(acc):
        name = acc.get('account_name', '')
        return name if case_sensitive else name.lower()

    def normalize(val):
        return val if case_sensitive else val.lower()

    if filter_type == "simple":
        keyword = normalize(filter_value)
        return [acc for acc in accounts if keyword in get_name(acc)]

    if filter_type == "regex":
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(filter_value, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        return [acc for acc in accounts if pattern.search(acc.get('account_name', ''))]

    if filter_type == "or":
        keywords = [normalize(kw) for kw in filter_value]
        return [acc for acc in accounts if any(kw in get_name(acc) for kw in keywords)]

    if filter_type == "and":
        keywords = [normalize(kw) for kw in filter_value]
        return [acc for acc in accounts if all(kw in get_name(acc) for kw in keywords)]

    return accounts


def extract_account_ids(accounts: list) -> list:
    """Extract cloud_account_id from account list."""
    return [
        acc.get('cloud_account_id')
        for acc in accounts
        if acc.get('cloud_account_id')
    ]


def extract_account_names(accounts: list) -> list:
    """Extract account_name from account list."""
    return [
        acc.get('account_name')
        for acc in accounts
        if acc.get('account_name')
    ]


def build_output(instance_ids: list, filter_keyword: str, case_sensitive: bool,
                 results_count: int, account_ids: list, account_names: list,
                 debug_mode: bool = False) -> str:
    """Build human-readable output for War Room."""

    case_mode = "case-sensitive" if case_sensitive else "case-insensitive"
    filter_display = f"`{filter_keyword}` ({case_mode})" if filter_keyword else "(none - returning all)"

    instance_display = ", ".join(f"`{iid}`" for iid in instance_ids)

    output = (
        f"**Instance IDs:** {instance_display}\n"
        f"**Filter:** {filter_display}\n"
        f"**Results:** {results_count}\n"
    )

    if debug_mode and account_names:
        output += "\n### Account Names\n\n```\n"
        output += "\n".join(str(v) for v in account_names)
        output += "\n```\n\n"

        output += "### Account IDs\n\n```\n"
        output += "\n".join(str(v) for v in account_ids)
        output += "\n```"

    return output


def main():
    """Main entry point."""
    try:
        # Get arguments
        args = demisto.args()
        instance_ids_arg = args.get('instance_ids')
        filter_keyword = args.get('filter_keyword')
        case_sensitive = argToBoolean(args.get('case_sensitive', 'false'))
        debug_mode = argToBoolean(args.get('debug', 'false'))

        # Handle array argument - argToList handles both single value and list
        instance_ids = argToList(instance_ids_arg)

        debug_info = []
        debug_info.append(f"Arguments - instance_ids: {instance_ids}, filter_keyword: {filter_keyword}, case_sensitive: {case_sensitive}")

        if not instance_ids:
            return_error("instance_ids is required")
            return

        # Parse filter expression
        filter_type, filter_value = parse_filter(filter_keyword)
        debug_info.append(f"Parsed filter - type: {filter_type}, value: {filter_value}")

        # Fetch accounts from all instances
        all_accounts = []
        for instance_id in instance_ids:
            debug_info.append(f"--- Fetching from instance: {instance_id} ---")
            try:
                accounts = get_accounts_for_instance(instance_id, debug_info if debug_mode else None)
                debug_info.append(f"Instance {instance_id}: fetched {len(accounts)} accounts")
                all_accounts.extend(accounts)
            except Exception as ex:
                debug_info.append(f"Instance {instance_id}: ERROR - {str(ex)}")
                demisto.debug(f"Error fetching accounts for instance {instance_id}: {ex}")

        debug_info.append(f"Total accounts from all instances: {len(all_accounts)}")
        if all_accounts:
            debug_info.append(f"Sample account keys: {list(all_accounts[0].keys())}")
            debug_info.append(f"First account: {all_accounts[0]}")

        # Filter accounts
        filtered_accounts = filter_accounts_by_name(all_accounts, filter_type, filter_value, case_sensitive)
        debug_info.append(f"After filtering: {len(filtered_accounts)} accounts")

        # Extract account IDs and names
        account_ids = extract_account_ids(filtered_accounts)
        account_names = extract_account_names(filtered_accounts)
        debug_info.append(f"Extracted {len(account_ids)} account IDs and {len(account_names)} account names")

        # Build readable output
        output = build_output(instance_ids, filter_keyword, case_sensitive,
                              len(account_ids), account_ids, account_names, debug_mode)

        # Append debug info if debug mode is enabled
        if debug_mode:
            output += "\n\n### Debug Info\n\n```\n"
            output += "\n".join(debug_info)
            output += "\n```"

        # Build and return results
        return_results(CommandResults(
            outputs_prefix='GetCloudAccounts',
            outputs_key_field='instance_ids',
            outputs={
                'instance_ids': instance_ids,
                'filter_keyword': filter_keyword,
                'case_sensitive': case_sensitive,
                'results_count': len(account_ids),
                'values': account_ids,
                'account_names': account_names
            },
            readable_output=output
        ))

    except Exception as ex:
        demisto.error(traceback.format_exc())
        return_error(f'GetCloudAccounts failed: {str(ex)}')


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()
