"""Mock Kingdee API responses for testing."""

import json

# Successful query response (list of lists - raw SDK format)
SUCCESS_RESPONSE_RAW = [
    ["MO0001", "AK2510034", "Workshop A", "P001", "Product A", "Spec A", 100, "Approved", "2025-01-15"],
]

# Empty response
EMPTY_RESPONSE = []

# Error response - query failed
ERROR_RESPONSE = {
    "Result": {
        "ResponseStatus": {
            "IsSuccess": False,
            "Errors": [{"Message": "Query failed: invalid field"}]
        }
    }
}

# Error response - form not found (MsgCode 4)
FORM_NOT_FOUND_RESPONSE = {
    "Result": {
        "MsgCode": 4,
        "ResponseStatus": {
            "IsSuccess": False,
            "Errors": [{"Message": "Business object does not exist"}]
        }
    }
}

# Error response - field not found
FIELD_NOT_FOUND_RESPONSE = {
    "Result": {
        "ResponseStatus": {
            "IsSuccess": False,
            "Errors": [{"Message": "Field does not exist"}]
        }
    }
}

# Nested error response (double wrapped - common for some errors)
NESTED_ERROR_RESPONSE = [[{
    "Result": {
        "ResponseStatus": {
            "IsSuccess": False,
            "Errors": [{"Message": "Field does not exist"}]
        }
    }
}]]

# JSON string response (SDK sometimes returns JSON as string)
SUCCESS_RESPONSE_JSON_STRING = json.dumps([
    ["MO0001", "AK2510034", "Workshop A", "P001", "Product A", "Spec A", 100, "Approved", "2025-01-15"],
])

# Multiple records response
MULTIPLE_RECORDS_RESPONSE = [
    ["MO0001", "AK2510034", "Workshop A", "P001", "Product A", "Spec A", 100, "Approved", "2025-01-15"],
    ["MO0002", "AK2510034", "Workshop B", "P002", "Product B", "Spec B", 50, "Approved", "2025-01-16"],
    ["MO0003", "AK2510035", "Workshop A", "P003", "Product C", "Spec C", 75, "Pending", "2025-01-17"],
]

# Aux property lookup response
AUX_PROPERTY_RESPONSE = [
    [1001, "Blue Model", ""],
    [1002, "", "Red"],
    [1003, "Green Special", "Green"],
]

# Pagination test responses
PAGE_1_RESPONSE = [["MO" + str(i).zfill(4), "AK001", 100] for i in range(2000)]  # Full page
PAGE_2_RESPONSE = [["MO" + str(2000 + i).zfill(4), "AK001", 100] for i in range(500)]  # Partial page


def create_success_response(data: list) -> list:
    """Create a successful SDK response."""
    return data


def create_error_response(message: str, msg_code: int = 0) -> dict:
    """Create an error SDK response."""
    return {
        "Result": {
            "MsgCode": msg_code,
            "ResponseStatus": {
                "IsSuccess": False,
                "Errors": [{"Message": message}]
            }
        }
    }
