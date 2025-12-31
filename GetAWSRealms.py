"""GetAWSRealms - Cortex XSIAM/XSOAR Script

Retrieves AWS account realm IDs filtered by account name keyword.

Arguments:
    filter_keyword (str): Keyword to filter account names. Defaults to 'SOC'.

Output:
    Context path: GetAWSRealms.values (list of AWS realm IDs)
"""

import time
import traceback


# ============================================================================
# CONSTANTS - Modify these to customize the script behavior
# ============================================================================

QUERY_NAME = 'XQLQuery'
TIMEOUT = 120  # Max seconds to wait for query results
POLL_INTERVAL = 10  # Seconds between status checks
DEFAULT_FILTER_KEYWORD = 'SOC'
OUTPUT_FIELD = 'xdm.asset.realm'

XQL_QUERY = '''dataset = asset_inventory 
| filter xdm.asset.type.category = "Account" 
| filter xdm.asset.provider contains "AWS" 
| alter account_name = json_extract_scalar(xdm.asset.raw_fields,"$.Platform Discovery.Name") 
| filter account_name != null 
| dedup xdm.asset.realm 
| filter account_name contains "{filter_keyword}" 
| fields account_name,xdm.asset.realm'''


# ============================================================================
# FUNCTIONS
# ============================================================================

def execute_xql_query(query: str) -> dict:
    """Execute XQL query and poll until results are ready."""
    
    results = demisto.executeCommand('xdr-xql-generic-query', {
        'query': query,
        'query_name': QUERY_NAME
    })

    if is_error(results):
        raise DemistoException(f"XQL query failed: {get_error(results)}")

    contents = results[0].get('Contents', {})
    status = contents.get('status', '')
    execution_id = contents.get('execution_id', '')
    data = contents.get('results')

    # Poll if query is still pending
    start_time = time.time()
    while status == 'PENDING' and (time.time() - start_time) < TIMEOUT:
        time.sleep(POLL_INTERVAL)
        
        poll_results = demisto.executeCommand('xdr-xql-get-query-results', {
            'query_id': execution_id
        })
        
        if not is_error(poll_results):
            contents = poll_results[0].get('Contents', {})
            status = contents.get('status', '')
            data = contents.get('results')
            if status != 'PENDING':
                break

    return {
        'execution_id': execution_id,
        'status': status,
        'results': data or []
    }


def extract_field_values(results: list, field: str) -> list:
    """Extract specific field values from query results."""
    return [item.get(field) for item in results if isinstance(item, dict) and field in item]


def build_output(filter_keyword: str, query_result: dict, extracted_values: list) -> str:
    """Build human-readable output for War Room."""
    status = query_result.get('status')
    results_count = len(query_result.get('results', []))
    
    output = (
        f"**Filter Keyword:** `{filter_keyword}`\n"
        f"**Status:** `{status}`\n"
        f"**Results Count:** {results_count}\n"
        f"**Extracted Values:** {len(extracted_values)}\n\n"
    )
    
    if status == 'SUCCESS' and extracted_values:
        output += f"### {OUTPUT_FIELD}\n\n```\n"
        output += "\n".join(str(v) for v in extracted_values)
        output += "\n```"
    elif status == 'SUCCESS':
        output += "### No results found."
    elif status == 'PENDING':
        output += "### Query timed out. Try again or check in Cortex directly."
    else:
        output += f"### Query ended with status: {status}"
    
    return output


def main():
    """Main entry point."""
    try:
        # Get filter keyword from arguments
        args = demisto.args()
        filter_keyword = args.get('filter_keyword') or DEFAULT_FILTER_KEYWORD
        
        # Build and execute query
        query = XQL_QUERY.replace('{filter_keyword}', filter_keyword)
        query_result = execute_xql_query(query)
        
        # Extract the specific field values
        extracted_values = extract_field_values(query_result.get('results', []), OUTPUT_FIELD)
        
        # Build and return results
        return_results(CommandResults(
            outputs_prefix='GetAWSRealms',
            outputs_key_field='execution_id',
            outputs={
                'execution_id': query_result.get('execution_id'),
                'status': query_result.get('status'),
                'filter_keyword': filter_keyword,
                'results_count': len(extracted_values),
                'values': extracted_values
            },
            readable_output=build_output(filter_keyword, query_result, extracted_values)
        ))
        
    except Exception as ex:
        demisto.error(traceback.format_exc())
        return_error(f'XQL Query Script failed: {str(ex)}')


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()
