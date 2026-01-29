# Webflow Form → Frappe CRM Lead Integration Guide

This guide explains how to set up automatic lead creation in Frappe CRM v16 from Webflow form submissions via n8n, and the complete lead-to-customer journey.

## Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MARKETING (Frappe CRM v16)                       │
│                                                                         │
│  ┌─────────────┐     ┌─────────┐     ┌──────────┐     ┌──────────┐     │
│  │   Webflow   │────▶│   n8n   │────▶│   Lead   │────▶│   Deal   │     │
│  │    Form     │     │ Webhook │     │  (CRM)   │     │  (CRM)   │     │
│  └─────────────┘     └─────────┘     └──────────┘     └────┬─────┘     │
│                                                            │           │
└────────────────────────────────────────────────────────────┼───────────┘
                                                             │
                                              ┌──────────────┘
                                              │ Convert to Customer
                                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SALES & OPERATIONS (ERPNext)                    │
│                                                                         │
│  ┌──────────┐     ┌─────────────┐     ┌───────────────┐                │
│  │ Customer │────▶│ Sales Order │────▶│ Manufacturing │                │
│  │          │     │             │     │    & Stock    │                │
│  └──────────┘     └─────────────┘     └───────────────┘                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Workflow Summary

| Stage | System | Responsibility | Actions |
|-------|--------|----------------|---------|
| **Lead** | Frappe CRM | Marketing | Capture, qualify, nurture |
| **Deal** | Frappe CRM | Marketing | Negotiate, proposal, close |
| **Customer** | ERPNext | Sales | Orders, manufacturing, fulfillment |

### Detailed Flow

1. **Lead Capture** (Automated)
   - User submits form on Webflow site
   - n8n receives webhook and transforms data
   - API creates Lead in Frappe CRM v16
   - Marketing team is notified

2. **Lead Nurturing** (Marketing Team)
   - Qualify the lead (New → Working → Qualified)
   - Add notes, schedule follow-ups
   - When ready, convert Lead → Deal

3. **Deal Management** (Marketing Team)
   - Create proposals/quotes
   - Track deal stages
   - When closed-won, convert Deal → Customer

4. **Customer Handoff** (Sales Team)
   - Customer record created in ERPNext
   - Contact linked to Customer
   - Sales team takes over for orders, manufacturing, etc.

## Field Mapping

| Webflow Form Field | Frappe CRM Lead Field | Notes |
|-------------------|----------------------|-------|
| First Name | `first_name` | Required |
| Last Name | `last_name` | |
| Email | `email` | Required (or phone) |
| Phone | `mobile_no` | Required (or email) |
| Company | `organization` | |
| Job Title | `job_title` | |
| Campaign ID | `webflow_campaign_id` | Custom field |
| UTM Source | `webflow_utm_source` | Custom field |
| UTM Medium | `webflow_utm_medium` | Custom field |
| UTM Campaign | `webflow_utm_campaign` | Custom field |

## Setup Instructions

### Step 1: Deploy and Migrate

The custom fields are added automatically via the patch `add_webflow_lead_fields.py` during migration.

```bash
# In your Frappe bench directory
bench migrate
```

This creates the following custom fields on CRM Lead:
- `webflow_campaign_id` - Campaign ID
- `webflow_utm_source` - UTM Source
- `webflow_utm_medium` - UTM Medium
- `webflow_utm_campaign` - UTM Campaign
- `webflow_form_name` - Form Name
- `webflow_form_id` - Webflow Form ID
- `webflow_submission_id` - Webflow Submission ID (unique, for deduplication)
- `webflow_form_data` - Additional Form Data (JSON)

It also adds "Webflow" as a Lead Source if CRM Lead Source doctype exists.

### Step 2: Import n8n Workflow

1. Open your n8n instance
2. Go to **Workflows** → **Import from File**
3. Import `n8n_workflows/webflow_lead_form.json`
4. Configure the **ERPNext API Key** credential:
   - Name: `ERPNext API Key`
   - Header Name: `Authorization`
   - Header Value: `token api_key:api_secret` (your ERPNext API credentials)

### Step 3: Get the Webhook URL

1. Open the imported workflow in n8n
2. Click on the **Webflow Form Webhook** node
3. Copy the **Webhook URL** (e.g., `https://your-n8n.com/webhook/webflow-lead-form`)

### Step 5: Configure Webflow Form

1. In Webflow Designer, select your form
2. Go to **Form Settings**
3. Under **Action**, select **Add Webhook**
4. Paste the n8n webhook URL
5. Publish your Webflow site

### Step 6: Add Hidden UTM Fields to Webflow Form

Add these hidden fields to capture UTM parameters:

```html
<!-- In Webflow's custom code or as hidden form fields -->
<input type="hidden" name="utm_source" data-wf-utm="source">
<input type="hidden" name="utm_medium" data-wf-utm="medium">
<input type="hidden" name="utm_campaign" data-wf-utm="campaign">
<input type="hidden" name="custom_campaign" data-wf-utm="campaign">
```

Add this JavaScript to populate UTM fields:

```html
<script>
document.addEventListener('DOMContentLoaded', function() {
  const urlParams = new URLSearchParams(window.location.search);
  
  // Map URL parameters to form fields
  const utmFields = {
    'utm_source': urlParams.get('utm_source'),
    'utm_medium': urlParams.get('utm_medium'),
    'utm_campaign': urlParams.get('utm_campaign'),
    'custom_campaign': urlParams.get('utm_campaign') || urlParams.get('campaign_id')
  };
  
  for (const [fieldName, value] of Object.entries(utmFields)) {
    if (value) {
      const field = document.querySelector(`[name="${fieldName}"]`);
      if (field) field.value = value;
    }
  }
});
</script>
```

## Testing

### Test the n8n Webhook Directly

```bash
curl -X POST "https://your-n8n.com/webhook/webflow-lead-form" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "+1-555-123-4567",
    "company": "Acme Corp",
    "utm_source": "google",
    "utm_medium": "cpc",
    "utm_campaign": "spring_2026"
  }'
```

### Test the ERPNext API Directly

```bash
curl -X POST "https://illumenatelighting.v.frappe.cloud/api/method/illumenate_lighting.illumenate_lighting.api.webflow_leads.create_lead_from_webflow" \
  -H "Content-Type: application/json" \
  -H "Authorization: token your_api_key:your_api_secret" \
  -d '{
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane.smith@example.com",
    "utm_source": "linkedin"
  }'
```

## Optional Enhancements

### Enable Slack Notifications

1. In the n8n workflow, click on the **Notify Sales Team (Slack)** node
2. Enable the node (toggle on)
3. Configure Slack credentials
4. Update the channel name to your sales channel

### Enable Auto-Reply Emails

1. In the n8n workflow, click on the **Send Auto-Reply Email** node
2. Enable the node (toggle on)
3. Configure SMTP credentials
4. Customize the email template

## Lead Conversion Workflow

### In Frappe CRM v16

#### Lead → Deal (Marketing Responsibility)

1. **View Leads**: Open Frappe CRM → Leads
2. **Qualify Lead**: Update status through the pipeline:
   - New → Contacted → Working → Qualified
3. **Convert to Deal**: Click "Convert to Deal" button
   - Creates a Deal record linked to the Lead
   - Preserves all UTM/campaign tracking data

#### Deal → Customer (Sales Handoff)

1. **Manage Deal**: Track through deal stages:
   - Qualification → Proposal → Negotiation → Closed Won
2. **Convert to Customer**: When deal is closed-won:
   - Click "Create Customer" or use the conversion action
   - This creates a **Customer** record in ERPNext
   - Optionally creates a **Contact** linked to the Customer
   - The Customer is now available in ERPNext for:
     - Sales Orders
     - Quotations
     - Manufacturing
     - Stock transactions
     - Invoicing

### Data Flow During Conversion

```
Frappe CRM Lead                 Frappe CRM Deal                 ERPNext Customer
├── first_name          ───────▶ ├── lead_name          ───────▶ ├── customer_name
├── last_name                    ├── organization                ├── customer_group
├── email               ───────▶ ├── email              ───────▶ ├── (Contact.email)
├── mobile_no           ───────▶ ├── mobile_no          ───────▶ ├── (Contact.phone)
├── organization        ───────▶ ├── organization       ───────▶ ├── customer_name
├── custom_utm_source            ├── (preserved)                 │
├── custom_utm_medium            ├── (preserved)                 │
└── custom_utm_campaign          └── (preserved)                 │
```

## Troubleshooting

### Common Issues

1. **"No form data received"**
   - Ensure Webflow form action is set to POST
   - Check webhook URL is correct

2. **"Missing required fields"**
   - Ensure form has `first_name` field (or `name`)
   - Ensure form has `email` or `phone` field

3. **"API authentication failed"**
   - Verify ERPNext API key credentials in n8n
   - Check that API user has permission to create CRM Leads

4. **Duplicate leads**
   - The system checks for duplicates by Webflow submission ID
   - Also checks for same email within 24 hours

### Checking Logs

- **n8n**: View execution history in n8n workflow
- **ERPNext**: Check Error Log doctype for "Webflow Lead Creation Error"

## API Reference

### `create_lead_from_webflow`

**Endpoint:** `POST /api/method/illumenate_lighting.illumenate_lighting.api.webflow_leads.create_lead_from_webflow`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| first_name | string | Yes | Lead's first name |
| last_name | string | No | Lead's last name |
| email | string | No* | Email address |
| phone | string | No* | Phone number |
| company_name | string | No | Company/Organization |
| job_title | string | No | Job title |
| website | string | No | Company website |
| source | string | No | Lead source (default: "Webflow") |
| campaign_id | string | No | Campaign identifier |
| utm_source | string | No | UTM source |
| utm_medium | string | No | UTM medium |
| utm_campaign | string | No | UTM campaign |
| form_name | string | No | Webflow form name |
| form_data | string | No | JSON of additional fields |
| webflow_form_id | string | No | Webflow form ID |
| webflow_submission_id | string | No | Webflow submission ID |

*Either email or phone is recommended for lead quality

**Response:**

```json
{
  "success": true,
  "lead_name": "CRM-LEAD-2026-00001",
  "message": "Lead created successfully",
  "duplicate": false
}
```
