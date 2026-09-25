# Quote intake and issued offers

A schedule quote request is an unpriced intake receipt. Its customer is the project's owning dealer company; the schedule snapshot retains the end-client reference. Existing intake records with the wrong commercial customer must be reviewed and replaced rather than silently rewritten.

Sales staff open an `ilL-Quote-Request` and choose **Prepare Quotation**, selecting the ERP selling company. The service prepares a draft ERP Quotation with the shared schedule row converter, configured Items and required BOMs. Review rates, taxes, exclusions, validity and terms using ERP. Submitting a Quotation linked through `ill_quote_request` creates the immutable portal offer and private issued PDF. Only that event marks the schedule QUOTED. A generic submitted Quotation without an intake link is not advertised as an issued portal offer.

Company dealers review offers under `/portal/quotes`. Technical collaborators and non-dealers cannot retrieve commercial offers. They can continue to use technical schedule/request access. Offer pages return an explicit commercial projection; the native offer record, including internal build snapshots, is restricted to sales staff. PDF access follows current company access, including after revocation.

Acceptance checks the current offer, ERP submission/cancellation status, validity date, customer and schedule content. It invokes ERP's Quotation-to-Sales-Order mapper, then checks quantities, rates, amounts, totals and pinned build links against the issued snapshot. Acceptance creates a **draft Sales Order** and its review intake. It does not submit a Sales Order or start production. The selected date is recorded as a buyer request. The native approval guard still requires staff authority and buyer acknowledgment of the current order revision. A cancelled source Quotation or detached accepted-offer link blocks approval.

Duplicate identical buyer responses return the existing receipt. A changed response conflicts; Sales must use the appropriate revision/change workflow. Decline and revision requests retain the original offer, note and actor. A replacement issued offer supersedes a previously open offer. Existing offers and private PDFs are retained.

The additive permission migration manages only the new `ilL Sales Review` and `ilL Order Approver` roles, preserving unrelated Custom DocPerm rules. It assigns no users. Sales reviewers can prepare and issue Quotations and edit draft Sales Orders. Only order approvers receive Sales Order submit permission from this migration. Native ERP permissions and the service's System User/capability checks both apply.

Local tests cover conversion mismatch, expiry, cancellation, supersession, current-schedule mismatch, denied commercial access, and duplicate acceptance. The new pages are rendered with local Jinja and checked for escaped content and read-only states. Frappe Cloud must still verify actual mapper behavior, print rendering, role/User Permission interactions, concurrent requests and native file downloads against its installed versions.

ERP conversion was checked against the [version-15 Quotation implementation](https://github.com/frappe/erpnext/blob/version-15/erpnext/selling/doctype/quotation/quotation.py); the installed Cloud commit remains part of release verification.
