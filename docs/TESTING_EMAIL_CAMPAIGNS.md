# Testing Email Campaign Automation

## Prerequisites

1. Scheduler must be enabled: **Setup → Settings → System Settings → Enable Scheduler**
2. Email settings configured: **Setup → Email → Email Account** (outgoing email)
3. Fixtures imported: Run `bench migrate`

## Test Cases

### Test 1: Verify Scheduler Job Registration

1. Go to **Setup → Scheduled Job Type**
2. Search for "send_email_to_leads_or_contacts"
3. Verify it exists and shows last execution time

### Test 2: Manual Email Campaign Test

1. Create a test Lead manually with email
2. Create an Email Campaign:
   - Campaign Name: Newsletter Welcome
   - Email Campaign For: Lead
   - Recipient: [your test lead]
   - Status: Scheduled
   - Start Date: Today
3. Run: `bench execute erpnext.crm.doctype.email_campaign.email_campaign.send_email_to_leads_or_contacts`
4. Check Email Queue for the outgoing email

### Test 3: End-to-End Webflow Test

1. Submit a test form on Webflow newsletter
2. Verify Lead created in Frappe CRM
3. Verify Email Campaign auto-created (CRM → Email Campaign)
4. Wait for scheduler (or run manually)
5. Verify email in Email Queue / recipient inbox

### Test 4: Duplicate Prevention

1. Submit same email twice via Webflow
2. Verify only one Email Campaign exists for that Lead

## Manual Testing Commands

### Run Email Campaign Scheduler Manually

```bash
# From bench directory
bench execute erpnext.crm.doctype.email_campaign.email_campaign.send_email_to_leads_or_contacts
```

### Check Email Queue

```bash
# In bench console
bench console
```

```python
import frappe
# Get pending emails
emails = frappe.get_all('Email Queue', 
    filters={'status': 'Not Sent'}, 
    fields=['name', 'recipient', 'subject', 'creation']
)
for email in emails:
    print(email)
```

### Check Campaign Enrollments

```python
import frappe
# Get all email campaigns for Newsletter Welcome
campaigns = frappe.get_all('Email Campaign',
    filters={'campaign_name': 'Newsletter Welcome'},
    fields=['name', 'recipient', 'status', 'start_date']
)
for campaign in campaigns:
    print(campaign)
```

## Expected Results

| Test | Expected Behavior |
|------|-------------------|
| Scheduler Registration | Job appears in Scheduled Job Type list |
| Manual Campaign | Email appears in Email Queue with status "Not Sent" or "Sent" |
| End-to-End Webflow | Lead created + Email Campaign created + Email sent |
| Duplicate Prevention | Same lead has only one Email Campaign record |

## Troubleshooting

### Email Not Sending

1. Check System Settings → Enable Scheduler is checked
2. Check Email Account is configured properly
3. Check Error Log for email sending errors
4. Verify SMTP credentials are correct

### Lead Not Auto-Enrolled

1. Check form_name field on Lead
2. Verify it matches newsletter patterns: "Newsletter", "Newsletter Signup", "newsletter-signup", etc.
3. Check Error Log for "Newsletter Auto-Enrollment" errors
4. Verify Campaign "Newsletter Welcome" exists

### Campaign Exists But Email Not Sent

1. Check Campaign Email Schedule exists for "Newsletter Welcome Email"
2. Check Email Template "Newsletter Welcome Email" exists
3. Run scheduler manually to test
4. Check if start_date is in the future (should be today or past)
