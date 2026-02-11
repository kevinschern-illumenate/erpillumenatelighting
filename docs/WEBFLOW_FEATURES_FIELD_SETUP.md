# Webflow CMS - Features Field Setup Guide

## Overview

The **Features** field was added to the ilL-Webflow-Product doctype to store key product features and selling points. This guide explains how to create the corresponding field in Webflow CMS to receive this data during the n8n product sync.

---

## Webflow CMS Field Configuration

### Field Details

| Property | Value |
|----------|-------|
| **Field Name** | Features |
| **Slug** | `features` |
| **Field Type** | **Plain Text** |
| **Required** | No (optional) |
| **Help Text** | Key product features and selling points |

### Step-by-Step Instructions

1. **Open Webflow CMS Settings**
   - Navigate to your Webflow project
   - Go to CMS Collections
   - Select the **Products** collection (ID: `696fc3c5c42c86528e97f413`)

2. **Add New Field**
   - Click "+ Add New Field"
   - Select **Plain Text** as the field type

3. **Configure Field Settings**
   - **Field Name**: Enter "Features"
   - **Slug**: Confirm it's set to `features` (auto-generated from name)
   - **Help Text**: "Key product features and selling points"
   - **Required**: Leave unchecked (field is optional)

4. **Save Changes**
   - Click "Save" to add the field to the Products collection

---

## Field Mapping Details

### From ERPNext to Webflow

The n8n workflow maps the field as follows:

```javascript
// In Transform to Webflow Format node
fieldData['features'] = product.features || '';
```

### Data Flow

```
ERPNext ilL-Webflow-Product
  └─> features (Small Text field)
       └─> n8n Workflow Transform
            └─> Webflow Products Collection
                 └─> features (Plain Text field)
```

---

## Field Characteristics

### ERPNext Side
- **Field Type**: Small Text (multi-line text input)
- **Location**: Marketing Content section
- **Position**: Between "Short Description" and "Long Description"
- **Description**: "Key product features and selling points"

### Webflow Side
- **Field Type**: Plain Text (multi-line text display)
- **Default Value**: Empty string if not set in ERPNext
- **Max Length**: Unlimited (Plain Text field supports long content)

---

## Usage Example

### In ERPNext
A user might enter features like:
```
• Energy-efficient LED technology
• Customizable length options
• Multiple mounting configurations
• IP67 rated for wet locations
• 5-year warranty
```

### In Webflow
This data will sync to the `features` field and can be displayed on product pages using:
```html
<div class="product-features">
  <div w-dyn="features"></div>
</div>
```

Or with Rich Text element bound to the `features` field for automatic formatting.

---

## Important Notes

1. **Field Type**: Must be **Plain Text** (not Rich Text) because the ERPNext source is Small Text, which doesn't contain HTML formatting.

2. **Line Breaks**: Multi-line text from ERPNext will be preserved in Webflow. Use CSS `white-space: pre-line` or `pre-wrap` if you want to display line breaks.

3. **Optional Field**: The field can be empty. The n8n workflow defaults to an empty string ('') if no features are specified.

4. **Sync Frequency**: Features data syncs with the main product sync workflow (every 6 hours by default).

---

## Verification

After creating the field in Webflow:

1. Trigger a product sync from n8n (or wait for the next scheduled sync)
2. Check a product in Webflow CMS that has features defined in ERPNext
3. Confirm the features text appears in the `features` field

---

## Related Documentation

- [Webflow Integration Guide](./WEBFLOW_INTEGRATION_GUIDE.md)
- [n8n Product Sync Workflow](../n8n_workflows/webflow_product_sync.json)
- [ERPNext DocType Definition](../illumenate_lighting/illumenate_lighting/doctype/ill_webflow_product/ill_webflow_product.json)

---

## Troubleshooting

### Features not syncing to Webflow

**Check:**
1. Field slug in Webflow is exactly `features` (lowercase, no spaces)
2. Field type is Plain Text
3. Product has features text in ERPNext
4. n8n workflow has run successfully (check workflow logs)
5. Product sync status in ERPNext shows "Synced"

### Features text appears without line breaks

**Solution:**
Apply CSS to preserve line breaks:
```css
.product-features {
  white-space: pre-line;
}
```

### Empty features field in Webflow

This is expected behavior if:
- The product doesn't have features defined in ERPNext
- The field was just added and hasn't synced yet
- The product sync failed (check n8n logs)
