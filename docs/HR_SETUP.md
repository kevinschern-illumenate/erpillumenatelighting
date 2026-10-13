# Frappe HR setup

Frappe HR (the `hrms` app) holds leave, attendance and expense claims for the team. Payroll stays in its current system for now; revisit after one full quarter on Frappe HR. The Accounting and HR lead is the only person who manages HR; everyone else sees only their own records.

Check progress at any point with the read-only audit (System Manager):

```
bench --site <site> execute illumenate_lighting.illumenate_lighting.portal.role_audit.hr
```

It reports `hrms_installed`, staff with no Employee record, Employees not tied to a login, Employees without a current leave policy or approvers, companies without a holiday list, and everyone who can open other people's HR records. Setup is done when every list is empty except `hr_role_holders` (the HR lead only) and `system_managers`.

## 1. Install

If the audit says `"hrms_installed": false`, add the HRMS app on the branch matching ERPNext (`version-16`) to the Frappe Cloud bench group, deploy, and install it on staging first, then production.

## 2. Company calendar

1. **Holiday List** for the calendar year: add weekly offs (Saturday, Sunday) and the company holidays.
2. **Company → Default Holiday List**: pick it. Leave and attendance skip these days.
3. **Departments**: Management, Sales, Accounting and HR, Marketing, Operations.
4. **Designations**: Owner, Accounting and HR Lead, Marketing and Web, Logistics and Assembly, Systems Administrator.

## 3. People

1. One **Employee** per person, with **User ID** set to their login and **Create User Permission** ticked (the default). That permission is what limits each person to their own Employee, leave and expense records.
2. **Leave Approver** and **Expense Approver** on each Employee: the HR lead for everyone, and the Owner for the HR lead. Give approvers the **Leave Approver** and **Expense Approver** roles.
3. Roles: everyone gets **Employee** and **Employee Self Service**. Only the HR lead gets **HR Manager**. Nobody gets **HR User**. System Managers can still open every record, so keep that role to the systems administrator.

## 4. Leave

1. **Leave Types**: Paid Time Off, Sick Leave, and Leave Without Pay (tick **Is Leave Without Pay**).
2. **Leave Policy**: the annual days for each type, set by the HR lead, then submit it.
3. **Leave Policy Assignment** for each Employee, effective for the leave period (the calendar year), and submit. This creates their allocations.
4. Attendance (default chosen here): no clock-in. Approved leave marks the absence; the HR lead marks other absences with **Employee Attendance Tool** when needed. Revisit if hourly tracking is ever required.

## 5. Expense claims

1. **Expense Claim Types**: Mileage, Supplies and Materials, Travel, Meals, each with the company's expense account.
2. People submit claims with receipts attached; the approver approves them.
3. QuickBooks is the payables book: Accounting reimburses approved claims from QuickBooks, then records the payment against the claim in ERPNext so it shows Paid.

## 6. Day to day

| Who | Does | Where |
|---|---|---|
| Everyone | Request leave, check balances, submit expenses | Frappe HR app at `/hrms`, or **Leave Application** / **Expense Claim** in Desk |
| HR lead | Approve leave and expenses, keep Employee records current | Approval notifications, **Leave Application** and **Expense Claim** lists |
| Owner | Approve the HR lead's leave and expenses | Same |
| Systems admin | Run `role_audit.hr` after any role change or new hire | Bench |

## 7. Acceptance

Each person requests a day of leave and the HR lead approves it. One person submits a small expense claim with a receipt and it is approved. Logged in as someone other than the HR lead, opening another person's Employee, Leave Application or Expense Claim is refused. `role_audit.hr` shows only the HR lead under `hr_role_holders`.
