# Webflow Integration API Documentation

## Overview

The Webflow Integration API provides endpoints for integrating ERPNext product data with Webflow CMS. It implements a hybrid sync approach where the base catalog syncs every 6 hours via n8n, while real-time stock and pricing data is fetched client-side via JavaScript.

## API Endpoints

### 1. Get Product Detail (Public)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_product_detail`

**Method:** GET/POST

**Authentication:** None required (allow_guest=True)

**Description:** Returns comprehensive product details including custom attributes, technical specs, real-time pricing, and stock information.

**Parameters:**
- `item_code` (optional): Item code (primary key)
- `sku` (optional): SKU/Item name (alternate lookup)

**Note:** At least one parameter (item_code or sku) is required.

**Example Request:**
```bash
curl -X GET "https://your-domain.com/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_product_detail?item_code=TEST-ITEM-001"
```

**Response Format:**
```json
{
  "success": true,
  "product": {
    "item_code": "TEST-ITEM-001",
    "item_name": "Test Product",
    "description": "Product description",
    "item_group": "Products",
    "stock_uom": "Nos",
    "weight_per_unit": 1.5,
    "weight_uom": "kg",
    "image": "/files/product-image.jpg",
    "is_sales_item": 1,
    "is_stock_item": 1,
    "price": 99.99,
    "currency": "USD",
    "stock_qty": 100,
    "in_stock": true,
    "is_configured_fixture": true,
    "custom_attributes": {
      "finish": {
        "code": "BK",
        "name": "Black",
        "surface_treatment": "Powder Coat"
      },
      "lens": {
        "name": "Clear",
        "code": "CLR",
        "transmission_percent": 90
      },
      "cct": {
        "name": "3000K",
        "code": "30",
        "kelvin": 3000,
        "display": "3000K"
      },
      "output_level": {
        "name": "High Output",
        "code": "HO",
        "value_lm_per_ft": 600
      },
      "cri": {
        "name": "CRI 90+",
        "code": "90",
        "ra_value": 90
      },
      "led_package": {
        "name": "2835",
        "code": "2835"
      },
      "mounting_method": {
        "name": "Surface Mount",
        "code": "SM"
      },
      "environment_rating": {
        "name": "Dry Location",
        "code": "DRY",
        "ip_rating": "IP20"
      },
      "power_feed_type": {
        "name": "Wire Lead",
        "code": "WL"
      },
      "drivers": [
        {
          "item": "DRIVER-001",
          "qty": 1,
          "input_voltage": "120-277VAC",
          "max_wattage": 96,
          "output_voltage": "24VDC",
          "dimming_protocol": "0-10V"
        }
      ]
    },
    "technical_specs": {
      "estimated_delivered_output": {
        "value": 540.0,
        "unit": "lm/ft",
        "display": "540.0 lm/ft"
      },
      "total_watts": {
        "value": 48.5,
        "display": "48.5W"
      },
      "length": {
        "mm": 1219,
        "inches": 48.0,
        "display": "1219mm (48.0\")"
      },
      "input_voltage": {
        "value": "120-277VAC",
        "display": "120-277VAC"
      }
    },
    "msrp_unit": 199.99,
    "tier_unit": 149.99
  },
  "cached_at": "2026-01-20T12:40:42.994Z"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Product not found: TEST-ITEM-001",
  "product": null
}
```

---

### 2. Get Related Products (Public)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_related_products`

**Method:** GET/POST

**Authentication:** None required (allow_guest=True)

**Description:** Returns related products in the same item group.

**Parameters:**
- `item_code` (required): Item code of the reference product
- `limit` (optional): Maximum number of results (default: 6)

**Example Request:**
```bash
curl -X GET "https://your-domain.com/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_related_products?item_code=TEST-ITEM-001&limit=6"
```

**Response Format:**
```json
{
  "success": true,
  "products": [
    {
      "item_code": "RELATED-ITEM-001",
      "item_name": "Related Product 1",
      "image": "/files/related-product-1.jpg",
      "price": 89.99
    },
    {
      "item_code": "RELATED-ITEM-002",
      "item_name": "Related Product 2",
      "image": "/files/related-product-2.jpg",
      "price": 79.99
    }
  ]
}
```

---

### 3. Get Active Products for Webflow (Authenticated)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_active_products_for_webflow`

**Method:** GET/POST

**Authentication:** Required (API Key or Session)

**Description:** Returns all active, sellable products for Webflow sync. Used by n8n for periodic catalog sync.

**Parameters:**
- `item_group` (optional): Filter by item group
- `modified_since` (optional): ISO datetime string to get only updated products

**Example Request:**
```bash
curl -X GET \
  "https://your-domain.com/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_active_products_for_webflow?item_group=Products&modified_since=2026-01-01T00:00:00" \
  -H "Authorization: token YOUR_API_KEY:YOUR_API_SECRET"
```

**Response Format:**
```json
{
  "success": true,
  "products": [
    {
      "item_code": "ITEM-001",
      "item_name": "Product 1",
      "description": "Product description",
      "item_group": "Products",
      "stock_uom": "Nos",
      "image": "/files/product-1.jpg",
      "price": 99.99,
      "currency": "USD",
      "stock_qty": 100,
      "in_stock": true,
      "modified": "2026-01-20T12:40:42.994Z"
    }
  ],
  "count": 1
}
```

---

### 4. Get Products by Codes (Authenticated)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_products_by_codes`

**Method:** POST

**Authentication:** Required (API Key or Session)

**Description:** Bulk fetch products by list of item codes. Used by n8n for batch processing.

**Parameters:**
- `item_codes` (required): List of item codes (as JSON array or JSON string)

**Example Request:**
```bash
curl -X POST \
  "https://your-domain.com/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_products_by_codes" \
  -H "Authorization: token YOUR_API_KEY:YOUR_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"item_codes": ["ITEM-001", "ITEM-002", "ITEM-003"]}'
```

**Response Format:**
```json
{
  "success": true,
  "products": [
    {
      "item_code": "ITEM-001",
      "item_name": "Product 1",
      "description": "Product description",
      "item_group": "Products",
      "stock_uom": "Nos",
      "image": "/files/product-1.jpg",
      "price": 99.99,
      "currency": "USD",
      "stock_qty": 100,
      "in_stock": true,
      "disabled": 0,
      "is_sales_item": 1
    }
  ],
  "count": 1
}
```

---

## CORS Configuration

The API is configured to accept requests from the following Webflow domains:

- `https://www.illumenatelighting.com`
- `https://illumenatelighting.webflow.io`

Allowed methods: GET, POST, OPTIONS

Allowed headers: Content-Type, Authorization

---

## Authentication

### For Public Endpoints
- `get_product_detail` and `get_related_products` do not require authentication
- Can be called directly from client-side JavaScript

### For Authenticated Endpoints
- `get_active_products_for_webflow` and `get_products_by_codes` require authentication
- Use API Key authentication:
  - Generate API Key and Secret in ERPNext (User → API Access)
  - Pass as header: `Authorization: token API_KEY:API_SECRET`

---

## Error Handling

All endpoints return a consistent error format:

```json
{
  "success": false,
  "error": "Error message describing what went wrong",
  "product": null  // or "products": []
}
```

All errors are logged to ERPNext's error log with the title "Webflow Integration Error".

---

## Data Flow

### Hybrid Sync Approach

1. **Base Catalog Sync (Every 6 hours via n8n)**
   - n8n calls `get_active_products_for_webflow` to get all products
   - Syncs product metadata to Webflow CMS
   - Uses `modified_since` parameter to get only updated products

2. **Real-Time Stock/Pricing (Client-side JavaScript)**
   - Webflow pages call `get_product_detail` on page load
   - JavaScript updates stock and pricing dynamically
   - No caching needed for real-time data

### Example n8n Workflow

1. **Scheduled Trigger** (Every 6 hours)
2. **HTTP Request Node**: Call `get_active_products_for_webflow`
3. **Loop Node**: Process each product
4. **Webflow Node**: Create/Update CMS item
5. **Error Handler**: Log any failures

### Example Client-side JavaScript

```javascript
// On product page load
const itemCode = document.querySelector('[data-item-code]').dataset.itemCode;

fetch(`https://your-domain.com/api/method/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_product_detail?item_code=${itemCode}`)
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      // Update price
      document.querySelector('.price').textContent = `$${data.product.price}`;
      
      // Update stock status
      const stockElement = document.querySelector('.stock-status');
      stockElement.textContent = data.product.in_stock ? 'In Stock' : 'Out of Stock';
      stockElement.className = data.product.in_stock ? 'in-stock' : 'out-of-stock';
      
      // Update technical specs if configured fixture
      if (data.product.is_configured_fixture && data.product.technical_specs) {
        document.querySelector('.output').textContent = 
          data.product.technical_specs.estimated_delivered_output?.display || 'N/A';
        document.querySelector('.length').textContent = 
          data.product.technical_specs.length?.display || 'N/A';
      }
    }
  })
  .catch(error => console.error('Error fetching product details:', error));
```

---

## Performance Considerations

1. **Minimal Database Queries**
   - Uses `frappe.db.get_value()` for single field lookups
   - Batches related queries when possible

2. **Early Returns**
   - Returns immediately if product not found or disabled
   - Avoids unnecessary processing

3. **Caching Recommendations**
   - Public endpoints can be cached client-side for 5-10 minutes
   - Authenticated endpoints should not be cached (real-time data)

---

## Testing

Unit tests are available in `test_webflow_integration.py`. To run tests:

```bash
bench --site your-site-name run-tests --app illumenate_lighting --module illumenate_lighting.illumenate_lighting.api.test_webflow_integration
```

---

## Webflow Portal Integration APIs

The following endpoints support the Webflow ↔ ERPNext portal integration
including authentication, dealer-gated pricing, and project/schedule management.

### 6. Get User Context (Authenticated)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_auth.get_user_context`

**Method:** POST

**Authentication:** Required (session cookie or token)

**Description:** Returns the authenticated user's context including role, linked customer, and API credentials. Called after successful login to populate the Webflow client session.

**Response Format:**
```json
{
  "success": true,
  "user": "dealer@example.com",
  "full_name": "John Dealer",
  "is_dealer": true,
  "is_internal": false,
  "customer": "CUST-001",
  "customer_name": "Acme Lighting",
  "api_key": "abc123...",
  "api_secret": "xyz789..."
}
```

### 7. Get Pricing (Dealer Only)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_portal.get_pricing`

**Method:** POST

**Authentication:** Required + Dealer or Internal role

**Parameters:**
- `item_code` (required): Item code to look up pricing for

**Response Format:**
```json
{
  "success": true,
  "price": 149.99,
  "currency": "USD",
  "price_list": "Standard Selling"
}
```

### 8. Get Projects (Authenticated)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_portal.get_projects`

**Method:** POST

**Authentication:** Required

**Description:** Returns all active ILL Projects linked to the user's Customer. Internal users see all projects.

**Response Format:**
```json
{
  "success": true,
  "projects": [
    {
      "name": "ILL-PROJ-2026-00001",
      "project_name": "Downtown Office Remodel",
      "customer": "CUST-001",
      "status": "ACTIVE",
      "location": "New York, NY"
    }
  ]
}
```

### 9. Get Fixture Schedules (Authenticated)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_portal.get_fixture_schedules`

**Method:** POST

**Authentication:** Required + Project ownership

**Parameters:**
- `project` (required): Name of the ilL-Project

**Response Format:**
```json
{
  "success": true,
  "schedules": [
    {
      "name": "ILL-SCHED-2026-00001",
      "schedule_name": "Floor 1 Lighting",
      "status": "DRAFT",
      "line_count": 5
    }
  ]
}
```

### 10. Get Line IDs (Authenticated)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_portal.get_line_ids`

**Method:** POST

**Authentication:** Required + Project ownership

**Parameters:**
- `project` (required): Name of the ilL-Project
- `fixture_schedule` (required): Name of the ilL-Project-Fixture-Schedule

**Response Format:**
```json
{
  "success": true,
  "lines": [
    {
      "name": "abc123",
      "line_id": "L001",
      "fixture_part_number": "SH01-DRY-30-MED-CLR-SUR-BLK-1000",
      "qty": 2,
      "location": "Conference Room A",
      "manufacturer_type": "ILLUMENATE",
      "configuration_status": "Configured"
    }
  ]
}
```

### 11. Add Fixture to Schedule (Authenticated)

**Endpoint:** `/api/method/illumenate_lighting.illumenate_lighting.api.webflow_portal.add_fixture_to_schedule`

**Method:** POST

**Authentication:** Required + Project ownership + Schedule write permission

**Parameters:**
- `project` (required): Name of the ilL-Project
- `fixture_schedule` (required): Name of the ilL-Project-Fixture-Schedule
- `fixture_part_number` (required): The configured fixture part number
- `line_id` (optional): Existing line ID to overwrite
- `overwrite` (optional): `"1"` to overwrite existing line, `"0"` to create new (default)

**Response Format:**
```json
{
  "success": true,
  "line_id": "L001",
  "action": "created"
}
```

---

## Webflow Client-Side Integration

Include `webflow_portal.js` on Webflow pages to use the portal integration:

```html
<script src="https://your-erpnext.com/assets/illumenate_lighting/js/webflow_portal.js"></script>
<script>
  IllumenatePortal.init({ erpnextUrl: "https://your-erpnext.com" });

  // Login
  IllumenatePortal.login("user@example.com", "password").then(function(ctx) {
    console.log("Logged in:", ctx.user, "Dealer:", ctx.is_dealer);
  });

  // Bind cascading dropdowns (auto-populates on selection change)
  IllumenatePortal.bindCascadingDropdowns({
    projectSelector: "#project-select",
    scheduleSelector: "#schedule-select",
    lineSelector: "#line-select",
  });

  // Fetch pricing for dealers
  IllumenatePortal.fetchPricing("ITEM-001", document.getElementById("price-display"));

  // Add fixture to schedule
  IllumenatePortal.addFixture("PROJ-001", "SCHED-001", "SH01-xxx", "L001", true);
</script>
```

---

## Support

For issues or questions, contact:
- Email: hi@illumenate.lighting
- Repository: https://github.com/kevinschern-illumenate/erpillumenatelighting
