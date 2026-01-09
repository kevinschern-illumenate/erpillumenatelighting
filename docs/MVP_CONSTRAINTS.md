# MVP Constraints and Known Limitations

This document outlines the current limitations and constraints of the ilLumenate Lighting MVP.
This serves as a clear scope statement for the team before shipping.

## Version Information

- **Engine Version**: 1.0.0
- **Document Updated**: January 2026

---

## Fixture Configuration Constraints

### SH01 Maximum Length (No Joiners)

The SH01 template **does not currently support joiner systems**. This means:

- **Maximum assembled shipping length**: 2590mm (~8.5 feet)
- Fixtures exceeding this length ship as "SHIP_PIECES" requiring field assembly
- No joiner accessories are available in the configurator
- Field assembly of longer fixtures requires customer to connect profile segments

**Workaround**: For continuous runs exceeding 8.5ft, customers must order multiple fixtures and plan for field joining.

### Lens Configuration

- **Lens sticks are 2-meter (2000mm) only** in the current inventory
- Lens quantity mirrors profile segment count (1:1 ratio)
- Continuous lens rolls are not implemented in MVP
- Lens segmentation follows profile segmentation exactly

### Tape Voltage Drop Calculations

- **Only the 85W power limit rule is fully implemented**
- The voltage drop lookup table is **not implemented**
- `max_run_ft_by_voltage_drop` uses the static value from tape spec when available
- Dynamic voltage drop calculation based on tape length and wire gauge is deferred

**Impact**: For high-wattage or long runs, manual engineering review may be needed.

---

## Pricing Constraints

### Customer Tier Pricing

- **MSRP pricing only** in MVP
- Customer price lists and tier discounts are not implemented
- `tier_unit` always equals `msrp_unit`
- Volume discounts are not calculated

### Pricing Visibility

- Pricing is hidden from users without the "Can View Pricing" role
- Priced exports (PDF/CSV) require explicit pricing permission
- API responses do not include pricing for unauthorized users

---

## Order and Manufacturing Constraints

### Payments

- **Payment processing is not implemented**
- No integration with payment gateways
- No deposit or milestone payment workflows
- Manual payment handling required outside the system

### Serial Number Traceability

- **Limited traceability - Serial numbers for finished goods only**
- Component-level serial tracking is not implemented
- Batch tracking for LED tape and other components is not implemented
- No parent-child serial number relationships

### Work Order Constraints

- Work Orders are created in Draft status
- Submission and completion workflows are standard ERPNext
- No custom routing or operation tracking in MVP
- Traveler notes are text-based only

---

## Technical Constraints

### Mapping Requirements

For the configurator to work correctly, all mapping tables must be populated:

1. **ilL-Rel-Endcap-Map**: Must cover all (style × color) combinations
2. **ilL-Rel-Mounting-Accessory-Map**: Must cover all mounting methods
3. **ilL-Rel-Leader-Cable-Map**: Must cover all (tape_spec × power_feed_type) combinations
4. **ilL-Rel-Driver-Eligibility**: Must be configured for driver auto-selection

**Recommendation**: Run `run_coverage_audit()` API before going live.

### Performance Considerations

- Configured Fixture lookups use config_hash index
- Mapping resolution is done per-request (cached in memory during request)
- Large schedules (>100 lines) may experience slower export generation
- PDF generation uses wkhtmltopdf which may be slow for complex documents

---

## User Experience Constraints

### Portal Limitations

- Portal UI is template-driven (Jinja)
- No real-time collaboration features
- Configuration changes require page refresh
- Mobile responsiveness is basic

### Collaboration Features

- Project collaborators can view/edit based on access level
- Real-time notifications not implemented
- Email notifications for schedule changes not implemented

---

## Security and Access Control

### Company Visibility

- Projects are visible to all users in the same `owner_customer` company
- Private projects require explicit collaborator access
- Schedule visibility inherits from project when `inherits_project_privacy = 1`

### Export File Access

- Export files are saved with `is_private = 0` (publicly accessible URLs)
- URL knowledge grants access to export files
- No time-limited or token-based download links in MVP

**Recommendation**: Implement private file storage for priced exports in a future release.

---

## Integration Constraints

### External Systems

- No ERP integration beyond native ERPNext functionality
- No CRM integration
- No CAD/design software integration
- No shipping carrier integration

### API Limitations

- All API endpoints require authenticated sessions
- No public API endpoints
- Rate limiting uses standard Frappe defaults
- No webhook support for external integrations

---

## Data Migration Constraints

### Upgrading Existing Sites

- Fixtures and patches handle forward migration
- Backward-compatible field additions only
- No automated data transformation for changed field semantics
- Manual review recommended after upgrades

---

## Known Issues Requiring Resolution Post-MVP

1. **Continuous lens** option for lengths requiring fewer seams
2. **Joiner system** support for SH01 and future templates
3. **Voltage drop lookup tables** for accurate run length calculations
4. **Customer tier pricing** with price lists and discounts
5. **Private file downloads** with access validation
6. **Component-level traceability** with batch/serial linking
7. **Real-time collaboration** features

---

## Support and Escalation

For issues related to these constraints:

1. Review this document to confirm it's a known limitation
2. Check the QA Checklist for expected behavior
3. Escalate to engineering if behavior differs from documented constraints

---

*This document should be updated as constraints are resolved or new ones are identified.*
