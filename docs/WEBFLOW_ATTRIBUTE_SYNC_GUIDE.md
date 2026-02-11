# Webflow Attribute Sync Setup Guide

This guide explains how to set up automatic synchronization between ERPNext ilL-Attribute doctypes and Webflow CMS collections.

## Overview

The Webflow Attribute Sync system automatically pushes attribute data (CCT, Finish, Dimming Protocol, etc.) from ERPNext to corresponding Webflow CMS collections. This enables:

- **Automatic sync**: When you create or update an attribute in ERPNext, it's automatically marked for sync
- **Scheduled sync**: n8n runs every 6 hours to sync pending changes
- **Manual sync**: Trigger sync manually from ERPNext or n8n
- **Error handling**: Failed syncs are logged and can be retried

## Prerequisites

1. **ERPNext Setup**
   - ilLumenate Lighting app installed
   - All ilL-Attribute doctypes created

2. **Webflow Setup**
   - Webflow site with CMS enabled
   - API token with write access to CMS

3. **n8n Setup**
   - n8n instance running (self-hosted or cloud)
   - Access to create workflows and credentials

## Step 1: Create Webflow CMS Collections

Create the following collections in Webflow CMS. Each collection should have fields that match the ERPNext attributes:

### Core Attribute Collections

| Collection Name | Key Fields | ERPNext Doctype |
|----------------|------------|-----------------|
| CCT Options | name, slug, cct-code, kelvin-value, hex-color, lumen-multiplier | ilL-Attribute-CCT |
| Finish Options | name, slug, finish-code, hex-color, texture, image | ilL-Attribute-Finish |
| Dimming Protocols | name, slug, protocol-code, protocol-type, signal-type, requires-interface | ilL-Attribute-Dimming Protocol |
| CRI Options | name, slug, cri-code, cri-value, description | ilL-Attribute-CRI |
| Environment Ratings | name, slug, rating-code, description | ilL-Attribute-Environment Rating |
| IP Ratings | name, slug, ip-code, solid-protection, liquid-protection | ilL-Attribute-IP Rating |
| LED Packages | name, slug, package-code, manufacturer | ilL-Attribute-LED Package |
| Lens Appearances | name, slug, lens-code, transmission | ilL-Attribute-Lens Appearance |
| Mounting Methods | name, slug, mounting-code, description | ilL-Attribute-Mounting Method |
| Output Levels | name, slug, output-code, watts-per-meter, lumens-per-meter | ilL-Attribute-Output Level |
| Output Voltages | name, slug, voltage-code, voltage-value | ilL-Attribute-Output Voltage |
| Certifications | name, slug, certification-code, certification-body, badge-image | ilL-Attribute-Certification |

### Additional Collections

| Collection Name | ERPNext Doctype |
|----------------|-----------------|
| Endcap Styles | ilL-Attribute-Endcap Style |
| Endcap Colors | ilL-Attribute-Endcap Color |
| Joiner Angles | ilL-Attribute-Joiner Angle |
| Joiner Systems | ilL-Attribute-Joiner System |
| Feed Directions | ilL-Attribute-Feed-Direction |
| Lead Time Classes | ilL-Attribute-Lead Time Class |
| Leader Cables | ilL-Attribute-Leader Cable |
| Lens Interface Types | ilL-Attribute-Lens Interface Type |
| Power Feed Types | ilL-Attribute-Power Feed Type |
| Pricing Classes | ilL-Attribute-Pricing Class |
| SDCM Options | ilL-Attribute-SDCM |

### Getting Collection IDs

After creating each collection in Webflow:

1. Open the collection in Webflow Designer
2. Click on the collection name in the left panel
3. Look at the URL - the collection ID is the alphanumeric string
4. Example URL: `https://webflow.com/design/site-name?collection=67a1b2c3d4e5f6g7h8i9j0`
5. The collection ID is: `67a1b2c3d4e5f6g7h8i9j0`

## Step 2: Configure ERPNext

### 2.1 Run the Migration

After deploying the updated code, run the migration to add Webflow sync fields:

```bash
bench --site [sitename] migrate
```

This will add the following fields to all attribute doctypes:
- `webflow_item_id`: Stores the Webflow CMS item ID
- `webflow_sync_status`: Tracks sync status (Never Synced, Pending, Synced, Error)
- `webflow_last_synced`: Timestamp of last successful sync
- `webflow_sync_error`: Error message if sync failed

### 2.2 Configure Webflow Settings

1. Go to **Settings > ilL-Webflow-Settings** in ERPNext
2. Enter your Webflow Site ID
3. Enter the Collection ID for each attribute type
4. Save the settings

Example configuration:

| Field | Value |
|-------|-------|
| Site ID | 696fc3c5c42c86528e97f412 |
| CCT Collection ID | 67a1b2c3d4e5f6g7h8i9j001 |
| Finish Collection ID | 67a1b2c3d4e5f6g7h8i9j002 |
| Dimming Protocol Collection ID | 67a1b2c3d4e5f6g7h8i9j003 |
| ... | ... |

## Step 3: Set Up n8n

### 3.1 Create Credentials

#### ERPNext API Key

1. In n8n, go to **Credentials** > **Add Credential**
2. Select **Header Auth**
3. Name: `ERPNext API Key`
4. Header Name: `Authorization`
5. Header Value: `token [api_key]:[api_secret]`

To get the API key/secret in ERPNext:
1. Go to **Settings** > **User**
2. Select your integration user
3. Go to **API Access** section
4. Generate Keys

#### Webflow API Token

1. In n8n, go to **Credentials** > **Add Credential**
2. Select **Header Auth**
3. Name: `Webflow API Token`
4. Header Name: `Authorization`
5. Header Value: `Bearer [your-webflow-api-token]`

To get the Webflow API token:
1. Go to **Webflow Dashboard** > **Site Settings** > **Integrations**
2. Generate an API token with CMS write access

### 3.2 Import the Workflow

1. In n8n, go to **Workflows** > **Import from File**
2. Select `n8n_workflows/webflow_attribute_sync.json`
3. Update the credentials in each HTTP Request node
4. Update the ERPNext URL if different from `illumenatelighting.v.frappe.cloud`
5. Save and activate the workflow

### 3.3 Workflow Configuration

The workflow runs every 6 hours by default. To change:

1. Click on the **Every 6 Hours** node
2. Adjust the interval as needed
3. Save the workflow

## Step 4: Initial Sync

### 4.1 Trigger Initial Sync via API

Run this API call to mark all attributes as pending sync:

```bash
curl -X POST \
  'https://[your-site]/api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.trigger_attribute_sync' \
  -H 'Authorization: token [api_key]:[api_secret]' \
  -H 'Content-Type: application/json' \
  -d '{"sync_all": true}'
```

### 4.2 Manually Trigger n8n Workflow

1. Go to n8n
2. Open the **ERPNext → Webflow Attributes Sync** workflow
3. Click **Execute Workflow** to run immediately

### 4.3 Verify Sync Status

Check sync statistics via API:

```bash
curl -X GET \
  'https://[your-site]/api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.get_attribute_sync_statistics' \
  -H 'Authorization: token [api_key]:[api_secret]'
```

## Step 5: Link Attributes to Products

Once attributes are synced to Webflow, you can reference them in your Products collection.

### 5.1 Create Filter Fields in Webflow

In your Products collection, add Plain Text fields for each attribute type filter:

- `finish-filter` → Comma-separated Finish names
- `output-levels-filter` → Comma-separated Output Level names
- `environment-ratings-filter` → Comma-separated Environment Rating names
- `dimming-filter` → Comma-separated Dimming Protocol names
- etc.

### 5.2 Update Product Sync Workflow

The existing `webflow_product_sync.json` workflow includes filter field data automatically. The `webflow_product_attribute_filter_sync.json` workflow can also be used to update filter fields independently.

## API Reference

### Get Attributes for Sync

```
GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.get_webflow_attributes

Parameters:
- attribute_type: string (required) - e.g., "cct", "finish"
- sync_status: string - "needs_sync", "Pending", "Synced", "Error"
- limit: int - default 100
- offset: int - default 0
```

### Mark Attribute Synced

```
POST /api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.mark_attribute_synced

Body:
{
  "attribute_type": "cct",
  "doc_name": "2700K Warm White",
  "webflow_item_id": "67a1b2c3d4e5f6g7h8i9j0"
}
```

### Trigger Sync

```
POST /api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.trigger_attribute_sync

Body:
{
  "attribute_type": "cct",  // optional
  "doc_names": ["2700K Warm White"],  // optional
  "sync_all": true  // optional
}
```

### Get Sync Statistics

```
GET /api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.get_attribute_sync_statistics
```

## Troubleshooting

### Attributes Not Syncing

1. **Check sync status**: Go to the attribute document in ERPNext and check the Webflow Sync section
2. **Verify collection ID**: Ensure the collection ID is configured in ilL-Webflow-Settings
3. **Check n8n logs**: Look at the workflow execution history in n8n

### Sync Errors

1. **Invalid field mapping**: Ensure Webflow collection fields match the expected names
2. **API rate limits**: Webflow has rate limits - the workflow processes items one at a time
3. **Permission issues**: Verify the Webflow API token has write access

### Re-sync Failed Items

To retry failed syncs:

```bash
curl -X POST \
  'https://[your-site]/api/method/illumenate_lighting.illumenate_lighting.api.webflow_attributes.trigger_attribute_sync' \
  -H 'Authorization: token [api_key]:[api_secret]' \
  -H 'Content-Type: application/json' \
  -d '{"attribute_type": "cct", "sync_all": true}'
```

## Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│     ERPNext         │         │      Webflow        │
│  ┌───────────────┐  │         │  ┌───────────────┐  │
│  │ Attribute     │  │         │  │ CMS           │  │
│  │ Doctypes      │  │         │  │ Collections   │  │
│  │ (CCT, Finish) │──┼────────▶│  │               │  │
│  └───────────────┘  │   n8n   │  └───────────────┘  │
│         │           │         │         │           │
│         ▼           │         │         ▼           │
│  ┌───────────────┐  │         │  ┌───────────────┐  │
│  │ Webflow       │  │         │  │ Products      │  │
│  │ Products      │──┼────────▶│  │ Collection    │  │
│  └───────────────┘  │         │  └───────────────┘  │
└─────────────────────┘         └─────────────────────┘
```

## Field Mapping Reference

### CCT Options

| ERPNext Field | Webflow Field |
|--------------|---------------|
| cct_name | name |
| cct_name (slugified) | slug |
| code | cct-code |
| kelvin | kelvin-value |
| hex_color | hex-color |
| sample_photo | sample-photo |
| lumen_multiplier | lumen-multiplier |
| description | description |
| sort_order | sort-order |

### Finish Options

| ERPNext Field | Webflow Field |
|--------------|---------------|
| finish_name | name |
| finish_name (slugified) | slug |
| code | finish-code |
| status | status |
| hex_color | hex-color |
| texture_feel | texture |
| image_attach | image |
| type | finish-type |
| thermal_performance_factor | thermal-factor |
| moq | moq |

See `webflow_attributes.py` for complete field mappings for all attribute types.
