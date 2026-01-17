#!/usr/bin/env python3
"""
Explore all Kingdee K3Cloud API fields for documentation
Queries each API to discover all available fields using View API
"""

import json
import os
from k3cloud_webapi_sdk.main import K3CloudApiSdk


# Configuration for all APIs to explore
APIS_CONFIG = [
    {
        "form_id": "PRD_INSTOCK",
        "name_cn": "生产入库单",
        "filter_field": "FMTONo",
        "output_file": "prd_instock_fields.json"
    },
    {
        "form_id": "PRD_PPBOM",
        "name_cn": "生产用料清单",
        "filter_field": "FMTONo",
        "output_file": "prd_ppbom_fields.json"
    },
    {
        "form_id": "PRD_PickMtrl",
        "name_cn": "生产领料单",
        "filter_field": "FMTONo",
        "output_file": "prd_pickmtrl_fields.json"
    },
    {
        "form_id": "SUB_POORDER",
        "name_cn": "委外订单",
        "filter_field": "FMTONo",
        "output_file": "sub_poorder_fields.json"
    },
    {
        "form_id": "SAL_SaleOrder",
        "name_cn": "销售订单",
        "filter_field": "FMTONo",
        "output_file": "sal_saleorder_fields.json"
    },
    {
        "form_id": "SAL_OUTSTOCK",
        "name_cn": "销售出库单",
        "filter_field": "FMTONo",
        "output_file": "sal_outstock_fields.json"
    },
    {
        "form_id": "PUR_PurchaseOrder",
        "name_cn": "采购订单",
        "filter_field": "FMTONo",
        "output_file": "pur_purchaseorder_fields.json"
    },
    {
        "form_id": "STK_InStock",
        "name_cn": "采购入库单",
        "filter_field": "FMTONo",
        "output_file": "stk_instock_fields.json"
    }
]

# Sample MTO numbers to try
MTO_NUMBERS = ["AS251008", "AS2511012", "AK2412023"]


def extract_fields(data, prefix="", results=None):
    """Recursively extract all field keys and sample values from JSON data"""
    if results is None:
        results = {"header_fields": {}, "entity_fields": {}}

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            # Skip internal fields
            if key.startswith("F") or key.startswith("_"):
                if isinstance(value, (dict, list)):
                    # Check if this is an entity (list of records)
                    if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                        results["entity_fields"][key] = {"fields": {}, "sample_count": len(value)}
                        # Extract fields from first item
                        extract_entity_fields(value[0], key, results["entity_fields"][key]["fields"])
                    else:
                        extract_fields(value, full_key, results)
                else:
                    # This is a header field
                    results["header_fields"][key] = {
                        "sample_value": value,
                        "type": type(value).__name__
                    }

    return results


def extract_entity_fields(data, entity_name, fields_dict):
    """Extract fields from an entity item"""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                if isinstance(value, dict):
                    # Nested object - flatten
                    for sub_key, sub_value in value.items():
                        if not isinstance(sub_value, (dict, list)):
                            fields_dict[f"{key}.{sub_key}"] = {
                                "sample_value": sub_value,
                                "type": type(sub_value).__name__
                            }
            else:
                fields_dict[key] = {
                    "sample_value": value,
                    "type": type(value).__name__
                }


def explore_api(api_sdk, config):
    """Explore a single API and extract its fields"""
    form_id = config["form_id"]
    name_cn = config["name_cn"]
    output_file = config["output_file"]

    print(f"\n{'='*60}")
    print(f"Exploring: {name_cn} ({form_id})")
    print(f"{'='*60}")

    # Step 1: Query to get sample document IDs
    print(f"Step 1: Querying {form_id} for sample documents...")

    query_para = {
        "FormId": form_id,
        "FieldKeys": "FBillNo,FId",
        "FilterString": [],
        "OrderString": "",
        "TopRowCount": 0,
        "StartRow": 0,
        "Limit": 10,
        "SubSystemId": ""
    }

    try:
        query_response = api_sdk.ExecuteBillQuery(query_para)
        query_result = json.loads(query_response)

        if not query_result:
            print(f"  No documents found for {form_id}")
            return None

        print(f"  Found {len(query_result)} documents")
        for item in query_result[:5]:
            print(f"    - BillNo: {item[0]}, ID: {item[1]}")

        # Use the first document
        bill_number = query_result[0][0]

    except Exception as e:
        print(f"  Query error: {e}")
        return None

    # Step 2: Use View API to get complete document structure
    print(f"\nStep 2: Viewing document {bill_number}...")

    view_para = {
        "CreateOrgId": 0,
        "Number": bill_number,
        "Id": "",
        "IsSortBySeq": "false"
    }

    try:
        response = api_sdk.View(form_id, view_para)
        res = json.loads(response)

        if "Result" not in res:
            print(f"  Error: Unexpected response format")
            return None

        result = res["Result"]

        if "ResponseStatus" in result:
            status = result["ResponseStatus"]
            if not status.get("IsSuccess", False):
                print(f"  View failed: {status}")
                return None

        bill_data = result.get("Result", {})

        if not bill_data:
            print(f"  Warning: Empty document data")
            return None

        # Save raw JSON for reference
        output_path = os.path.join("field_data", output_file)
        os.makedirs("field_data", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(bill_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved raw data to: {output_path}")

        # Extract and categorize fields
        print(f"\nStep 3: Extracting fields...")
        fields_info = analyze_document_structure(bill_data)

        # Save field analysis
        analysis_path = os.path.join("field_data", f"{form_id}_analysis.json")
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(fields_info, f, indent=2, ensure_ascii=False)
        print(f"  Saved field analysis to: {analysis_path}")

        return fields_info

    except Exception as e:
        print(f"  View error: {e}")
        import traceback
        traceback.print_exc()
        return None


def analyze_document_structure(data, path=""):
    """Analyze document structure and categorize fields"""
    result = {
        "header_fields": [],
        "entities": {}
    }

    if not isinstance(data, dict):
        return result

    for key, value in data.items():
        # Skip non-field keys
        if not key.startswith("F") and key not in ["Id", "BillNo"]:
            continue

        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            # This is an entity (detail rows)
            entity_fields = []
            sample_item = value[0]

            for field_key, field_value in sample_item.items():
                if isinstance(field_value, dict):
                    # Nested object (like FMaterialId with subfields)
                    for sub_key, sub_value in field_value.items():
                        if not isinstance(sub_value, (dict, list)):
                            entity_fields.append({
                                "key": f"{field_key}.{sub_key}",
                                "query_key": f"{key}_{field_key}_{sub_key}",
                                "sample_value": sub_value,
                                "type": type(sub_value).__name__
                            })
                elif not isinstance(field_value, list):
                    entity_fields.append({
                        "key": field_key,
                        "query_key": f"{key}_{field_key}",
                        "sample_value": field_value,
                        "type": type(field_value).__name__
                    })

            result["entities"][key] = {
                "count": len(value),
                "fields": entity_fields
            }

        elif isinstance(value, dict):
            # Nested header object (like FPrdOrgId with subfields)
            for sub_key, sub_value in value.items():
                if not isinstance(sub_value, (dict, list)):
                    result["header_fields"].append({
                        "key": f"{key}.{sub_key}",
                        "sample_value": sub_value,
                        "type": type(sub_value).__name__
                    })
        else:
            # Simple header field
            result["header_fields"].append({
                "key": key,
                "sample_value": value,
                "type": type(value).__name__
            })

    return result


def main():
    # Initialize SDK
    print("Initializing Kingdee K3Cloud SDK...")
    api_sdk = K3CloudApiSdk("http://flt.hotker.com:8200/k3cloud/")
    api_sdk.Init(config_path='conf.ini', config_node='config')

    # Explore each API
    results = {}
    for config in APIS_CONFIG:
        result = explore_api(api_sdk, config)
        if result:
            results[config["form_id"]] = {
                "name_cn": config["name_cn"],
                "fields": result
            }

    # Save summary
    summary_path = os.path.join("field_data", "all_apis_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n\nSummary saved to: {summary_path}")

    # Print summary
    print("\n" + "="*60)
    print("EXPLORATION SUMMARY")
    print("="*60)
    for form_id, data in results.items():
        name_cn = data["name_cn"]
        fields = data["fields"]
        header_count = len(fields.get("header_fields", []))
        entity_count = len(fields.get("entities", {}))
        print(f"\n{name_cn} ({form_id}):")
        print(f"  Header fields: {header_count}")
        print(f"  Entities: {entity_count}")
        for entity_name, entity_data in fields.get("entities", {}).items():
            print(f"    - {entity_name}: {len(entity_data.get('fields', []))} fields")


if __name__ == "__main__":
    main()
