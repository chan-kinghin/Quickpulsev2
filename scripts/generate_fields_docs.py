#!/usr/bin/env python3
"""
Generate FIELDS.md documentation files from discovered API field data
"""

import json
import os

# Mapping of form IDs to their Chinese names and entity keys
API_CONFIG = {
    "PRD_INSTOCK": {
        "name_cn": "生产入库单",
        "entity_key": "Entity",
        "json_file": "prd_instock_fields.json",
        "filter_field": "FMTONo"
    },
    "PRD_PPBOM": {
        "name_cn": "生产用料清单",
        "entity_key": "PPBomEntry",
        "json_file": "prd_ppbom_fields.json",
        "filter_field": "FMTONo"
    },
    "PRD_PickMtrl": {
        "name_cn": "生产领料单",
        "entity_key": "Entity",
        "json_file": "prd_pickmtrl_fields.json",
        "filter_field": "FMTONo"
    },
    "SUB_SUBREQORDER": {
        "name_cn": "委外申请订单",
        "entity_key": "TreeEntity",
        "json_file": "sub_subreqorder_fields.json",
        "filter_field": "FMTONo"
    },
    "SAL_SaleOrder": {
        "name_cn": "销售订单",
        "entity_key": "SaleOrderEntry",
        "json_file": "sal_saleorder_fields.json",
        "filter_field": "FMTONo"
    },
    "SAL_OUTSTOCK": {
        "name_cn": "销售出库单",
        "entity_key": "SAL_OUTSTOCKENTRY",
        "json_file": "sal_outstock_fields.json",
        "filter_field": "FMTONo"
    },
    "PUR_PurchaseOrder": {
        "name_cn": "采购订单",
        "entity_key": "POOrderEntry",
        "json_file": "pur_purchaseorder_fields.json",
        "filter_field": "FMTONo"
    },
    "STK_InStock": {
        "name_cn": "采购入库单",
        "entity_key": "InStockEntry",
        "json_file": "stk_instock_fields.json",
        "filter_field": "FMTONo"
    }
}

# Common Chinese translations for field names
FIELD_TRANSLATIONS = {
    "Id": "单据内码",
    "BillNo": "单据编号",
    "DocumentStatus": "单据状态",
    "Date": "日期",
    "CreateDate": "创建日期",
    "CreatorId": "创建人",
    "ApproverId": "审核人",
    "ApproveDate": "审核日期",
    "ModifierId": "修改人",
    "ModifyDate": "修改日期",
    "CancelDate": "作废日期",
    "Seq": "行号",
    "MaterialId": "物料",
    "UnitId": "单位",
    "StockId": "仓库",
    "StockLocId": "仓位",
    "Qty": "数量",
    "Price": "单价",
    "Amount": "金额",
    "TaxPrice": "含税单价",
    "TaxRate": "税率",
    "Note": "备注",
    "Lot": "批号",
    "MtoNo": "计划跟踪号",
    "FMTONo": "计划跟踪号",
    "ProduceDate": "生产日期",
    "ExpiryDate": "有效期至",
    "SaleOrgId": "销售组织",
    "StockOrgId": "库存组织",
    "PurchaseOrgId": "采购组织",
    "PrdOrgId": "生产组织",
    "SupplierId": "供应商",
    "CustomerId": "客户",
    "CustId": "客户",
    "CustomerID": "客户",
    "DeptId": "部门",
    "SaleDeptId": "销售部门",
    "SalerId": "销售员",
    "PurchaserId": "采购员",
    "WorkShopId": "车间",
    "BomId": "BOM版本",
    "Status": "状态",
    "OwnerIdHead": "货主(表头)",
    "OwnerId": "货主",
    "KeeperId": "保管者",
    "StockStatusId": "库存状态",
    "ExchangeRate": "汇率",
    "LocalCurrId": "本位币",
    "SettleCurrId": "结算币别",
    "BaseUnitId": "基本单位",
    "BaseUnitQty": "基本单位数量",
    "MustQty": "应收/应发数量",
    "RealQty": "实收/实发数量",
    "DeliveryDate": "交货日期",
    "MoEntryId": "生产订单分录内码",
    "MoBillNo": "生产订单编号",
    "POOrderEntryId": "采购订单分录内码",
    "SrcBillNo": "源单编号",
    "SrcBillType": "源单类型",
    "Remarks": "备注",
    "AuxPropId": "辅助属性"
}


def get_field_description(field_name):
    """Get Chinese description for a field name"""
    # Remove prefixes like F_ or trailing _Id
    clean_name = field_name
    if clean_name.startswith("F"):
        clean_name = clean_name[1:]
    if clean_name.endswith("_Id"):
        clean_name = clean_name[:-3]

    # Check direct mapping
    if field_name in FIELD_TRANSLATIONS:
        return FIELD_TRANSLATIONS[field_name]
    if clean_name in FIELD_TRANSLATIONS:
        return FIELD_TRANSLATIONS[clean_name]

    # Return the field name if no translation found
    return field_name


def format_sample_value(value):
    """Format sample value for display"""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        if len(value) > 50:
            return value[:47] + "..."
        return value if value else "-"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        # Try to get meaningful value from dict
        if "Number" in value:
            return value["Number"]
        if "Name" in value and isinstance(value["Name"], list):
            for name_item in value["Name"]:
                if isinstance(name_item, dict) and "Value" in name_item:
                    return name_item["Value"]
        return "(object)"
    if isinstance(value, list):
        return f"(list: {len(value)} items)"
    return str(value)


def extract_header_fields(data):
    """Extract header fields from document data"""
    fields = []

    for key, value in data.items():
        # Skip entity arrays and internal fields
        if isinstance(value, list):
            continue
        if key.endswith("_Id") and not key.startswith("F"):
            continue  # Skip _Id fields for linked entities
        if key == "FFormId":
            continue
        if key.startswith("_"):
            continue

        # Handle nested objects (like SaleOrgId containing Number/Name)
        if isinstance(value, dict):
            # Get the Number and Name from nested object
            sample_val = format_sample_value(value)
            fields.append({
                "key": key,
                "query_key": f"F{key}" if not key.startswith("F") else key,
                "description": get_field_description(key),
                "sample_value": sample_val
            })
        else:
            fields.append({
                "key": key,
                "query_key": f"F{key}" if not key.startswith("F") else key,
                "description": get_field_description(key),
                "sample_value": format_sample_value(value)
            })

    return fields


def extract_entity_fields(data, entity_key):
    """Extract fields from entity (detail) rows"""
    fields = []

    if entity_key not in data or not isinstance(data[entity_key], list):
        return fields

    entity_list = data[entity_key]
    if not entity_list or not isinstance(entity_list[0], dict):
        return fields

    sample_item = entity_list[0]

    for key, value in sample_item.items():
        if key.endswith("_Id") and not key.startswith("F"):
            continue  # Skip _Id fields
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            continue  # Skip sub-entities

        if isinstance(value, dict):
            sample_val = format_sample_value(value)
        else:
            sample_val = format_sample_value(value)

        # Query key format: FEntityKey_FFieldKey
        query_key = f"F{entity_key}_F{key}" if not key.startswith("F") else f"F{entity_key}_{key}"

        fields.append({
            "key": key,
            "query_key": query_key,
            "description": get_field_description(key),
            "sample_value": sample_val
        })

    return fields


def generate_fields_md(form_id, config, data):
    """Generate FIELDS.md content for an API"""
    name_cn = config["name_cn"]
    entity_key = config["entity_key"]

    header_fields = extract_header_fields(data)
    entity_fields = extract_entity_fields(data, entity_key)

    # Build the markdown content
    content = f"""# {name_cn} ({form_id}) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
"""

    for field in header_fields:
        content += f"| `{field['query_key']}` | {field['description']} | {field['sample_value']} |\n"

    content += f"""
## 二、明细行字段 ({entity_key})

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
"""

    for field in entity_fields:
        content += f"| `{field['query_key']}` | {field['description']} | {field['sample_value']} |\n"

    content += f"""
## 三、常用查询示例

```python
# 根据计划跟踪号查询{name_cn}
query_para = {{
    "FormId": "{form_id}",
    "FieldKeys": "FBillNo,FId,F{entity_key}_FMaterialId.FNumber,F{entity_key}_FMaterialId.FName,F{entity_key}_FQty",
    "FilterString": "F{entity_key}_FMTONo='AS251008'",
    "Limit": 100
}}
result = api_sdk.ExecuteBillQuery(query_para)
```

## 四、状态值说明

### 单据状态 (FDocumentStatus)

| 值 | 说明 |
|----|------|
| A | 创建 |
| B | 审核中 |
| C | 已审核 |
| Z | 暂存 |

## 五、API 使用说明

### 单据查询 (ExecuteBillQuery)
- 用于批量查询，返回二维数组
- 支持过滤、排序、分页
- 最大返回 10000 条

### 查看 (View)
- 用于查看单条记录完整详情
- 通过 `Number` 或 `Id` 定位
- 返回完整 JSON 数据包
"""

    return content


def main():
    field_data_dir = "field_data"
    output_dir = "."  # Same directory as other md files

    for form_id, config in API_CONFIG.items():
        json_file = config.get("json_file")

        if not json_file:
            print(f"Skipping {form_id} - no data available")
            continue

        json_path = os.path.join(field_data_dir, json_file)

        if not os.path.exists(json_path):
            print(f"Skipping {form_id} - JSON file not found: {json_path}")
            continue

        print(f"Generating {form_id}_FIELDS.md...")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        content = generate_fields_md(form_id, config, data)

        output_path = os.path.join(output_dir, f"{form_id}_FIELDS.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  Saved to: {output_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
