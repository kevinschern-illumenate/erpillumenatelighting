# Job Title Master

## Overview
The Job Title Master doctype maintains a standardized list of job titles for the lighting industry, used in CRM Leads to ensure data consistency and improve reporting.

## Features
- Categorized job titles for better organization
- Active/inactive status for lifecycle management
- Sort order control for dropdown presentation
- Upgrade-safe implementation using Frappe custom fields

## Usage

### Adding New Job Titles
1. Navigate to: ilLumenate Lighting → ilL-Job-Title-Master
2. Click "New"
3. Enter job title name, category, and sort order
4. Save

### Managing Existing Titles
- Use "Is Active" checkbox to hide obsolete titles without deleting
- Adjust "Sort Order" to control dropdown presentation
- Edit descriptions for clarity

### Integration with CRM Lead
The job_title field in CRM Lead now links to this master data.
- Users select from predefined list
- "Other" option available for edge cases
- Historical data migrated during patch execution

## Technical Details

### Field Specifications
- **job_title_name**: Unique identifier and display name
- **category**: Groups titles for reporting (Design & Engineering, Procurement & Purchasing, Project Management, Facility Management, Sales & Distribution, Other)
- **sort_order**: Controls presentation order (lower numbers appear first)
- **is_active**: Controls visibility in new forms (inactive titles won't appear in dropdowns)
- **description**: Optional clarification of the role

### Initial Job Titles
The following job titles are included in the initial fixture data:

| Job Title | Category | Sort Order |
|-----------|----------|------------|
| Lighting Designer | Design & Engineering | 1 |
| Electrical Engineer | Design & Engineering | 2 |
| Architect | Design & Engineering | 3 |
| Project Manager | Project Management | 4 |
| Construction Manager | Project Management | 5 |
| Facility Manager | Facility Management | 6 |
| Purchasing Manager | Procurement & Purchasing | 7 |
| Procurement Specialist | Procurement & Purchasing | 8 |
| Electrical Contractor | Project Management | 9 |
| Distributor | Sales & Distribution | 10 |
| Sales Representative | Sales & Distribution | 11 |
| Interior Designer | Design & Engineering | 12 |
| Other | Other | 99 |

### Database Migration
Existing job title data is migrated via patch:
- `illumenate_lighting.patches.convert_lead_job_title_to_link`
- Unique titles auto-created in Job Title Master
- Invalid/unmapped titles defaulted to "Other"

### Rollback Procedure
If needed, the migration can be reversed:
1. Delete the Property Setters for CRM Lead job_title field via Frappe UI
2. Job Title Master records can be kept or deleted as needed
3. Original data remains in the database
