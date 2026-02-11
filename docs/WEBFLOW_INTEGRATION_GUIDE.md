# Webflow Integration Guide for Web Designers

## Overview

This document explains how ilLumenate Lighting's ERPNext system integrates with Webflow for:
1. **Product catalog sync** (ERPNext → Webflow via n8n)
2. **Real-time product data** (Webflow → ERPNext via JavaScript)
3. **Fixture configurator** (Interactive configuration on product pages)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SYNC FLOW (Every 6 Hours)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────┐         ┌──────────────┐         ┌──────────────┐        │
│   │   ERPNext    │ ──────► │     n8n      │ ──────► │   Webflow    │        │
│   │   Products   │  Fetch  │  Automation  │ Create/ │   Products   │        │
│   │   Database   │ Products│   Workflow   │ Update  │  Collection  │        │
│   └──────────────┘         └──────────────┘         └──────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         REAL-TIME FLOW (Client-Side)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────┐         ┌──────────────┐         ┌──────────────┐        │
│   │   Website    │ ──────► │  JavaScript  │ ──────► │   ERPNext    │        │
│   │   Visitor    │ Loads   │     API      │  Fetch  │     API      │        │
│   │   Browser    │  Page   │    Calls     │  Data   │  (Public)    │        │
│   └──────────────┘         └──────────────┘         └──────────────┘        │
│         │                         │                        │                │
│         │                         │                        ▼                │
│         │                         │                 ┌──────────────┐        │
│         │                         │◄────────────────│   Stock &    │        │
│         │                         │    Response     │   Pricing    │        │
│         │                         │                 └──────────────┘        │
│         │                         │                                         │
│         │◄────────────────────────┘                                         │
│              Update DOM                                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: Webflow CMS Collections

### Products Collection

**Collection ID:** `696fc3c5c42c86528e97f413`

This collection stores the base product catalog. Products are synced from ERPNext every 6 hours.

#### Required Fields

| Field Name | Slug | Type | Description |
|------------|------|------|-------------|
| Name | `name` | Plain Text | Product name (auto-created by Webflow) |
| Slug | `slug` | Plain Text | URL slug (auto-created by Webflow) |
| Product Type | `product-type` | Option | Type of product |
| Short Description | `short-description` | Plain Text | Brief product description |
| Features | `features` | Plain Text | Key product features and selling points |
| Long Description | `long-description` | Rich Text | Full product description |
| Is Configurable | `is-configurable` | Switch | Whether product has configurator |
| Min Length (mm) | `min-length-mm` | Number | Minimum fixture length |
| Max Length (mm) | `max-length-mm` | Number | Maximum fixture length |
| ERP Sync ID | `erp-sync-id` | Plain Text | ERPNext sync identifier |
| Specifications HTML | `specifications-html` | Rich Text | Auto-generated specs list |
| Specifications JSON | `specifications-json` | Plain Text | Structured specs with attribute links |
| Attribute Links JSON | `attribute-links-json` | Plain Text | All linked attributes for filtering |
| Featured Image | `featured-image` | Image | Main product image |

#### Filter Fields (for CMS filtering)

These plain-text filter fields contain comma-separated attribute names for Webflow CMS filtering. When the n8n sync runs, it automatically builds these from the product's attribute links:

| Field Name | Slug | Type | Description |
|------------|------|------|-------------|
| CRI Filter | `cri-filter` | Plain Text | e.g. "90+,95+" |
| Finish Filter | `finish-filter` | Plain Text | e.g. "Black Anodized,White" |
| Lens Filter | `lens-filter` | Plain Text | Available lens types |
| Mounting Filter | `mounting-filter` | Plain Text | Installation options |
| Output Level Filter | `output-levels-filter` | Plain Text | Lumen output options |
| Environment Rating Filter | `environment-ratings-filter` | Plain Text | IP ratings, wet/dry location |
| Feed Direction Filter | `feed-direction-filter` | Plain Text | Feed direction options |
| LED Package Filter | `led-package-filter` | Plain Text | LED chip/package types |
| Dimming Filter | `dimming-filter` | Plain Text | Dimming protocol options |

**How Attribute Filter Fields Work:**

1. In ERPNext, each Webflow Product is linked to a Fixture Template
2. The Fixture Template has "Allowed Options" (finishes, lenses, mounting methods, etc.) and "Allowed Tape Offerings" (CCT, output levels, LED packages)
3. When the Webflow Product is saved, it automatically pulls all applicable attributes from the template
4. During product sync, the n8n workflow builds comma-separated name strings for each filter field
5. Webflow receives plain-text filter values that can be used in CMS filtering

**Enabling Product Filtering:**

With filter fields, you can create filters in Webflow using conditional visibility or custom filtering:

```html
<!-- Filter products by finish -->
<a href="/products?finish=black-anodized">Black Anodized</a>

<!-- In Webflow: Create a Collection List filtered by "Finishes contains [current finish item]" -->
```

#### Attribute Links JSON Structure

The `attribute-links-json` field contains all linked attributes for a product:

```json
[
  {
    "attribute_type": "Finish",
    "attribute_doctype": "ilL-Attribute-Finish",
    "attribute_name": "Black Anodized",
    "display_label": "Black Anodized",
    "webflow_item_id": "65abc123def456",
    "display_order": 1
  },
  {
    "attribute_type": "CCT",
    "attribute_doctype": "ilL-Attribute-CCT",
    "attribute_name": "3000K",
    "display_label": "3000K Warm White",
    "webflow_item_id": "65abc789ghi012",
    "display_order": 2
  }
]
```

#### Specifications JSON Structure

The `specifications-json` field contains structured specification data that can be used for Webflow collection filtering. Each specification can include linked attribute options that reference other Webflow collections (e.g., Finishes, Lens Appearances).

```json
[
  {
    "spec_group": "Physical",
    "spec_label": "Finish Options",
    "spec_value": "Black Anodized, White, Silver",
    "spec_unit": "",
    "display_order": 1,
    "show_on_card": false,
    "attribute_doctype": "ilL-Attribute-Finish",
    "attribute_options": [
      {
        "attribute_type": "Finish",
        "attribute_doctype": "ilL-Attribute-Finish",
        "attribute_value": "Black Anodized",
        "display_label": "Black Anodized",
        "is_default": true
      },
      {
        "attribute_type": "Finish",
        "attribute_doctype": "ilL-Attribute-Finish",
        "attribute_value": "White",
        "display_label": "White",
        "is_default": false
      }
    ]
  },
  {
    "spec_group": "Optical",
    "spec_label": "Light Color (CCT)",
    "spec_value": "2700K + 3000K + 4000K",
    "spec_unit": "",
    "display_order": 2,
    "show_on_card": true,
    "attribute_doctype": "ilL-Attribute-CCT",
    "attribute_options": [
      {
        "attribute_type": "CCT",
        "attribute_doctype": "ilL-Attribute-CCT",
        "attribute_value": "2700K",
        "display_label": "2700K Warm White",
        "code": "27",
        "kelvin": 2700
      }
    ]
  }
]
```

**Using Specifications for Filtering:**

1. Create corresponding Webflow collections for each attribute type (e.g., "Finishes", "CCT Options", "Lens Types")
2. In your Webflow CMS, parse the `specifications-json` field to extract `attribute_options`
3. Use the `attribute_value` field to match/link to items in your attribute collections
4. This enables filtering products by specific attribute values (e.g., "Show all products with Frosted lens option")

#### Product Type Options

Add these exact values to the `product-type` Option field:
- `Fixture Template`
- `Driver`
- `Controller`
- `Extrusion Kit`
- `LED Tape`
- `Component`
- `Accessory`

---

### Categories Collection

**Collection ID:** `697105f368b2ba752d0651b8`

This collection stores product categories for navigation.

#### Required Fields

| Field Name | Slug | Type | Description |
|------------|------|------|-------------|
| Name | `name` | Plain Text | Category name |
| Slug | `slug` | Plain Text | URL slug |
| Description | `description` | Plain Text | Category description |
| Sort Order | `sort-order` | Number | Display order |
| Parent Category | `parent-category` | Reference | Link to parent category |
| Featured Image | `featured-image` | Image | Category image |

---

## Part 2: Product Pages

### Static Content (From Webflow CMS)

These fields are populated by the n8n sync and should be bound directly to CMS fields:

- **Product Name** → `name`
- **Short Description** → `short-description`
- **Features** → `features`
- **Long Description** → `long-description`
- **Featured Image** → `featured-image`
- **Specifications** → `specifications-html`

### Dynamic Content (Fetched via JavaScript)

These values are fetched in real-time from ERPNext when the page loads:

- **Price** (current pricing)
- **Stock Status** (in stock / out of stock)
- **Lead Time** (estimated availability)

#### JavaScript Example: Fetch Real-Time Product Data

```html
<script>
// Configuration
const ERPNEXT_API_BASE = 'https://illumenatelighting.v.frappe.cloud/api/method';

// Get product data when page loads
document.addEventListener('DOMContentLoaded', async function() {
  // Get the product slug from the URL or a data attribute
  const productSlug = window.location.pathname.split('/').pop();
  
  try {
    const response = await fetch(
      `${ERPNEXT_API_BASE}/illumenate_lighting.illumenate_lighting.api.webflow_integration.get_product_detail?sku=${productSlug}`
    );
    
    const data = await response.json();
    
    if (data.message && data.message.success) {
      const product = data.message.product;
      
      // Update price display
      document.querySelector('[data-price]').textContent = `$${product.price.toFixed(2)}`;
      
      // Update stock status
      const stockElement = document.querySelector('[data-stock-status]');
      if (product.in_stock) {
        stockElement.textContent = 'In Stock';
        stockElement.classList.add('in-stock');
      } else {
        stockElement.textContent = 'Out of Stock';
        stockElement.classList.add('out-of-stock');
      }
    }
  } catch (error) {
    console.error('Failed to fetch product data:', error);
  }
});
</script>
```

### Product Page HTML Structure

```html
<div class="product-page" data-product-slug="{{ slug }}">
  <!-- Static Content (CMS Bound) -->
  <div class="product-header">
    <h1>{{ name }}</h1>
    <p class="short-description">{{ short-description }}</p>
  </div>
  
  <div class="product-image">
    <img src="{{ featured-image.url }}" alt="{{ name }}">
  </div>
  
  <!-- Dynamic Content (JavaScript Updated) -->
  <div class="product-pricing">
    <span class="price" data-price>Loading...</span>
    <span class="stock-status" data-stock-status>Checking availability...</span>
  </div>
  
  <!-- Specifications (CMS Rich Text) -->
  <div class="specifications">
    {{ specifications-html }}
  </div>
  
  <!-- Configurator Section (for configurable products) -->
  <div class="configurator-section" data-is-configurable="{{ is-configurable }}">
    <!-- Configurator loads here -->
  </div>
</div>
```

---

## Part 3: Fixture Configurator

The configurator is an interactive component that allows users to configure custom lighting fixtures. It only appears on products where `is-configurable` is `true`.

### Configurator Flow

The configurator follows a horizontal step-by-step flow:

```
┌───────┐   ┌─────────┐   ┌─────┐   ┌────────┐   ┌──────┐   ┌──────────┐
│Series │ → │ Dry/Wet │ → │ CCT │ → │ Output │ → │ Lens │ → │ Mounting │
│(locked)│   │         │   │     │   │        │   │      │   │          │
└───────┘   └─────────┘   └─────┘   └────────┘   └──────┘   └──────────┘
                                          │
    ┌─────────────────────────────────────┘
    ▼
┌────────┐   ┌────────┐   ┌─────────────┐   ┌─────────────┐
│ Finish │ → │ Length │ → │ Start Feed  │ → │  End Feed   │
│        │   │        │   │ Dir + Length│   │ Dir + Length│
└────────┘   └────────┘   └─────────────┘   └─────────────┘
                                                    │
                                                    ▼
                                            ┌──────────────┐
                                            │ Part Number  │
                                            │   Preview    │
                                            └──────────────┘
```

### Step Definitions

| Step | Name | Label | Required | Cascades From |
|------|------|-------|----------|---------------|
| 0 | series | Series | Yes | (Locked - from product) |
| 1 | environment_rating | Dry/Wet | Yes | series |
| 2 | cct | CCT | Yes | series, environment_rating |
| 3 | output_level | Output | Yes | series, environment_rating, cct |
| 4 | lens_appearance | Lens | Yes | series |
| 5 | mounting_method | Mounting | Yes | (Independent) |
| 6 | finish | Finish | Yes | (Independent) |
| 7 | length | Length | Yes | (Independent) |
| 8 | start_feed_direction | Start Feed Direction | Yes | (Independent) |
| 9 | start_feed_length | Start Feed Length | Yes | start_feed_direction |
| 10 | end_feed_direction | End Feed Direction | Yes | (Independent) |
| 11 | end_feed_length | End Feed Length | Yes | end_feed_direction |

### Cascading Options

When a user selects an option, dependent options are filtered:

1. **Environment Rating** → Filters available CCT options
2. **CCT** → Filters available Output Level options
3. **Output Level** is recalculated when Lens changes (transmission affects delivered output)

### Configurator API Endpoints

#### 1. Initialize Configurator

**Endpoint:** `GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_configurator_init`

**Parameters:**
- `product_slug` (required): The Webflow product slug

**Response:**
```json
{
  "success": true,
  "product": {
    "slug": "ra01-linear",
    "name": "RA01 Linear",
    "template_code": "RA01"
  },
  "series": {
    "series_code": "RA01",
    "series_name": "RA01 Linear",
    "led_package": "Full Spectrum 2835",
    "led_package_code": "FS",
    "display_name": "ilLumenate RA01 Linear [FS] Full Spectrum"
  },
  "steps": [
    {"step": 0, "name": "series", "label": "Series", "required": true, "locked": true},
    {"step": 1, "name": "environment_rating", "label": "Dry/Wet", "required": true}
    // ... more steps
  ],
  "options": {
    "environment_ratings": [
      {"value": "Dry", "label": "Dry", "code": "D", "description": "Indoor dry locations"},
      {"value": "Wet", "label": "Wet", "code": "W", "description": "Outdoor/wet locations"}
    ],
    "lens_appearances": [
      {"value": "Clear", "label": "Clear", "code": "CLR", "transmission": 95},
      {"value": "Frosted", "label": "Frosted", "code": "FRO", "transmission": 85}
    ],
    "mounting_methods": [
      {"value": "Surface", "label": "Surface Mount", "code": "SM"},
      {"value": "Recessed", "label": "Recessed", "code": "RC"}
    ],
    "finishes": [
      {"value": "Black", "label": "Black", "code": "BK"},
      {"value": "White", "label": "White", "code": "WH"},
      {"value": "Silver", "label": "Silver", "code": "SV"}
    ],
    "feed_directions": [
      {"value": "left", "label": "Left"},
      {"value": "right", "label": "Right"},
      {"value": "back", "label": "Back"},
      {"value": "none", "label": "No Feed"}
    ],
    "leader_lengths_ft": [2, 4, 6, 8, 10, 15, 20, 25, 30]
  },
  "length_config": {
    "min_inches": 12,
    "max_inches": 120,
    "default_inches": 50,
    "max_run_note": "Maximum length is 30 ft"
  },
  "part_number_prefix": "ILL-RA01-FS"
}
```

#### 2. Get Cascading Options

**Endpoint:** `GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_cascading_options`

**Parameters:**
- `product_slug` (required): The Webflow product slug
- `step_name` (required): The step that was just selected
- `selections` (required): JSON string of current selections

**Example Call:**
```javascript
const response = await fetch(`${API_BASE}/get_cascading_options?` + new URLSearchParams({
  product_slug: 'ra01-linear',
  step_name: 'environment_rating',
  selections: JSON.stringify({
    environment_rating: 'Dry'
  })
}));
```

**Response:**
```json
{
  "success": true,
  "step_completed": "environment_rating",
  "selections": {"environment_rating": "Dry"},
  "updated_options": {
    "ccts": [
      {"value": "2700K", "label": "2700K", "code": "27", "kelvin": 2700},
      {"value": "3000K", "label": "3000K", "code": "30", "kelvin": 3000},
      {"value": "4000K", "label": "4000K", "code": "40", "kelvin": 4000}
    ]
  },
  "clear_selections": ["cct", "output_level"],
  "part_number_preview": {
    "full": "ILL-RA01-FS-D-xx-xxx-xx-xx",
    "complete_percentage": 15
  }
}
```

#### 3. Validate Configuration

**Endpoint:** `GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.validate_configuration`

**Parameters:**
- `product_slug` (required): The Webflow product slug
- `selections` (required): JSON string of all selections

**Response (Valid):**
```json
{
  "success": true,
  "is_valid": true,
  "part_number": "ILL-RA01-FS-D-30-450-CLR-SM-BK-50-L4-R4",
  "tape_offering_id": "TAPE-001",
  "configuration_summary": {
    "Series": "RA01 Linear [FS]",
    "Environment": "Dry",
    "CCT": "3000K",
    "Output": "450 lm/ft",
    "Lens": "Clear",
    "Mounting": "Surface Mount",
    "Finish": "Black",
    "Length": "50 inches",
    "Start Feed": "Left, 4ft lead",
    "End Feed": "Right, 4ft lead"
  },
  "pricing": {
    "unit_price": 245.00,
    "currency": "USD"
  },
  "can_add_to_project": false,
  "can_add_to_cart": true
}
```

**Response (Invalid):**
```json
{
  "success": false,
  "is_valid": false,
  "error": "Missing required fields: finish, length_inches",
  "missing_fields": ["finish", "length_inches"]
}
```

#### 4. Get Part Number Preview

**Endpoint:** `GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_part_number_preview`

**Parameters:**
- `product_slug` (required): The Webflow product slug
- `selections` (required): JSON string of current selections

**Response:**
```json
{
  "success": true,
  "part_number_preview": "ILL-RA01-FS-D-30-xxx-CLR-xx-xx-xx-xx-xx",
  "segments": [
    {"name": "prefix", "value": "ILL", "complete": true},
    {"name": "series", "value": "RA01", "complete": true},
    {"name": "led_package", "value": "FS", "complete": true},
    {"name": "environment", "value": "D", "complete": true},
    {"name": "cct", "value": "30", "complete": true},
    {"name": "output", "value": "xxx", "complete": false},
    {"name": "lens", "value": "CLR", "complete": true},
    {"name": "mounting", "value": "xx", "complete": false},
    {"name": "finish", "value": "xx", "complete": false}
  ],
  "complete_percentage": 55
}
```

### Configurator JavaScript Implementation

```javascript
class FixtureConfigurator {
  constructor(productSlug, containerSelector) {
    this.productSlug = productSlug;
    this.container = document.querySelector(containerSelector);
    this.selections = {};
    this.options = {};
    this.API_BASE = 'https://illumenatelighting.v.frappe.cloud/api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator';
  }

  async init() {
    try {
      const response = await fetch(`${this.API_BASE}.get_configurator_init?product_slug=${this.productSlug}`);
      const data = await response.json();
      
      if (data.message && data.message.success) {
        this.config = data.message;
        this.options = data.message.options;
        this.renderConfigurator();
      } else {
        console.error('Failed to initialize configurator:', data.message?.error);
      }
    } catch (error) {
      console.error('Configurator init error:', error);
    }
  }

  renderConfigurator() {
    // Render the configurator UI based on this.config.steps
    // Each step should show available options from this.options
    this.container.innerHTML = `
      <div class="configurator">
        <div class="step-indicator">
          ${this.config.steps.map(step => `
            <div class="step ${step.locked ? 'locked' : ''}" data-step="${step.step}">
              ${step.label}
            </div>
          `).join('')}
        </div>
        
        <div class="part-number-preview">
          <span class="prefix">${this.config.part_number_prefix}</span>
          <span class="dynamic">-xx-xxx-xx-xx-xx-xx-xx</span>
        </div>
        
        <div class="options-container">
          ${this.renderStepOptions()}
        </div>
        
        <div class="actions">
          <button class="add-to-cart" disabled>Add to Cart</button>
          <a href="${this.config.complex_fixture_url}" class="complex-link">
            Have a complex jumper fixture? Use our Fixture Coordinator →
          </a>
        </div>
      </div>
    `;
    
    this.attachEventListeners();
  }

  renderStepOptions() {
    // Render option buttons/dropdowns for each step
    // This is a simplified example
    return `
      <div class="option-group" data-step="environment_rating">
        <h4>Environment</h4>
        <div class="option-buttons">
          ${this.options.environment_ratings.map(opt => `
            <button class="option-btn" data-value="${opt.value}" data-step="environment_rating">
              ${opt.label}
            </button>
          `).join('')}
        </div>
      </div>
      <!-- More option groups... -->
    `;
  }

  attachEventListeners() {
    // Listen for option selections
    this.container.querySelectorAll('.option-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const step = e.target.dataset.step;
        const value = e.target.dataset.value;
        this.selectOption(step, value);
      });
    });
  }

  async selectOption(stepName, value) {
    // Update selections
    this.selections[stepName] = value;
    
    // Mark button as selected
    this.container.querySelectorAll(`[data-step="${stepName}"]`).forEach(btn => {
      btn.classList.remove('selected');
    });
    this.container.querySelector(`[data-step="${stepName}"][data-value="${value}"]`)?.classList.add('selected');
    
    // Fetch cascading options
    try {
      const response = await fetch(`${this.API_BASE}.get_cascading_options?` + new URLSearchParams({
        product_slug: this.productSlug,
        step_name: stepName,
        selections: JSON.stringify(this.selections)
      }));
      
      const data = await response.json();
      
      if (data.message && data.message.success) {
        // Clear downstream selections
        for (const field of data.message.clear_selections || []) {
          delete this.selections[field];
          this.clearStepUI(field);
        }
        
        // Update options for dependent steps
        for (const [optionKey, optionValues] of Object.entries(data.message.updated_options || {})) {
          this.updateStepOptions(optionKey, optionValues);
        }
        
        // Update part number preview
        if (data.message.part_number_preview) {
          this.updatePartNumberPreview(data.message.part_number_preview);
        }
        
        // Check if configuration is complete
        this.checkComplete();
      }
    } catch (error) {
      console.error('Error fetching cascading options:', error);
    }
  }

  updateStepOptions(stepName, options) {
    const container = this.container.querySelector(`[data-step="${stepName}"] .option-buttons`);
    if (container) {
      container.innerHTML = options.map(opt => `
        <button class="option-btn" data-value="${opt.value}" data-step="${stepName}">
          ${opt.label}
        </button>
      `).join('');
      
      // Re-attach event listeners
      container.querySelectorAll('.option-btn').forEach(btn => {
        btn.addEventListener('click', (e) => this.selectOption(stepName, e.target.dataset.value));
      });
    }
  }

  clearStepUI(stepName) {
    this.container.querySelectorAll(`[data-step="${stepName}"]`).forEach(btn => {
      btn.classList.remove('selected');
    });
  }

  updatePartNumberPreview(preview) {
    const previewEl = this.container.querySelector('.part-number-preview .dynamic');
    if (previewEl) {
      previewEl.textContent = preview.full.replace(this.config.part_number_prefix, '');
    }
  }

  async checkComplete() {
    // Validate configuration
    try {
      const response = await fetch(`${this.API_BASE}.validate_configuration?` + new URLSearchParams({
        product_slug: this.productSlug,
        selections: JSON.stringify(this.selections)
      }));
      
      const data = await response.json();
      
      if (data.message && data.message.success && data.message.is_valid) {
        // Enable Add to Cart
        const addBtn = this.container.querySelector('.add-to-cart');
        addBtn.disabled = false;
        addBtn.dataset.partNumber = data.message.part_number;
        
        // Show pricing
        if (data.message.pricing) {
          this.showPricing(data.message.pricing);
        }
      }
    } catch (error) {
      console.error('Validation error:', error);
    }
  }

  showPricing(pricing) {
    // Display pricing in UI
    let pricingEl = this.container.querySelector('.pricing-display');
    if (!pricingEl) {
      pricingEl = document.createElement('div');
      pricingEl.className = 'pricing-display';
      this.container.querySelector('.actions').prepend(pricingEl);
    }
    pricingEl.innerHTML = `
      <span class="price">${pricing.currency} $${pricing.unit_price.toFixed(2)}</span>
    `;
  }
}

// Initialize on product pages with configurator
document.addEventListener('DOMContentLoaded', function() {
  const configuratorEl = document.querySelector('[data-configurator]');
  if (configuratorEl && configuratorEl.dataset.isConfigurable === 'true') {
    const productSlug = configuratorEl.dataset.productSlug;
    const configurator = new FixtureConfigurator(productSlug, '[data-configurator]');
    configurator.init();
  }
});
```

---

## Part 4: ERPNext Doctype Reference

### Key Doctypes

| Doctype | Purpose | Used For |
|---------|---------|----------|
| `ilL-Webflow-Product` | Webflow product sync tracking | n8n sync |
| `ilL-Webflow-Category` | Webflow category sync tracking | n8n sync |
| `ilL-Fixture-Template` | Configurable fixture definitions | Configurator |
| `ilL-Configured-Fixture` | User-configured fixtures | Orders |
| `ilL-Attribute-CCT` | Color temperature options | Configurator |
| `ilL-Attribute-Output Level` | Lumen output options | Configurator |
| `ilL-Attribute-Lens Appearance` | Lens options | Configurator |
| `ilL-Attribute-Finish` | Finish/color options | Configurator |
| `ilL-Attribute-Mounting Method` | Mounting options | Configurator |
| `ilL-Attribute-Environment Rating` | Dry/Wet ratings | Configurator |
| `ilL-Rel-Tape Offering` | LED tape configurations | Configurator cascading |

---

## Part 5: CORS & Security

### Allowed Origins

The ERPNext API is configured to accept requests from:
- `https://www.illumenatelighting.com`
- `https://illumenatelighting.webflow.io`

### Public vs Authenticated Endpoints

| Endpoint | Auth Required | Use Case |
|----------|--------------|----------|
| `get_product_detail` | No | Client-side pricing/stock |
| `get_configurator_init` | No | Configurator initialization |
| `get_cascading_options` | No | Configurator step navigation |
| `validate_configuration` | No | Configurator validation |
| `get_webflow_products` | Yes (n8n) | Catalog sync |
| `mark_product_synced` | Yes (n8n) | Catalog sync |

---

## Part 6: Testing Checklist

### Product Pages

- [ ] Product name displays correctly
- [ ] Product image loads
- [ ] Short description displays
- [ ] Long description displays (Rich Text)
- [ ] Specifications HTML renders correctly
- [ ] Real-time price loads via JavaScript
- [ ] Stock status displays correctly
- [ ] Configurator appears for configurable products
- [ ] Configurator is hidden for non-configurable products

### Configurator

- [ ] Configurator initializes without errors
- [ ] Series is pre-selected and locked
- [ ] Environment options display
- [ ] Selecting Environment filters CCT options
- [ ] Selecting CCT filters Output options
- [ ] Lens, Mounting, Finish are independent
- [ ] Length slider/input works
- [ ] Feed direction dropdowns work
- [ ] Part number updates in real-time
- [ ] Validation shows errors for incomplete config
- [ ] Add to Cart enables when config is valid
- [ ] Complex fixture link navigates to portal

### API Responses

- [ ] `get_product_detail` returns stock & price
- [ ] `get_configurator_init` returns all options
- [ ] `get_cascading_options` filters correctly
- [ ] `validate_configuration` returns part number
- [ ] Error handling works gracefully

---

## Part 7: Sync Schedule

| Sync Type | Frequency | Trigger |
|-----------|-----------|---------|
| Products | Every 6 hours | n8n scheduled workflow |
| Categories | Every 6 hours | n8n scheduled workflow |
| Stock/Pricing | Real-time | Client-side JavaScript |

---

## Contact

For questions about the ERPNext API or data structure, contact the development team.

**ERPNext Instance:** https://illumenatelighting.v.frappe.cloud

**API Documentation:** See `WEBFLOW_API_DOCUMENTATION.md` in the codebase.
